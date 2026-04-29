"""
B4: Walk-forward backtest — price + IPTO features only (no weather).

Produces the baseline pinball-loss number that weather features (B5/B6) must beat.
Output: data/processed/forecast_walkforward_v0_no_weather.parquet
"""

import sys
sys.path.insert(0, ".")

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
import pandas as pd
import numpy as np

from forecast.features import build_feature_frame, LABEL_COL
from forecast.tier0 import fit_tier0_model
from forecast.backtest import run_walk_forward_backtest, load_history_frame

HISTORY_PATH = Path("data/processed/history.parquet")
OUTPUT_PATH = Path("data/processed/forecast_walkforward_v0_no_weather.parquet")


def model_factory(train_df: pd.DataFrame):
    """Factory function for walk-forward: fits a Tier0Model on the training fold."""
    return fit_tier0_model(train_df)


def main():
    print("=" * 60)
    print("B4: Walk-forward backtest (no weather)")
    print("=" * 60)

    # Load history
    df = load_history_frame(HISTORY_PATH)
    print(f"History shape: {df.shape}")
    print(f"Date range: {df['timestamp'].min()} -> {df['timestamp'].max()}")
    print(f"Columns: {list(df.columns)}")

    # Drop weather columns for this baseline run
    weather_cols = [c for c in df.columns if any(
        prefix in c for prefix in [
            "solar_weighted_", "wind_weighted_", "load_weighted_",
            "temperature_2m_c", "wind_speed_10m", "shortwave_radiation",
            "ssrd_wm2",
        ]
    )]
    if weather_cols:
        print(f"\nDropping {len(weather_cols)} weather columns for no-weather baseline:")
        for c in weather_cols:
            print(f"  - {c}")
        df = df.drop(columns=weather_cols)

    # Drop rows with missing IPTO features (needed for residual load)
    pre_drop = len(df)
    df = df.dropna(subset=["load_forecast_mw", "res_forecast_mw", LABEL_COL])
    print(f"\nDropped {pre_drop - len(df)} rows with missing IPTO/price data.")
    print(f"Remaining rows: {len(df)}")

    # Run walk-forward backtest
    # 12-month initial training window, 1-month steps, 1-month horizon
    print("\nStarting walk-forward backtest...")
    print("  Initial window: 365 days")
    print("  Step: 30 days")
    print("  Horizon: 30 days")

    result = run_walk_forward_backtest(
        df=df,
        model_factory=model_factory,
        initial_window=pd.Timedelta(days=365),
        step=pd.Timedelta(days=30),
        horizon=pd.Timedelta(days=30),
        min_train_rows=5000,
    )

    # Print summary
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nOverall summary:")
    print(result.summary.to_string(index=False))

    print(f"\nBy year:")
    print(result.by_year.to_string(index=False))

    print(f"\nTotal predictions: {len(result.predictions)}")

    # Coverage check
    cov = result.summary["coverage_p10_p90"].iloc[0]
    print(f"\nP10-P90 coverage: {cov:.3f} (target ≈ 0.80)")

    # Save predictions
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.predictions.to_parquet(OUTPUT_PATH, index=False)
    print(f"\n✓ Saved predictions -> {OUTPUT_PATH}")

    # Save summary
    summary_path = Path("data/processed/forecast_summary_v0_no_weather.csv")
    result.summary.to_csv(summary_path, index=False)
    print(f"✓ Saved summary -> {summary_path}")


if __name__ == "__main__":
    main()
