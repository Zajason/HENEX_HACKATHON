"""Produce P10/P50/P90 forecasts for a delivery day.

Usage:
    python -m scripts.predict_day --date 2026-04-30
    python -m scripts.predict_day --date 2026-04-30 --pipeline models/forecast_pipeline.pkl

Reads the per-day aligned dataset (data/processed/<date>_aligned_dataset.csv),
runs the trained pipeline, writes:
    data/processed/<date>_forecast.csv with timestamp + p10/p50/p90.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from forecast.pipeline import ForecastPipeline, predict_day

PROCESSED_DIR = Path("data") / "processed"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="ISO date YYYY-MM-DD")
    p.add_argument(
        "--pipeline",
        type=Path,
        default=Path("models") / "forecast_pipeline.pkl",
    )
    p.add_argument("--resolution", choices=["hourly", "15min"], default="15min")
    args = p.parse_args()

    feature_path = PROCESSED_DIR / f"{args.date}_aligned_dataset.csv"
    if not feature_path.exists():
        raise SystemExit(
            f"Aligned dataset not found at {feature_path}. "
            f"Run `python data_pipeline.py` for {args.date} first."
        )
    day_df = pd.read_csv(feature_path, parse_dates=["timestamp"])

    pipeline = ForecastPipeline.load(args.pipeline)
    out = predict_day(pipeline, day_df, resolution=args.resolution)

    out_path = PROCESSED_DIR / f"{args.date}_forecast.csv"
    out.to_csv(out_path, index=False)
    print(f"[PREDICT] wrote {out_path} ({len(out)} rows)")


if __name__ == "__main__":
    main()
