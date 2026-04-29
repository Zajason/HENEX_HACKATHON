"""Run the forecast-to-optimisation path end to end.

Examples:
    python -m scripts.run_forecast_optimisation --forecast-csv data/processed/2026-04-30_forecast.csv
    python -m scripts.run_forecast_optimisation --forecast-csv data/processed/forecast_walkforward_v1_with_weather_calibrated.csv --date 2025-10-05
    python -m scripts.run_forecast_optimisation --date 2026-05-01 --generate-forecast
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

from optimisation.forecast_dispatch import (
    BatteryConfig,
    load_forecast_csv,
    optimize_forecast_dispatch,
)


DEFAULT_OUT_DIR = Path("optimisation") / "results"


def generate_forecast(date: str) -> Path:
    cmd = [sys.executable, "-m", "scripts.predict_tomorrow", "--date", date]
    subprocess.run(cmd, check=True)
    return Path("data") / "processed" / f"{date}_forecast.csv"


def write_metrics(metrics: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([metrics]).to_csv(path, index=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecast-csv", type=Path, default=None)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD; required for multi-day forecast files")
    parser.add_argument(
        "--generate-forecast",
        action="store_true",
        help="Run scripts.predict_tomorrow first, then optimise its output.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--power-mw", type=float, default=75.0)
    parser.add_argument("--energy-mwh", type=float, default=300.0)
    parser.add_argument("--degradation-eur-mwh", type=float, default=10.0)
    parser.add_argument("--risk-lambda", type=float, default=0.35)
    parser.add_argument("--max-cycles", type=float, default=2.0)
    args = parser.parse_args()

    if args.generate_forecast:
        if args.date is None:
            raise SystemExit("--date is required with --generate-forecast")
        forecast_csv = generate_forecast(args.date)
    elif args.forecast_csv is not None:
        forecast_csv = args.forecast_csv
    else:
        raise SystemExit("Provide --forecast-csv or use --generate-forecast --date YYYY-MM-DD")

    forecast = load_forecast_csv(forecast_csv, date=args.date)
    config = BatteryConfig(
        power_mw=args.power_mw,
        energy_mwh=args.energy_mwh,
        degradation_eur_mwh=args.degradation_eur_mwh,
        risk_lambda=args.risk_lambda,
        max_cycles=args.max_cycles,
    )
    schedule, metrics = optimize_forecast_dispatch(forecast, config=config)

    date_label = args.date
    if date_label is None:
        unique_dates = pd.to_datetime(schedule["timestamp"]).dt.date.unique()
        date_label = str(unique_dates[0]) if len(unique_dates) == 1 else "multi_day"

    args.output_dir.mkdir(parents=True, exist_ok=True)
    schedule_path = args.output_dir / f"{date_label}_forecast_dispatch_schedule.csv"
    metrics_path = args.output_dir / f"{date_label}_forecast_dispatch_metrics.csv"
    schedule.to_csv(schedule_path, index=False)
    write_metrics(metrics, metrics_path)

    print("\n=== Forecast -> Optimisation ===")
    print(f"Forecast CSV: {forecast_csv}")
    print(f"Rows: {len(schedule)} | {schedule['timestamp'].min()} -> {schedule['timestamp'].max()}")
    print(f"Schedule: {schedule_path}")
    print(f"Metrics:  {metrics_path}")
    print("\nKey metrics:")
    for key in [
        "profit_eur",
        "revenue_eur",
        "energy_cost_eur",
        "degradation_eur",
        "throughput_mwh",
        "equivalent_cycles",
        "profit_per_mwh_throughput",
        "avg_buy_price_eur_mwh",
        "avg_sell_price_eur_mwh",
        "active_intervals",
        "idle_intervals",
        "objective_risk_adjusted_eur",
    ]:
        value = metrics.get(key)
        if isinstance(value, float):
            print(f"  {key}: {value:,.4f}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
