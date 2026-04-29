"""LightGBM quantile residual model.

Three independent fits at q in {0.1, 0.5, 0.9}, each predicting
    residual_t = price_t - prophet_yhat_t
conditional on the kink + weather + macro feature matrix from features.py.

Tree splits handle the residual-load kinks natively, so the explicit
rl_low_kink / rl_high_kink terms are belt-and-braces — they survive in case
the LGBM dependency fails and the linear-quantile fallback kicks in.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from forecast.features import LGBM_FEATURE_COLS, select_lgbm_features

DEFAULT_QUANTILES = (0.1, 0.5, 0.9)


@dataclass
class QuantileResidualModel:
    models: dict[float, object]
    feature_cols: list[str]
    backend: str

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        X = df[self.feature_cols]
        out = {}
        for q, m in self.models.items():
            out[f"residual_q{int(q * 100):02d}"] = m.predict(X)
        return pd.DataFrame(out, index=df.index)


def fit_quantile_residual_model(
    df: pd.DataFrame,
    residual_col: str = "residual",
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
) -> QuantileResidualModel:
    """Fit one quantile model per q. LightGBM if available, else sklearn linear."""
    feats = select_lgbm_features(df)
    feature_cols = list(feats.columns)
    y = df[residual_col].astype(float).to_numpy()

    mask = (~feats.isna().any(axis=1)) & (~np.isnan(y))
    feats = feats.loc[mask]
    y = y[mask.to_numpy()]

    try:
        import lightgbm as lgb

        models = {}
        for q in quantiles:
            m = lgb.LGBMRegressor(
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
            m.fit(feats, y)
            models[q] = m
        return QuantileResidualModel(models=models, feature_cols=feature_cols, backend="lightgbm")

    except ImportError:
        from sklearn.linear_model import QuantileRegressor

        models = {}
        for q in quantiles:
            m = QuantileRegressor(quantile=q, alpha=0.001, solver="highs")
            m.fit(feats, y)
            models[q] = m
        return QuantileResidualModel(models=models, feature_cols=feature_cols, backend="sklearn")
