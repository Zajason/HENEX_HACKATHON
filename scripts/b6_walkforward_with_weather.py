"""
B6: Walk-forward backtest — price + IPTO + ERA5 capacity-weighted weather.

Mirrors B4 but keeps the weighted weather columns. Compare pinball loss
to v0_no_weather to quantify the weather lift.

Output: data/processed/forecast_walkforward_v1_with_weather.parquet
"""

import sys
sys.path.insert(0, ".")

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
import pandas as pd

from forecast.features import LABEL_COL
from forecast.tier0 import fit_tier0_model
from forecast.backtest import run_walk_forward_backtest, load_history_frame

HISTORY_PATH = Path("data/processed/history.parquet")
OUTPUT_PATH = Path("data/processed/forecast_walkforward_v1_with_weather.parquet")


def model_factory(train_df: pd.DataFrame):
    return fit_tier0_model(train_df)


def main():
    print("=" * 60)
    print("B6: Walk-forward backtest (with weather)")
    print("=" * 60)

    df = load_history_frame(HISTORY_PATH)
    print(f"History shape: {df.shape}")
    print(f"Date range: {df['timestamp'].min()} -> {df['timestamp'].max()}")

    weather_cols = [c for c in df.columns if any(
        c.startswith(p) for p in ("solar_weighted_", "wind_weighted_", "load_weighted_")
    )]
    print(f"Weather columns kept ({len(weather_cols)}):")
    for c in weather_cols:
        print(f"  - {c}")

    pre_drop = len(df)
    df = df.dropna(subset=["load_forecast_mw", "res_forecast_mw", LABEL_COL])
    print(f"\nDropped {pre_drop - len(df)} rows missing IPTO/price.")
    print(f"Remaining rows: {len(df)}")

    print("\nStarting walk-forward backtest (365d/30d/30d)...")
    result = run_walk_forward_backtest(
        df=df,
        model_factory=model_factory,
        initial_window=pd.Timedelta(days=365),
        step=pd.Timedelta(days=30),
        horizon=pd.Timedelta(days=30),
        min_train_rows=5000,
    )

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print("\nOverall summary:")
    print(result.summary.to_string(index=False))
    print("\nBy year:")
    print(result.by_year.to_string(index=False))

    cov = result.summary["coverage_p10_p90"].iloc[0]
    print(f"\nP10-P90 coverage: {cov:.3f} (target ~0.80)")
    print(f"Total predictions: {len(result.predictions)}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.predictions.to_parquet(OUTPUT_PATH, index=False)
    print(f"\nSaved predictions -> {OUTPUT_PATH}")

    summary_path = Path("data/processed/forecast_summary_v1_with_weather.csv")
    result.summary.to_csv(summary_path, index=False)
    print(f"Saved summary -> {summary_path}")


if __name__ == "__main__":
    main()
