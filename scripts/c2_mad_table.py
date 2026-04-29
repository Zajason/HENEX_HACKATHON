"""
C2: Forecast-error MAD table by (hour, weekday).

Consumed by the optimizer's spread filter. Per OPTIMIZER.md the filter reads
    MAD_{hour, weekday} = median_t( |dam_price_eur_mwh_t - p50_eur_mwh_t| )
indexed by (hour, weekday) and uses it to size the lambda_buffer guard
on candidate (charge, discharge) intervals.

Source variant defaults to v1_with_weather (the better model). Falls back
to v0_no_weather if v1 is not yet on disk.

Window defaults to post-2025-10-01 only — that is the era the optimizer
will actually trade in (15-min MTU). A separate hourly-era table can be
written with --era hourly if needed.

Output: data/processed/mad_table.parquet  (also CSV sidecar)
        columns: hour, weekday, mad_eur_mwh, n_obs, variant, era
"""

import sys
sys.path.insert(0, ".")

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

LABEL = "dam_price_eur_mwh"

VARIANTS = {
    "v1_with_weather": Path("data/processed/forecast_walkforward_v1_with_weather.parquet"),
    "v0_no_weather": Path("data/processed/forecast_walkforward_v0_no_weather.parquet"),
}

ERA_CUTOFF = pd.Timestamp("2025-10-01")


def pick_variant(preferred: str | None) -> tuple[str, Path]:
    if preferred:
        path = VARIANTS.get(preferred)
        if path is None:
            raise SystemExit(f"unknown variant '{preferred}'. choices: {list(VARIANTS)}")
        if not path.exists():
            raise SystemExit(f"{preferred} parquet missing at {path}")
        return preferred, path

    for name, path in VARIANTS.items():
        if path.exists():
            return name, path
    raise SystemExit(
        "no walk-forward parquet found. run B4 (and ideally B6) first."
    )


def filter_era(df: pd.DataFrame, era: str) -> pd.DataFrame:
    if era == "all":
        return df
    if era == "15min":
        return df[df["timestamp"] >= ERA_CUTOFF].copy()
    if era == "hourly":
        return df[df["timestamp"] < ERA_CUTOFF].copy()
    raise SystemExit(f"unknown era '{era}'. choices: all, 15min, hourly")


def build_mad_table(predictions: pd.DataFrame) -> pd.DataFrame:
    d = predictions[[LABEL, "p50_eur_mwh", "timestamp"]].dropna().copy()
    d["abs_err"] = (d[LABEL] - d["p50_eur_mwh"]).abs()
    d["hour"] = d["timestamp"].dt.hour
    d["weekday"] = d["timestamp"].dt.weekday

    grouped = (
        d.groupby(["hour", "weekday"])
        .agg(
            mad_eur_mwh=("abs_err", "median"),
            n_obs=("abs_err", "size"),
        )
        .reset_index()
    )
    return grouped


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--variant", choices=list(VARIANTS), default=None,
                   help="which walk-forward parquet to read; default: prefer v1_with_weather")
    p.add_argument("--era", choices=["all", "15min", "hourly"], default="15min",
                   help="time-window filter; default 15min (post-2025-10-01)")
    p.add_argument("--out", type=Path, default=Path("data/processed/mad_table.parquet"))
    args = p.parse_args()

    variant, path = pick_variant(args.variant)
    print(f"[C2] reading {variant} from {path}")
    df = pd.read_parquet(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    print(f"[C2] {len(df):,} prediction rows | "
          f"{df['timestamp'].min()} -> {df['timestamp'].max()}")

    df = filter_era(df, args.era)
    if df.empty:
        raise SystemExit(f"no rows in era '{args.era}'.")
    print(f"[C2] after era filter ({args.era}): {len(df):,} rows")

    table = build_mad_table(df)
    table["variant"] = variant
    table["era"] = args.era

    pooled = float(np.median((df[LABEL] - df["p50_eur_mwh"]).abs()))
    print(f"[C2] pooled MAD across all (hour, weekday): {pooled:.2f} EUR/MWh")
    print(f"[C2] cell range: {table['mad_eur_mwh'].min():.2f} -> "
          f"{table['mad_eur_mwh'].max():.2f} EUR/MWh "
          f"({(table['n_obs'] < 10).sum()} thin cells with n_obs < 10)")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    table.to_parquet(args.out, index=False)
    csv_sidecar = args.out.with_suffix(".csv")
    table.to_csv(csv_sidecar, index=False)
    print(f"[C2] wrote {args.out} ({len(table)} rows)")
    print(f"[C2] wrote {csv_sidecar}")


if __name__ == "__main__":
    main()
