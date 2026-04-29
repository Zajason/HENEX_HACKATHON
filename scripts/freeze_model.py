"""
Freeze a trained Tier-0 model + MAD table for shipping.

Runs on the box that has history.parquet (full training data). Produces
artefacts that any other machine can use to predict P10/P50/P90 for a
delivery day without owning the training data:

    models/tier0.pkl              pickled Tier0Model
    models/mad_table.parquet      forecast-error MAD by (hour, weekday)
    models/manifest.json          training range, feature columns,
                                  lightgbm version, git SHA, n_train

Usage:
    python -m scripts.freeze_model
    python -m scripts.freeze_model --variant v1_with_weather
    python -m scripts.freeze_model --history data/processed/history.parquet
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

import pandas as pd

from forecast.features import LABEL_COL
from forecast.tier0 import fit_tier0_model

DEFAULT_HISTORY = Path("data/processed/history.parquet")
DEFAULT_MAD_SOURCES = {
    "v1_with_weather": Path("data/processed/forecast_walkforward_v1_with_weather.parquet"),
    "v0_no_weather": Path("data/processed/forecast_walkforward_v0_no_weather.parquet"),
}
ERA_15MIN_CUTOFF = pd.Timestamp("2025-10-01")


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def lgbm_version() -> str:
    try:
        import lightgbm
        return lightgbm.__version__
    except Exception:
        return "unavailable"


def build_mad_table(walkforward_path: Path, era_15min_only: bool = True) -> pd.DataFrame:
    df = pd.read_parquet(walkforward_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    if era_15min_only:
        df = df[df["timestamp"] >= ERA_15MIN_CUTOFF]
    if df.empty:
        raise SystemExit(f"MAD source {walkforward_path} empty after era filter.")
    df = df.dropna(subset=[LABEL_COL, "p50_eur_mwh"]).copy()
    df["abs_err"] = (df[LABEL_COL] - df["p50_eur_mwh"]).abs()
    df["hour"] = df["timestamp"].dt.hour
    df["weekday"] = df["timestamp"].dt.weekday
    return (
        df.groupby(["hour", "weekday"])
        .agg(
            mad_eur_mwh=("abs_err", "median"),
            n_obs=("abs_err", "size"),
        )
        .reset_index()
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    p.add_argument("--variant", choices=list(DEFAULT_MAD_SOURCES), default="v1_with_weather",
                   help="which walk-forward parquet to compute MAD from")
    p.add_argument("--mad-source", type=Path, default=None,
                   help="override path of the walkforward parquet to compute MAD from")
    p.add_argument("--output-dir", type=Path, default=Path("models"))
    p.add_argument("--era-all", action="store_true",
                   help="compute MAD pooled across all eras (default: 15-min era only)")
    args = p.parse_args()

    if not args.history.exists():
        raise SystemExit(f"history not found at {args.history}. Run Phase A1-A5 first.")

    print(f"[freeze] loading history from {args.history}")
    history = pd.read_parquet(args.history)
    history["timestamp"] = pd.to_datetime(history["timestamp"]).dt.tz_localize(None)
    history = history.dropna(subset=["load_forecast_mw", "res_forecast_mw", LABEL_COL])
    print(f"[freeze] training rows: {len(history):,} | "
          f"{history['timestamp'].min()} -> {history['timestamp'].max()}")

    print("[freeze] fitting Tier0Model on full history (no walk-forward)")
    model = fit_tier0_model(history)
    print(f"[freeze] backend: {model.backend} | "
          f"feature_cols: {len(model.feature_cols)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.output_dir / "tier0.pkl"
    model.save(model_path)
    print(f"[freeze] wrote {model_path}")

    mad_source = args.mad_source or DEFAULT_MAD_SOURCES[args.variant]
    if mad_source.exists():
        mad = build_mad_table(mad_source, era_15min_only=not args.era_all)
        mad_path = args.output_dir / "mad_table.parquet"
        mad.to_parquet(mad_path, index=False)
        mad.to_csv(mad_path.with_suffix(".csv"), index=False)
        print(f"[freeze] wrote {mad_path}  ({len(mad)} cells, "
              f"min n_obs={mad['n_obs'].min()}, "
              f"median MAD={mad['mad_eur_mwh'].median():.2f} EUR/MWh)")
    else:
        print(f"[freeze] WARNING: MAD source {mad_source} missing; skipping mad_table")
        mad_path = None

    manifest = {
        "frozen_at_utc": datetime.utcnow().isoformat() + "Z",
        "git_sha": git_sha(),
        "lightgbm_version": lgbm_version(),
        "model_backend": model.backend,
        "model_class": "Tier0Model",
        "quantiles": list(model.quantiles),
        "feature_cols": list(model.feature_cols),
        "training_rows": int(len(history)),
        "training_start": str(history["timestamp"].min()),
        "training_end": str(history["timestamp"].max()),
        "mad_variant": args.variant,
        "mad_source": str(mad_source) if mad_source.exists() else None,
        "mad_era": "15min" if not args.era_all else "all",
    }
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"[freeze] wrote {manifest_path}")
    print("\n[freeze] done. Commit models/ to ship the trained artefact.")


if __name__ == "__main__":
    main()
