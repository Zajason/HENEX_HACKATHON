"""Pure Tier-0 LightGBM quantile price model.

This is the Phase B floor: three independent single-stage quantile models
predicting DAM price directly from forecast-vintage features. Prophet-based
models live in forecast.pipeline and must beat this floor before shipping.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from forecast.features import (
    LABEL_COL,
    build_feature_frame,
    select_lgbm_features,
)
from forecast.calibration import apply_residual_quantile_calibration
from forecast.lgbm_quantile import DEFAULT_QUANTILES


ERA_15MIN_CUTOFF = pd.Timestamp("2025-10-01")


def compute_sample_weights(
    timestamps: pd.Series,
    half_life_days: float = 365.0,
    floor: float = 0.3,
    era_boost: float = 2.0,
) -> np.ndarray:
    """Recency + era-aware sample weights.

    - Exponential decay with half-life ~1y, floored so 2023 rows still inform
      the trees.
    - Multiplicative boost for the 15-min era we'll actually trade in
      (post-2025-10-01), since coverage on that segment is thin and
      its statistics drive the live MAD.
    """
    ts = pd.to_datetime(timestamps).reset_index(drop=True)
    ref = ts.max()
    age_days = (ref - ts).dt.total_seconds() / 86400.0
    decay = np.power(0.5, age_days / float(half_life_days))
    decay = np.clip(decay, floor, 1.0)
    era = np.where(ts >= ERA_15MIN_CUTOFF, era_boost, 1.0)
    return (decay.to_numpy() * era).astype(float)


@dataclass
class Tier0Model:
    models: dict[float, object]
    feature_cols: list[str]
    backend: str
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES
    calibration_table: pd.DataFrame | None = None

    def predict(self, features_df: pd.DataFrame) -> pd.DataFrame:
        feats = build_feature_frame(features_df)
        missing = [c for c in self.feature_cols if c not in feats.columns]
        if missing:
            raise ValueError(f"Prediction frame missing Tier-0 features: {missing}")

        X = feats[self.feature_cols]
        out = pd.DataFrame({"timestamp": feats["timestamp"]})
        for q in self.quantiles:
            out[f"p{int(q * 100):02d}_eur_mwh"] = self.models[q].predict(X)

        cols = [f"p{int(q * 100):02d}_eur_mwh" for q in sorted(self.quantiles)]
        out[cols] = np.sort(out[cols].to_numpy(), axis=1)
        if self.calibration_table is not None:
            out = apply_residual_quantile_calibration(out, self.calibration_table)
        return out.reset_index(drop=True)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path) -> "Tier0Model":
        with open(path, "rb") as f:
            return pickle.load(f)


def fit_tier0_model(
    training_df: pd.DataFrame,
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
    use_sample_weights: bool = True,
) -> Tier0Model:
    """Fit direct quantile price models on the Phase A history frame."""
    feats = build_feature_frame(training_df)
    feats = feats.dropna(subset=[LABEL_COL]).reset_index(drop=True)

    X = select_lgbm_features(feats)
    feature_cols = list(X.columns)
    if not feature_cols:
        raise ValueError("No usable Tier-0 feature columns found.")

    y = feats[LABEL_COL].astype(float).to_numpy()
    ts = feats["timestamp"]
    mask = (~X.isna().any(axis=1)).to_numpy() & (~np.isnan(y))
    X = X.loc[mask]
    y = y[mask]
    ts = ts.loc[mask].reset_index(drop=True)
    if len(X) == 0:
        raise ValueError("No rows remain after dropping missing Tier-0 features.")

    sw = compute_sample_weights(ts) if use_sample_weights else None

    try:
        import lightgbm as lgb

        models = {}
        for q in quantiles:
            model = lgb.LGBMRegressor(
                objective="quantile",
                alpha=q,
                n_estimators=600,
                learning_rate=0.05,
                num_leaves=63,
                min_child_samples=40,
                feature_fraction=0.9,
                bagging_fraction=0.9,
                bagging_freq=5,
                verbose=-1,
            )
            model.fit(X, y, sample_weight=sw)
            models[q] = model
        return Tier0Model(
            models=models,
            feature_cols=feature_cols,
            backend="lightgbm",
            quantiles=tuple(quantiles),
        )

    except ImportError:
        from sklearn.linear_model import QuantileRegressor

        models = {}
        for q in quantiles:
            model = QuantileRegressor(quantile=q, alpha=0.001, solver="highs")
            model.fit(X, y, sample_weight=sw)
            models[q] = model
        return Tier0Model(
            models=models,
            feature_cols=feature_cols,
            backend="sklearn",
            quantiles=tuple(quantiles),
        )
