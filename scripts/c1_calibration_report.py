"""
C1: Calibration report.

For each walkforward artefact (v0_no_weather, v1_with_weather), compute
pinball loss + coverage sliced by year, month, mtu_resolution, and hour.

Output: data/processed/forecast_calibration_report.csv (long format,
one row per (variant, slice_kind, slice_value)).
"""

import sys
sys.path.insert(0, ".")

from pathlib import Path
import pandas as pd
import numpy as np

from forecast.metrics import pinball_loss, coverage

LABEL = "dam_price_eur_mwh"
HISTORY_PATH = Path("data/processed/history.parquet")

VARIANTS = {
    "v0_no_weather": Path("data/processed/forecast_walkforward_v0_no_weather.parquet"),
    "v1_with_weather": Path("data/processed/forecast_walkforward_v1_with_weather.parquet"),
}


def metrics_row(d: pd.DataFrame) -> dict:
    y = d[LABEL].to_numpy()
    p10 = d["p10_eur_mwh"].to_numpy()
    p50 = d["p50_eur_mwh"].to_numpy()
    p90 = d["p90_eur_mwh"].to_numpy()
    return {
        "rows": len(d),
        "pinball_p10": pinball_loss(y, p10, 0.1),
        "pinball_p50": pinball_loss(y, p50, 0.5),
        "pinball_p90": pinball_loss(y, p90, 0.9),
        "pinball_avg": (pinball_loss(y, p10, 0.1) + pinball_loss(y, p50, 0.5) + pinball_loss(y, p90, 0.9)) / 3.0,
        "coverage_p10_p90": coverage(y, p10, p90),
        "p50_mae": float(np.mean(np.abs(y - p50))),
    }


def slice_metrics(df: pd.DataFrame, kind: str, key) -> dict:
    return {"slice_kind": kind, "slice_value": key, **metrics_row(df)}


def main():
    hist = pd.read_parquet(HISTORY_PATH, columns=["timestamp", "mtu_resolution"])
    hist["timestamp"] = pd.to_datetime(hist["timestamp"]).dt.tz_localize(None)

    rows = []
    for variant, path in VARIANTS.items():
        if not path.exists():
            print(f"skip {variant}: {path} missing")
            continue
        df = pd.read_parquet(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
        df = df.merge(hist, on="timestamp", how="left")
        df = df.dropna(subset=[LABEL, "p10_eur_mwh", "p50_eur_mwh", "p90_eur_mwh"])
        print(f"{variant}: {len(df)} rows")

        rows.append({"variant": variant, **slice_metrics(df, "all", "all")})
        for y, g in df.groupby(df["timestamp"].dt.year):
            rows.append({"variant": variant, **slice_metrics(g, "year", int(y))})
        for m, g in df.groupby(df["timestamp"].dt.month):
            rows.append({"variant": variant, **slice_metrics(g, "month", int(m))})
        for h, g in df.groupby(df["timestamp"].dt.hour):
            rows.append({"variant": variant, **slice_metrics(g, "hour", int(h))})
        if "mtu_resolution" in df.columns:
            for r, g in df.groupby("mtu_resolution"):
                rows.append({"variant": variant, **slice_metrics(g, "mtu_resolution", str(r))})

    out = pd.DataFrame(rows)
    out_path = Path("data/processed/forecast_calibration_report.csv")
    out.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}  ({len(out)} rows)")

    print("\n=== Headline (slice_kind=all) ===")
    print(out[out["slice_kind"] == "all"].to_string(index=False))

    print("\n=== By year ===")
    print(
        out[out["slice_kind"] == "year"]
        .pivot(index="slice_value", columns="variant",
               values=["pinball_avg", "coverage_p10_p90", "p50_mae"])
        .round(2)
    )


if __name__ == "__main__":
    main()
