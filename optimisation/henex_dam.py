"""HEnEx Day-Ahead Market actual price fetcher.

Downloads the daily DAM Results Summary XLSX from enexgroup.gr and produces
a CSV with columns (timestamp, price_eur_mwh) at 15-min MTU resolution.

The Day-Ahead Market publications page lists each day's file as a Liferay
document_library link of the form:

  /c/document_library/get_file?uuid=<UUID>&groupId=20126

We scrape the page once, match the desired delivery-day filename
(`YYYYMMDD_EL-DAM_ResultsSummary_EN_v##.xlsx`) and resolve the UUID to a real
download URL. The latest version (highest v##) per date wins.
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
from openpyxl import load_workbook

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LISTING_PAGE = "https://www.enexgroup.gr/markets-publications-el-day-ahead-market"
BASE = "https://www.enexgroup.gr"
USER_AGENT = (
    "Mozilla/5.0 (compatible; HENEX-Hackathon-Optimiser/1.0)"
)

_FILE_LINK_RE = re.compile(
    r'href=["\'](/c/document_library/get_file\?[^"\']+?)["\'][^>]*>'
    r'\s*(?:<[^>]+>\s*)*'
    r'(?:&nbsp;\s*)*'
    r'(\d{8})_EL-DAM_ResultsSummary_EN_v(\d{2})\.xlsx',
    re.IGNORECASE,
)


def _list_published_files() -> dict[str, tuple[int, str]]:
    """Return {YYYYMMDD: (version, absolute_url)} for the latest version of each day."""
    req = Request(LISTING_PAGE, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    latest: dict[str, tuple[int, str]] = {}
    for href, ymd, ver_str in _FILE_LINK_RE.findall(html):
        ver = int(ver_str)
        url = href if href.startswith("http") else BASE + href
        url = url.replace("&amp;", "&")
        existing = latest.get(ymd)
        if existing is None or ver > existing[0]:
            latest[ymd] = (ver, url)
    return latest


def fetch_dam_xlsx(target_date: date) -> tuple[bytes, str]:
    """Download the latest published DAM Results Summary XLSX for `target_date`.

    Returns (raw_bytes, source_url). Raises RuntimeError if not yet published.
    """
    ymd = target_date.strftime("%Y%m%d")
    listing = _list_published_files()
    if ymd not in listing:
        available = sorted(listing.keys(), reverse=True)[:5]
        raise RuntimeError(
            f"No DAM Results Summary published for {target_date.isoformat()} on "
            f"{LISTING_PAGE}. Most recent available: {available}"
        )
    _, url = listing[ymd]
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=60) as resp:
        return resp.read(), url


def parse_dam_xlsx(xlsx_bytes: bytes, target_date: date) -> pd.DataFrame:
    """Parse the HEnEx DAM Results Summary workbook and return a 96-row
    DataFrame with columns (timestamp, price_eur_mwh) at 15-min MTU.

    Layout (verified for v01 files since the 15-min MTU rollout):
      Sheet `SPOT_Summary (SELL)` or `(BUY)` — both carry the same MCP row.
      First column row label `Greece Mainland  (15min MTU)` → 96 numeric cells
      to its right, one per 15-min MTU of the delivery day.
    """
    from io import BytesIO

    wb = load_workbook(filename=BytesIO(xlsx_bytes), data_only=True)

    candidate_sheets = [
        s for s in wb.sheetnames
        if "spot" in s.lower() or "coupling" in s.lower()
    ] or wb.sheetnames

    prices: list[float] | None = None
    for sheet_name in candidate_sheets:
        try:
            ws = wb[sheet_name]
        except KeyError:
            continue
        if not hasattr(ws, "iter_rows"):
            continue
        for row in ws.iter_rows(values_only=True):
            if not row:
                continue
            label = row[0]
            if not isinstance(label, str):
                continue
            norm = " ".join(label.lower().split())
            if "greece" in norm and "15min" in norm and "mcp" in norm:
                values = [c for c in row[1:] if isinstance(c, (int, float))]
                if len(values) >= 96:
                    prices = [float(v) for v in values[:96]]
                    break
        if prices is not None:
            break

    if prices is None:
        raise ValueError(
            "Could not locate the 15-min MCP row in the DAM XLSX. "
            "HEnEx may have changed the workbook layout."
        )

    base = datetime.combine(target_date, datetime.min.time())
    rows = [
        {
            "timestamp": base + timedelta(minutes=15 * i),
            "price_eur_mwh": prices[i],
        }
        for i in range(96)
    ]
    return pd.DataFrame(rows)


def fetch_actual_prices(target_date: date) -> tuple[pd.DataFrame, str, Path]:
    """End-to-end: fetch + parse + save CSV. Returns (df, source_url, csv_path)."""
    raw, url = fetch_dam_xlsx(target_date)
    df = parse_dam_xlsx(raw, target_date)
    csv_path = DATA_DIR / f"dam_actual_{target_date.isoformat()}.csv"
    df.to_csv(csv_path, index=False)
    return df, url, csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch HEnEx DAM clearing prices.")
    parser.add_argument(
        "--date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
        help="Delivery day (YYYY-MM-DD). Defaults to today.",
    )
    args = parser.parse_args()

    df, url, csv_path = fetch_actual_prices(args.date)
    print(f"Source: {url}")
    print(f"Saved:  {csv_path}")
    print(f"Mean clearing price: {df['price_eur_mwh'].mean():.2f} €/MWh "
          f"(min {df['price_eur_mwh'].min():.2f}, max {df['price_eur_mwh'].max():.2f})")


if __name__ == "__main__":
    main()
