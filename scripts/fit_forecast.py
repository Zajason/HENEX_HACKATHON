"""Train the forecast pipeline end-to-end on the HEnEx archive history.

Usage:
    python -m scripts.fit_forecast
    python -m scripts.fit_forecast --out models/forecast_pipeline.pkl

This is the canonical entry point for re-training. It:
    1. Loads DAM history from data/raw/henex_archive/extracted/ via forecast.io.
    2. Joins macro drivers (TTF / EUA proxies).
    3. NOTE: Forecast-vintage load / RES / weather are NOT yet stitched onto
       the historical archive frame — that requires a separate IPTO/weather
       backfill loader (see DATA.md). For now, the script will fit on
       whatever feature columns are present and skip ones that aren't.
    4. Fits the pipeline and pickles it to disk.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from forecast.io import load_training_history
from forecast.pipeline import fit_pipeline


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--out",
        type=Path,
        default=Path("models") / "forecast_pipeline.pkl",
        help="where to pickle the trained pipeline",
    )
    p.add_argument(
        "--min-date",
        type=str,
        default=None,
        help="optional ISO date floor (YYYY-MM-DD) to filter training history",
    )
    args = p.parse_args()

    print("[FIT] loading DAM + macro history ...")
    df = load_training_history()
    if args.min_date:
        df = df[df["timestamp"] >= pd.Timestamp(args.min_date)]

    print(f"[FIT] {len(df):,} rows | "
          f"{df['timestamp'].min()} -> {df['timestamp'].max()}")

    needed = ["load_forecast_mw", "res_forecast_mw"]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        print(
            f"[WARN] training frame is missing forecast-vintage features {missing}. "
            "Backfill IPTO load+RES history before training a serious model."
        )

    pipeline = fit_pipeline(df)
    pipeline.save(args.out)
    print(f"[FIT] pipeline saved to {args.out}")


if __name__ == "__main__":
    main()
