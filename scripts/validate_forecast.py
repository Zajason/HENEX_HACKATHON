"""Compare forecast for a past date against realized DAM prices."""

import sys
from pathlib import Path
import pandas as pd

from data_pipeline import download_henex_dam, parse_henex_dam

DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-04-28"

# Load forecast
fcst_path = Path(f"data/processed/{DATE}_forecast.csv")
if not fcst_path.exists():
    raise SystemExit(f"Forecast not found: {fcst_path}. Run predict_tomorrow first.")
fcst = pd.read_csv(fcst_path, parse_dates=["timestamp"])

# Download and parse realized DAM prices
dam_path = download_henex_dam(DATE)
dam = parse_henex_dam(dam_path)

# DAM may have multiple rows per timestamp — keep one per timestamp
dam = dam.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")

# Merge
merged = fcst.merge(
    dam[["timestamp", "dam_price_eur_mwh"]], on="timestamp", how="left"
)

merged["error_p50"] = merged["p50_eur_mwh"] - merged["dam_price_eur_mwh"]
merged["abs_error_p50"] = merged["error_p50"].abs()
merged["in_band"] = (
    (merged["dam_price_eur_mwh"] >= merged["p10_eur_mwh"])
    & (merged["dam_price_eur_mwh"] <= merged["p90_eur_mwh"])
)

# Save comparison CSV
out_path = Path(f"data/processed/{DATE}_forecast_vs_realized.csv")
merged.to_csv(out_path, index=False)

# Print summary
valid = merged.dropna(subset=["dam_price_eur_mwh"])
mae = valid["abs_error_p50"].mean()
coverage = valid["in_band"].mean()
realized_mean = valid["dam_price_eur_mwh"].mean()
p50_mean = valid["p50_eur_mwh"].mean()
max_err = valid["abs_error_p50"].max()

print(f"\n=== Forecast Validation: {DATE} ===")
print(f"Intervals matched:    {len(valid)} / {len(merged)}")
print(f"MAE (P50):            {mae:.2f} EUR/MWh")
print(f"Coverage [P10, P90]:  {coverage:.1%}")
print(f"Mean realized price:  {realized_mean:.2f} EUR/MWh")
print(f"Mean P50 forecast:    {p50_mean:.2f} EUR/MWh")
print(f"Bias (P50 - real):    {(p50_mean - realized_mean):.2f} EUR/MWh")
print(f"Max absolute error:   {max_err:.2f} EUR/MWh")
print(f"\nSaved to: {out_path}")
print(f"\nFull comparison ({len(merged)} rows):")
cols = [
    "timestamp",
    "p10_eur_mwh",
    "p50_eur_mwh",
    "p90_eur_mwh",
    "dam_price_eur_mwh",
    "error_p50",
    "in_band",
]
print(merged[cols].to_string(index=False))
