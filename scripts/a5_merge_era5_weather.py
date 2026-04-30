"""
A5: Merge ERA5 weather into history.parquet.

For each ERA5 monthly NetCDF:
  1. era5_points_to_dataframe → per-zone weather at representative points
  2. build_capacity_weighted_weather_dataset → solar/wind/load-weighted aggregates
  3. Concatenate across months
  4. Convert UTC → Europe/Athens (naive)
  5. Convert accumulated ssrd (J/m²) to instantaneous W/m² via diff/3600
  6. Forward-fill hourly weather to 15-min resolution
  7. Left-join into history.parquet
"""

import sys
sys.path.insert(0, ".")

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
import pandas as pd
import numpy as np
from weather_sources import (
    era5_points_to_dataframe,
    build_capacity_weighted_weather_dataset,
    RAW_WEATHER_DIR,
    PROCESSED_WEATHER_DIR,
)

HISTORY_PATH = Path("data/processed/history.parquet")


def process_all_era5_months():
    """Process all ERA5 NetCDF files and build a single weather DataFrame."""
    nc_files = sorted(RAW_WEATHER_DIR.glob("era5_greece_*.nc"))
    print(f"Found {len(nc_files)} ERA5 NetCDF files to process.")

    all_weighted = []

    for i, nc in enumerate(nc_files):
        print(f"  [{i+1}/{len(nc_files)}] Processing {nc.name}...")

        # Step 1: extract per-zone weather
        zone_df = era5_points_to_dataframe(nc)

        # Step 2: build capacity-weighted aggregates
        stem = nc.stem  # e.g. era5_greece_2024_01
        weighted = build_capacity_weighted_weather_dataset(
            zone_df, output_name=f"{stem}_weighted.csv"
        )

        all_weighted.append(weighted)

    # Concatenate all months
    weather = pd.concat(all_weighted, ignore_index=True)
    weather["timestamp"] = pd.to_datetime(weather["timestamp"])

    # Deduplicate (overlapping month boundaries)
    weather = weather.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    print(f"\nCombined weather shape: {weather.shape}")
    print(f"Weather date range: {weather['timestamp'].min()} -> {weather['timestamp'].max()}")
    print(f"Weather columns: {list(weather.columns)}")

    return weather


def convert_ssrd_to_instantaneous(weather: pd.DataFrame) -> pd.DataFrame:
    """Convert accumulated ssrd (J/m²) to instantaneous W/m² via hourly diff."""
    out = weather.copy()

    ssrd_cols = [c for c in out.columns if "surface_solar_radiation_downwards" in c]
    for col in ssrd_cols:
        new_name = col.replace("surface_solar_radiation_downwards", "ssrd_wm2")
        # Diff the accumulated field; divide by 3600s to get W/m²
        out[new_name] = out[col].diff() / 3600.0
        # First value of each day reset: clip negatives (day boundary resets)
        out[new_name] = out[new_name].clip(lower=0.0)
        # Fill the first row NaN
        out[new_name] = out[new_name].fillna(0.0)

    return out


def convert_utc_to_athens(weather: pd.DataFrame) -> pd.DataFrame:
    """Convert UTC timestamps to Europe/Athens naive."""
    out = weather.copy()
    out["timestamp"] = (
        out["timestamp"]
        .dt.tz_localize("UTC")
        .dt.tz_convert("Europe/Athens")
        .dt.tz_localize(None)
    )
    # DST fall-back creates duplicate naive timestamps; keep the first
    out = out.drop_duplicates(subset=["timestamp"], keep="first")
    return out


def forward_fill_to_15min(weather: pd.DataFrame) -> pd.DataFrame:
    """Resample hourly weather to 15-min via forward-fill within each hour."""
    weather = weather.sort_values("timestamp").drop_duplicates(subset=["timestamp"])
    weather = weather.set_index("timestamp").sort_index()

    # Create 15-min index spanning the weather range
    idx_15min = pd.date_range(
        start=weather.index.min(),
        end=weather.index.max(),
        freq="15min",
    )

    # Reindex and forward-fill (hourly value applies to its 4 quarter-hours)
    weather_15min = weather.reindex(idx_15min, method="ffill")
    weather_15min.index.name = "timestamp"
    weather_15min = weather_15min.reset_index()

    return weather_15min


def main():
    print("=" * 60)
    print("A5: Merging ERA5 weather into history.parquet")
    print("=" * 60)

    # Step 1: Process all ERA5 months
    weather = process_all_era5_months()

    # Step 2: Convert accumulated ssrd to instantaneous W/m²
    weather = convert_ssrd_to_instantaneous(weather)

    # Step 3: Convert UTC to Europe/Athens
    weather = convert_utc_to_athens(weather)

    # Step 4: Forward-fill to 15-min resolution
    weather_15min = forward_fill_to_15min(weather)
    print(f"\n15-min weather shape: {weather_15min.shape}")

    # Step 5: Load history and left-join
    print(f"\nLoading {HISTORY_PATH}...")
    history = pd.read_parquet(HISTORY_PATH)
    history["timestamp"] = pd.to_datetime(history["timestamp"])
    print(f"History shape: {history.shape}")
    print(f"History date range: {history['timestamp'].min()} -> {history['timestamp'].max()}")

    # Select the key weather columns for the join
    # We want: temperature, wind speed, and solar radiation under each weighting scheme
    weather_cols = ["timestamp"]
    for col in weather_15min.columns:
        if col == "timestamp":
            continue
        # Include the weighted aggregates and the derived ssrd columns
        if any(prefix in col for prefix in [
            "solar_weighted_", "wind_weighted_", "load_weighted_"
        ]):
            weather_cols.append(col)

    weather_to_join = weather_15min[weather_cols].copy()
    weather_value_cols = [c for c in weather_cols if c != "timestamp"]

    existing_weather_cols = [c for c in weather_value_cols if c in history.columns]
    if existing_weather_cols:
        print(f"\nDropping {len(existing_weather_cols)} existing weather columns before refresh.")
        history = history.drop(columns=existing_weather_cols)

    # Merge
    merged = history.merge(weather_to_join, on="timestamp", how="left")

    # Report coverage
    for col in weather_value_cols[:3]:  # Show first 3 as sample
        non_null = merged[col].notna().sum()
        pct = 100 * non_null / len(merged)
        print(f"  {col}: {non_null}/{len(merged)} non-null ({pct:.1f}%)")

    print(f"\nFinal merged shape: {merged.shape}")
    print(f"Final columns ({len(merged.columns)}): {list(merged.columns)}")

    # Save
    merged.to_parquet(HISTORY_PATH, index=False)
    print(f"\n✓ Saved updated history.parquet -> {HISTORY_PATH}")

    # Also save the full weather dataset for reference
    full_weather_path = Path("data/processed/weather/era5_full_weighted.parquet")
    weather_15min.to_parquet(full_weather_path, index=False)
    print(f"✓ Saved full weather dataset -> {full_weather_path}")


if __name__ == "__main__":
    main()
