"""HEnEx Day-Ahead Market actual price fetcher.

Downloads the daily DAM Results Summary XLSX from enexgroup.gr and produces
a CSV with columns (timestamp, price_eur_mwh) at 15-min MTU resolution.

URL pattern documented by HEnEx for automated download:
  https://www.enexgroup.gr/documents/20126/366820/<YYYYMMDD>_EL-DAM_ResultsSummary_EN_v<NN>.xlsx

The version suffix (_v01, _v02 …) increases when HEnEx republishes a corrected
file; this fetcher probes from v01 upwards and keeps the highest available.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
from openpyxl import load_workbook

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

URL_TEMPLATE = (
    "https://www.enexgroup.gr/documents/20126/366820/"
    "{ymd}_EL-DAM_ResultsSummary_EN_v{ver:02d}.xlsx"
)
USER_AGENT = (
    "Mozilla/5.0 (compatible; HENEX-Hackathon-Optimiser/1.0; "
    "+https://github.com/anthropics/claude-code)"
)


def fetch_dam_xlsx(target_date: date, max_version: int = 10) -> tuple[bytes, str]:
    """Download the latest available DAM Results Summary XLSX for `target_date`.

    Returns (raw_bytes, source_url). Raises RuntimeError if no version is found.
    """
    ymd = target_date.strftime("%Y%m%d")
    last_bytes: bytes | None = None
    last_url: str | None = None

    for ver in range(1, max_version + 1):
        url = URL_TEMPLATE.format(ymd=ymd, ver=ver)
        req = Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urlopen(req, timeout=20) as resp:
                if resp.status != 200:
                    continue
                last_bytes = resp.read()
                last_url = url
        except HTTPError as e:
            if e.code == 404:
                if last_bytes is not None:
                    break
                continue
            raise
        except URLError:
            continue

    if last_bytes is None:
        raise RuntimeError(
            f"No DAM Results Summary published for {target_date.isoformat()} yet "
            f"(probed v01–v{max_version:02d} at {URL_TEMPLATE.split('{ymd}')[0]}…)."
        )

    return last_bytes, last_url


def parse_dam_xlsx(xlsx_bytes: bytes, target_date: date) -> pd.DataFrame:
    """Parse the HEnEx DAM Results Summary workbook and return a 96-row
    DataFrame with columns (timestamp, price_eur_mwh) at 15-min MTU.

    The workbook layout: a "Market Clearing Price" or "MCP" row whose 24 hourly
    values lie horizontally. We locate it by scanning the first column for the
    label, then read the numeric cells to its right.
    """
    from io import BytesIO

    wb = load_workbook(filename=BytesIO(xlsx_bytes), data_only=True)

    hourly: list[float] | None = None

    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            if not row:
                continue
            label = row[0]
            if not isinstance(label, str):
                continue
            label_norm = label.strip().lower()
            if "market clearing price" in label_norm or label_norm in {"mcp", "mcp (€/mwh)"}:
                values = [c for c in row[1:] if isinstance(c, (int, float))]
                if len(values) >= 24:
                    hourly = [float(v) for v in values[:24]]
                    break
        if hourly is not None:
            break

    if hourly is None:
        raise ValueError(
            "Could not locate the Market Clearing Price row in the DAM XLSX. "
            "HEnEx may have changed the workbook layout."
        )

    base = datetime.combine(target_date, datetime.min.time())
    rows = []
    for h in range(24):
        for q in range(4):
            rows.append({
                "timestamp": base + timedelta(hours=h, minutes=15 * q),
                "price_eur_mwh": hourly[h],
            })

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
