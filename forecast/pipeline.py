"""Forecast pipeline orchestrator.

Fit:
    1. Build feature frame on training history.
    2. Fit Prophet on (timestamp, price) with exogenous regressors.
    3. Compute residual = price - prophet_yhat on training set.
    4. Fit LightGBM-quantile (q in {0.1, 0.5, 0.9}) on residual.
    5. Fit intra-hour shape table from post-Oct-2025 sample.

Predict:
    For a delivery day D with a feature frame at hourly resolution:
    1. prophet_yhat = ProphetBaseline.predict(features_D)
    2. residual_q   = QuantileResidualModel.predict(features_D)
    3. P_q = prophet_yhat + residual_q  for each q
    4. Disaggregate to 15-min via intra_hour shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from forecast.features import build_feature_frame, LABEL_COL, PROPHET_REGRESSOR_COLS
from forecast.prophet_baseline import fit_prophet_baseline, ProphetBaseline
from forecast.lgbm_quantile import (
    fit_quantile_residual_model,
    QuantileResidualModel,
    DEFAULT_QUANTILES,
)
from forecast.intra_hour import (
    fit_intra_hour_shape,
    apply_intra_hour_shape,
)


@dataclass
class ForecastPipeline:
    prophet: ProphetBaseline
    quantile_residual: QuantileResidualModel
    intra_hour_shape: pd.DataFrame
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES

    def predict_hourly(self, features_df: pd.DataFrame) -> pd.DataFrame:
        feats = build_feature_frame(features_df)
        prophet_yhat = self.prophet.predict(feats)
        residual_pred = self.quantile_residual.predict(feats)
        out = pd.DataFrame({"timestamp": feats["timestamp"]})
        for q in self.quantiles:
            col = f"residual_q{int(q * 100):02d}"
            out[f"p{int(q * 100):02d}_eur_mwh"] = prophet_yhat + residual_pred[col].to_numpy()
        # enforce monotonicity P10 <= P50 <= P90 row-wise
        cols = [f"p{int(q * 100):02d}_eur_mwh" for q in sorted(self.quantiles)]
        out[cols] = np.sort(out[cols].to_numpy(), axis=1)
        return out

    def predict_15min(self, hourly_features_df: pd.DataFrame) -> pd.DataFrame:
        hourly = self.predict_hourly(hourly_features_df)
        return apply_intra_hour_shape(hourly, self.intra_hour_shape)

    # Persistence ------------------------------------------------------

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: Path) -> "ForecastPipeline":
        with open(path, "rb") as f:
            return pickle.load(f)


def fit_pipeline(
    training_df: pd.DataFrame,
    quantiles: tuple[float, ...] = DEFAULT_QUANTILES,
) -> ForecastPipeline:
    """Train the full Prophet + LGBM-quantile pipeline on `training_df`.

    `training_df` must contain `timestamp`, `dam_price_eur_mwh`, and the
    forecast-vintage feature inputs (load_forecast_mw, res_forecast_mw,
    weather columns, optional macro). Rows without a label are dropped.
    """
    feats = build_feature_frame(training_df)
    feats = feats.dropna(subset=[LABEL_COL])

    regressors = [c for c in PROPHET_REGRESSOR_COLS if c in feats.columns]
    prophet = fit_prophet_baseline(feats, regressors=regressors)

    feats["prophet_yhat"] = prophet.predict(feats)
    feats["residual"] = feats[LABEL_COL] - feats["prophet_yhat"]

    qmodel = fit_quantile_residual_model(
        feats, residual_col="residual", quantiles=quantiles
    )

    fifteen = feats[feats["timestamp"] >= pd.Timestamp("2025-10-01")]
    shape = fit_intra_hour_shape(fifteen)

    return ForecastPipeline(
        prophet=prophet,
        quantile_residual=qmodel,
        intra_hour_shape=shape,
        quantiles=tuple(quantiles),
    )


def predict_day(
    pipeline: ForecastPipeline,
    day_features_df: pd.DataFrame,
    resolution: str = "15min",
) -> pd.DataFrame:
    if resolution == "15min":
        return pipeline.predict_15min(day_features_df)
    if resolution == "hourly":
        return pipeline.predict_hourly(day_features_df)
    raise ValueError(f"Unknown resolution: {resolution}")
