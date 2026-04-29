"""
Predict P10/P50/P90 for a delivery day using the frozen Tier-0 model.

Runs WITHOUT training data on disk. Fetches the day's IPTO load + RES
forecasts, Open-Meteo per-zone weather, and the latest macro
(TTF/EUA proxies via yfinance) live from the internet, builds the
feature frame, and predicts using the pickled model in models/.

Usage:
    python -m scripts.predict_tomorrow --date 2026-04-30
    python -m scripts.predict_tomorrow --date 2026-04-30 --dry-run

The --dry-run flag fetches inputs and builds the feature frame but does
not load the model — useful for verifying the inference data path on a
machine that doesn't yet have the model artefacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from data_pipeline import (
    download_ipto_load,
    download_ipto_res,
    parse_ipto_forecast,
    get_macro_for_delivery_day,
)
from forecast.features import build_feature_frame
from forecast.tier0 import Tier0Model
from weather_sources import GREEK_ZONES, build_capacity_weighted_weather_dataset


MODEL_DIR = Path("models")
DEFAULT_OUT_DIR = Path("data/processed")


# ----------------------------------------------------------------------
# Live Open-Meteo fetch for the six Greek zones
# ----------------------------------------------------------------------

def _open_meteo_url(lat: float, lon: float, date: str) -> str:
    return (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=temperature_2m,wind_speed_10m,shortwave_radiation"
        f"&start_date={date}&end_date={date}"
        "&timezone=Europe%2FAthens"
    )


def fetch_zone_weather_open_meteo(date: str) -> pd.DataFrame:
    """Per-zone hourly weather for `date`, with capacity weights attached."""
    rows = []
    for zone in GREEK_ZONES:
        url = _open_meteo_url(zone["lat"], zone["lon"], date)
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            raise SystemExit(
                f"Open-Meteo fetch failed for zone {zone['zone']}: "
                f"{r.status_code} | {url}"
            )
        h = r.json().get("hourly", {})
        if not h:
            raise SystemExit(f"Open-Meteo returned no hourly block for {zone['zone']}.")
        zdf = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(h["time"]),
                "temperature_2m_c": h.get("temperature_2m"),
                "wind_speed_10m": h.get("wind_speed_10m"),
                "shortwave_radiation": h.get("shortwave_radiation"),
            }
        )
        zdf["zone"] = zone["zone"]
        zdf["solar_weight"] = zone["solar_weight"]
        zdf["wind_weight"] = zone["wind_weight"]
        zdf["load_weight"] = zone["load_weight"]
        rows.append(zdf)
    return pd.concat(rows, ignore_index=True)


def aggregate_weather(zone_weather: pd.DataFrame) -> pd.DataFrame:
    """Capacity-weight then rename `*_shortwave_radiation` -> `*_ssrd_wm2`
    so the column names match what the model trained on."""
    weighted = build_capacity_weighted_weather_dataset(
        zone_weather, output_name="predict_tomorrow_weighted.csv"
    )
    rename = {}
    for c in weighted.columns:
        if c.endswith("_shortwave_radiation"):
            rename[c] = c.replace("_shortwave_radiation", "_ssrd_wm2")
    return weighted.rename(columns=rename)


# ----------------------------------------------------------------------
# 15-min broadcast for hourly weather
# ----------------------------------------------------------------------

def hourly_to_15min(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("timestamp").drop_duplicates("timestamp").set_index("timestamp")
    idx = pd.date_range(df.index.min(), df.index.max() + pd.Timedelta("45min"),
                        freq="15min")
    out = df.reindex(idx, method="ffill")
    out.index.name = "timestamp"
    return out.reset_index()


# ----------------------------------------------------------------------
# Build the feature frame for one day
# ----------------------------------------------------------------------

def build_inference_frame(date: str) -> pd.DataFrame:
    print(f"[predict] fetching IPTO load forecast for {date}")
    load = parse_ipto_forecast(download_ipto_load(date), "load_forecast_mw", date)
    print(f"[predict] fetching IPTO RES forecast for {date}")
    res = parse_ipto_forecast(download_ipto_res(date), "res_forecast_mw", date)

    print(f"[predict] fetching Open-Meteo for {len(GREEK_ZONES)} Greek zones")
    zone_weather = fetch_zone_weather_open_meteo(date)
    weather = aggregate_weather(zone_weather)
    weather_15 = hourly_to_15min(weather)

    print(f"[predict] fetching macro drivers (TTF / EUA proxies)")
    macro = get_macro_for_delivery_day(date)

    df = load.merge(res, on="timestamp", how="outer").sort_values("timestamp")
    df = pd.merge_asof(
        df,
        weather_15.sort_values("timestamp"),
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta("30min"),
    )
    if not macro.empty:
        df["date"] = df["timestamp"].dt.date
        macro_row = macro.tail(1).copy()
        macro_row["date"] = df["date"].iloc[-1]
        df = df.merge(macro_row, on="date", how="left").drop(columns=["date"])

    return df


# ----------------------------------------------------------------------
# Validate against manifest, predict, write output
# ----------------------------------------------------------------------

def load_manifest() -> dict:
    path = MODEL_DIR / "manifest.json"
    if not path.exists():
        raise SystemExit(
            f"manifest not found at {path}. "
            "Ask your training-side teammate to run scripts/freeze_model.py "
            "and commit models/ to the branch."
        )
    return json.loads(path.read_text())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="ISO delivery date, e.g. 2026-04-30")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--dry-run", action="store_true",
                   help="build the feature frame and report columns; skip prediction")
    args = p.parse_args()

    df = build_inference_frame(args.date)
    feats = build_feature_frame(df)
    print(f"\n[predict] feature frame: {len(feats)} rows | "
          f"{feats['timestamp'].min()} -> {feats['timestamp'].max()}")

    if args.dry_run:
        present = sorted(feats.columns.tolist())
        print(f"[predict] (dry run) columns produced: {len(present)}")
        for c in present:
            print(f"           {c}")
        return

    manifest = load_manifest()
    expected = manifest["feature_cols"]
    missing = [c for c in expected if c not in feats.columns]
    if missing:
        raise SystemExit(
            f"feature frame missing {len(missing)} columns the model needs:\n"
            f"  {missing}\n"
            "If these are weather columns, the inference weather path likely\n"
            "broke (Open-Meteo schema change?). Otherwise an upstream fetch failed."
        )

    print(f"[predict] loading model from {MODEL_DIR / 'tier0.pkl'}")
    model = Tier0Model.load(MODEL_DIR / "tier0.pkl")
    out = model.predict(feats)

    mad_path = MODEL_DIR / "mad_table.parquet"
    if mad_path.exists():
        mad = pd.read_parquet(mad_path)
        out["hour"] = pd.to_datetime(out["timestamp"]).dt.hour
        out["weekday"] = pd.to_datetime(out["timestamp"]).dt.weekday
        out = out.merge(
            mad[["hour", "weekday", "mad_eur_mwh"]],
            on=["hour", "weekday"],
            how="left",
        ).drop(columns=["hour", "weekday"])

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{args.date}_forecast.csv"
    out.to_csv(out_path, index=False)

    print(f"\n[predict] wrote {out_path} ({len(out)} rows)")
    print(out.head(4).to_string(index=False))
    print("...")
    print(out.tail(4).to_string(index=False))


if __name__ == "__main__":
    main()
