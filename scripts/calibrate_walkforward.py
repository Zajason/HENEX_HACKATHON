"""Calibrate a walk-forward prediction parquet using residual quantiles."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from forecast.calibration import (
    apply_residual_quantile_calibration,
    build_residual_quantile_table,
)
from forecast.metrics import coverage, pinball_loss

LABEL = "dam_price_eur_mwh"


def summarize(df: pd.DataFrame) -> str:
    y = df[LABEL].to_numpy()
    p10 = df["p10_eur_mwh"].to_numpy()
    p50 = df["p50_eur_mwh"].to_numpy()
    p90 = df["p90_eur_mwh"].to_numpy()
    avg = (
        pinball_loss(y, p10, 0.1)
        + pinball_loss(y, p50, 0.5)
        + pinball_loss(y, p90, 0.9)
    ) / 3.0
    return (
        f"pinball_avg={avg:.4f} "
        f"coverage={coverage(y, p10, p90):.4f} "
        f"p50_mae={abs(df[LABEL] - df['p50_eur_mwh']).mean():.4f}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/forecast_walkforward_v1_with_weather.parquet"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/forecast_walkforward_v1_with_weather_calibrated.parquet"),
    )
    parser.add_argument(
        "--table-out",
        type=Path,
        default=Path("data/processed/calibration_table_v1_with_weather.parquet"),
    )
    args = parser.parse_args()

    df = pd.read_parquet(args.input)
    table = build_residual_quantile_table(df)
    calibrated = apply_residual_quantile_calibration(df, table)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    calibrated.to_parquet(args.output, index=False)
    table.to_parquet(args.table_out, index=False)
    table.to_csv(args.table_out.with_suffix(".csv"), index=False)

    print(f"[calibrate] raw:        {summarize(df)}")
    print(f"[calibrate] calibrated: {summarize(calibrated)}")
    print(f"[calibrate] wrote {args.output}")
    print(f"[calibrate] wrote {args.table_out}")


if __name__ == "__main__":
    main()

