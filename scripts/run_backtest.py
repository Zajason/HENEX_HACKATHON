"""Run Phase B rolling-origin forecast backtests.

Examples:
    python -m scripts.run_backtest --model tier0
    python -m scripts.run_backtest --model prophet_lgbm --history data/processed/history.parquet
    python -m scripts.run_backtest --model tier0 --no-weather --out data/processed/tier0_backtest.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from forecast.backtest import load_history_frame, run_walk_forward_backtest
from forecast.pipeline import fit_pipeline
from forecast.tier0 import fit_tier0_model

WEATHER_COLS = {
    "temperature_2m_c",
    "wind_speed_10m",
    "shortwave_radiation",
    "solar_weighted_shortwave_radiation",
    "solar_weighted_temperature_2m",
    "wind_weighted_wind_speed_10m",
    "wind_weighted_wind_speed_100m",
    "load_weighted_temperature_2m",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        choices=["tier0", "prophet_lgbm"],
        default="tier0",
        help="forecast architecture to backtest",
    )
    parser.add_argument(
        "--history",
        type=Path,
        default=Path("data") / "processed" / "history.parquet",
        help="Phase A joined history frame",
    )
    parser.add_argument(
        "--initial-window-days",
        type=int,
        default=365,
        help="training window before first held-out fold",
    )
    parser.add_argument("--step-days", type=int, default=30)
    parser.add_argument("--horizon-days", type=int, default=7)
    parser.add_argument("--min-train-rows", type=int, default=1000)
    parser.add_argument(
        "--no-weather",
        action="store_true",
        help="drop weather columns for the Phase B4 price + IPTO sanity check",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    try:
        df = load_history_frame(args.history)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"{exc}\nPhase A must write the joined history frame first "
            "(expected by default: data/processed/history.parquet)."
        ) from exc
    if args.no_weather:
        df = df.drop(columns=[c for c in WEATHER_COLS if c in df.columns])

    if args.model == "tier0":
        model_factory = fit_tier0_model
    else:
        model_factory = fit_pipeline

    try:
        result = run_walk_forward_backtest(
            df,
            model_factory=model_factory,
            initial_window=pd.Timedelta(days=args.initial_window_days),
            step=pd.Timedelta(days=args.step_days),
            horizon=pd.Timedelta(days=args.horizon_days),
            min_train_rows=args.min_train_rows,
        )
    except ValueError as exc:
        raise SystemExit(f"[BACKTEST] {exc}") from exc

    print("\n[BACKTEST] overall")
    print(result.summary.to_string(index=False))
    print("\n[BACKTEST] by year")
    print(result.by_year.to_string(index=False))
    print("\n[BACKTEST] by hour")
    print(result.by_hour.to_string(index=False))
    if result.by_regime is not None:
        print("\n[BACKTEST] by regime")
        print(result.by_regime.to_string(index=False))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        result.predictions.to_csv(args.out, index=False)
        print(f"\n[BACKTEST] wrote predictions to {args.out}")


if __name__ == "__main__":
    main()
