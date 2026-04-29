"""
HEnEx market-tightness calculator.

This module reads the HEnEx aggregated buy/sell curve XLSX files and estimates
market tightness as the local dP/dQ around the clearing point. Higher values mean
the market is steeper: a small MW imbalance would move price more.

Typical use in your optimizer:

    from market_tightness import add_market_tightness

    df = pd.read_csv("synthetic_forecast_day.csv", parse_dates=["timestamp"])
    df = add_market_tightness(
        df,
        curves_path="2025_EL-DAM-IDAs_AggrCurves/2025_EL-DAM-IDAs_AggrCurves.zip/DAM/20250108_EL-DAM_AggrCurves_EN_v01.xlsx",
        results_path="2025_EL-DAM-IDAs_Results/2025_EL-DAM-IDAs_Results.zip/Results/DAM/20250108_EL-DAM_Results_EN_v01.xlsx",
    )
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable
from zipfile import ZipFile
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd


XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
DEFAULT_VOLUME_SHOCK_MW = 75.0


def normalize_series(s: pd.Series) -> pd.Series:
    values = s.astype(float)
    span = values.max() - values.min()
    if not np.isfinite(span) or span <= 1e-12:
        return pd.Series(0.0, index=s.index)
    return (values - values.min()) / span


def read_henex_xlsx(path: str | Path) -> pd.DataFrame:
    """
    Read simple HEnEx XLSX exports without requiring openpyxl.

    The HEnEx files in this dataset are single-sheet workbooks with shared
    strings, so a small XML reader is enough and keeps the module lightweight.
    """

    path = Path(path)
    with ZipFile(path) as zf:
        shared_strings = _read_shared_strings(zf)
        sheet_name = _first_worksheet_name(zf)
        root = ET.fromstring(zf.read(sheet_name))

    rows: list[list[object]] = []
    for row in root.iter(f"{XML_NS}row"):
        values: list[object] = []
        for cell in row.findall(f"{XML_NS}c"):
            col_idx = _column_index(cell.attrib.get("r", "A"))
            while len(values) <= col_idx:
                values.append(None)
            values[col_idx] = _cell_value(cell, shared_strings)
        rows.append(values)

    if not rows:
        return pd.DataFrame()

    header = [str(col).strip() if col is not None else f"col_{i}" for i, col in enumerate(rows[0])]
    return pd.DataFrame(rows[1:], columns=header)


def calculate_market_tightness(
    curves_path: str | Path,
    results_path: str | Path | None = None,
    volume_shock_mw: float = DEFAULT_VOLUME_SHOCK_MW,
) -> pd.DataFrame:
    """
    Calculate hourly market tightness from one HEnEx aggregated-curve file.

    Parameters
    ----------
    curves_path:
        HEnEx `*_AggrCurves_*.xlsx` file.
    results_path:
        Optional matching `*_Results_*.xlsx` file. If present, MCP is used as
        the clearing price. If absent, the clearing price is estimated from the
        buy/sell curve intersection.
    volume_shock_mw:
        MW shock used to estimate local dP/dQ. For a 75 MW battery, 75 is a
        useful default. Smaller values make the metric more local but noisier.

    Returns
    -------
    DataFrame with timestamp, clearing price, raw tightness, and normalized
    tightness. Raw units are approximately EUR/MWh per MW.
    """

    curves = read_henex_xlsx(curves_path)
    _require_columns(curves, {"SIDE_DESCR", "DELIVERY_MTU", "QUANTITY", "UNITPRICE"})

    curves = curves.copy()
    curves["timestamp"] = pd.to_datetime(curves["DELIVERY_MTU"], errors="coerce")
    curves["QUANTITY"] = pd.to_numeric(curves["QUANTITY"], errors="coerce")
    curves["UNITPRICE"] = pd.to_numeric(curves["UNITPRICE"], errors="coerce")
    curves["SIDE_DESCR"] = curves["SIDE_DESCR"].astype(str).str.strip().str.lower()
    curves = curves.dropna(subset=["timestamp", "QUANTITY", "UNITPRICE", "SIDE_DESCR"])

    mcp_by_timestamp = _load_mcp(results_path) if results_path else {}

    records = []
    for timestamp, group in curves.groupby("timestamp", sort=True):
        buy = group[group["SIDE_DESCR"].eq("buy")]
        sell = group[group["SIDE_DESCR"].eq("sell")]
        if buy.empty or sell.empty:
            continue

        clearing_price = mcp_by_timestamp.get(timestamp)
        metric = _tightness_for_hour(
            buy_prices=buy["UNITPRICE"].to_numpy(float),
            buy_quantities=buy["QUANTITY"].to_numpy(float),
            sell_prices=sell["UNITPRICE"].to_numpy(float),
            sell_quantities=sell["QUANTITY"].to_numpy(float),
            clearing_price=clearing_price,
            volume_shock_mw=volume_shock_mw,
        )
        if metric is None:
            continue

        records.append(
            {
                "timestamp": timestamp,
                "clearing_price_eur_mwh": metric["clearing_price"],
                "clearing_volume_mw": metric["clearing_volume"],
                "market_tightness": metric["tightness"],
                "shock_down_price_eur_mwh": metric["shock_down_price"],
                "shock_up_price_eur_mwh": metric["shock_up_price"],
            }
        )

    out = pd.DataFrame(records).sort_values("timestamp").reset_index(drop=True)
    if out.empty:
        raise ValueError(f"No market-tightness rows could be calculated from {curves_path}")

    out["market_tightness_norm"] = normalize_series(out["market_tightness"])
    return out


def add_market_tightness(
    forecast: pd.DataFrame,
    curves_path: str | Path,
    results_path: str | Path | None = None,
    timestamp_col: str = "timestamp",
    volume_shock_mw: float = DEFAULT_VOLUME_SHOCK_MW,
) -> pd.DataFrame:
    """
    Add `market_tightness` and `market_tightness_norm` to a forecast DataFrame.

    If the forecast is 15-minute data and the HEnEx curve is hourly, the hourly
    tightness is matched by flooring forecast timestamps to the hour.
    """

    if timestamp_col not in forecast.columns:
        raise ValueError(f"Forecast is missing timestamp column: {timestamp_col}")

    tightness = calculate_market_tightness(
        curves_path=curves_path,
        results_path=results_path,
        volume_shock_mw=volume_shock_mw,
    )

    out = forecast.copy()
    out[timestamp_col] = pd.to_datetime(out[timestamp_col], errors="coerce")
    out["_tightness_hour"] = out[timestamp_col].dt.floor("h")

    joined = out.merge(
        tightness.rename(columns={"timestamp": "_tightness_hour"}),
        on="_tightness_hour",
        how="left",
    ).drop(columns=["_tightness_hour"])

    if joined["market_tightness"].isna().any():
        missing = int(joined["market_tightness"].isna().sum())
        raise ValueError(
            f"Could not match market tightness for {missing} forecast rows. "
            "Check that the forecast date matches the HEnEx curve file date."
        )

    return joined


def _tightness_for_hour(
    buy_prices: np.ndarray,
    buy_quantities: np.ndarray,
    sell_prices: np.ndarray,
    sell_quantities: np.ndarray,
    clearing_price: float | None,
    volume_shock_mw: float,
) -> dict[str, float] | None:
    buy_curve = _prepare_curve(buy_prices, buy_quantities)
    sell_curve = _prepare_curve(sell_prices, sell_quantities)
    if buy_curve is None or sell_curve is None:
        return None

    buy_p, buy_q = buy_curve
    sell_p, sell_q = sell_curve

    price_grid = np.unique(np.concatenate([buy_p, sell_p]))
    if price_grid.size < 2:
        return None

    def buy_at(price: float | np.ndarray) -> np.ndarray:
        return np.interp(price, buy_p, buy_q)

    def sell_at(price: float | np.ndarray) -> np.ndarray:
        return np.interp(price, sell_p, sell_q)

    def net_supply(price: float | np.ndarray) -> np.ndarray:
        return sell_at(price) - buy_at(price)

    if clearing_price is None or not np.isfinite(clearing_price):
        clearing_price = _price_at_net_supply(price_grid, net_supply(price_grid), target=0.0)

    clearing_net = float(net_supply(clearing_price))
    shock_down_price = _price_at_net_supply(price_grid, net_supply(price_grid), clearing_net - volume_shock_mw)
    shock_up_price = _price_at_net_supply(price_grid, net_supply(price_grid), clearing_net + volume_shock_mw)

    tightness = abs(shock_up_price - shock_down_price) / max(2.0 * volume_shock_mw, 1e-9)
    clearing_volume = (float(buy_at(clearing_price)) + float(sell_at(clearing_price))) / 2.0

    return {
        "clearing_price": float(clearing_price),
        "clearing_volume": clearing_volume,
        "tightness": float(tightness),
        "shock_down_price": float(shock_down_price),
        "shock_up_price": float(shock_up_price),
    }


def _prepare_curve(prices: np.ndarray, quantities: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    ok = np.isfinite(prices) & np.isfinite(quantities)
    prices = prices[ok]
    quantities = quantities[ok]
    if prices.size < 2:
        return None

    df = pd.DataFrame({"price": prices, "quantity": quantities})
    df = df.groupby("price", as_index=False)["quantity"].mean().sort_values("price")
    return df["price"].to_numpy(float), df["quantity"].to_numpy(float)


def _price_at_net_supply(price_grid: np.ndarray, net_values: np.ndarray, target: float) -> float:
    order = np.argsort(net_values)
    x = net_values[order]
    y = price_grid[order]

    unique_x, unique_idx = np.unique(x, return_index=True)
    unique_y = y[unique_idx]
    if unique_x.size == 1:
        return float(unique_y[0])

    clipped_target = float(np.clip(target, unique_x.min(), unique_x.max()))
    return float(np.interp(clipped_target, unique_x, unique_y))


def _load_mcp(results_path: str | Path) -> dict[pd.Timestamp, float]:
    results = read_henex_xlsx(results_path)
    _require_columns(results, {"DELIVERY_MTU", "MCP"})

    results = results.copy()
    results["timestamp"] = pd.to_datetime(results["DELIVERY_MTU"], errors="coerce")
    results["MCP"] = pd.to_numeric(results["MCP"], errors="coerce")
    results = results.dropna(subset=["timestamp", "MCP"])
    return results.groupby("timestamp")["MCP"].first().to_dict()


def _read_shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall(f"{XML_NS}si"):
        strings.append("".join(text.text or "" for text in item.iter(f"{XML_NS}t")))
    return strings


def _first_worksheet_name(zf: ZipFile) -> str:
    sheets = sorted(name for name in zf.namelist() if name.startswith("xl/worksheets/sheet"))
    if not sheets:
        raise ValueError("Workbook has no worksheets")
    return sheets[0]


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> object:
    value = cell.find(f"{XML_NS}v")
    if value is None or value.text is None:
        return None

    if cell.attrib.get("t") == "s":
        return shared_strings[int(value.text)]

    try:
        number = float(value.text)
    except ValueError:
        return value.text
    return int(number) if number.is_integer() else number


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    idx = 0
    for letter in letters:
        idx = idx * 26 + ord(letter) - ord("A") + 1
    return idx - 1


def _require_columns(df: pd.DataFrame, required: Iterable[str]) -> None:
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate HEnEx curve-derived market tightness.")
    parser.add_argument("curves_path", help="Path to a HEnEx *_AggrCurves_*.xlsx file")
    parser.add_argument("--results-path", help="Optional matching HEnEx *_Results_*.xlsx file")
    parser.add_argument("--forecast-path", help="Optional forecast CSV to enrich")
    parser.add_argument("--output", default="market_tightness.csv", help="Output CSV path")
    parser.add_argument("--volume-shock-mw", type=float, default=DEFAULT_VOLUME_SHOCK_MW)
    args = parser.parse_args()

    if args.forecast_path:
        forecast = pd.read_csv(args.forecast_path, parse_dates=["timestamp"])
        out = add_market_tightness(
            forecast,
            curves_path=args.curves_path,
            results_path=args.results_path,
            volume_shock_mw=args.volume_shock_mw,
        )
    else:
        out = calculate_market_tightness(
            args.curves_path,
            results_path=args.results_path,
            volume_shock_mw=args.volume_shock_mw,
        )

    out.to_csv(args.output, index=False)
    print(f"Saved {len(out)} rows to {args.output}")


if __name__ == "__main__":
    main()
