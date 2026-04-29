"""Day-ahead price forecasting layer.

Architecture (Tier 0, Option B):
  Prophet (trend + seasonality + holidays + exogenous regressors)
    -> baseline yhat per timestamp
  LightGBM-quantile  on  residual = price - prophet_yhat
    at q in {0.1, 0.5, 0.9}, with kink + weather features
    -> conditional quantiles of residual
  Final P_q = prophet_yhat + lgbm_q(residual | features)

Inputs contract (Option B): forecast-vintage features only.
  Realized values reach the model only as the *label* during training.

Public API:
  forecast.io.load_training_history     -> training DataFrame
  forecast.features.build_feature_frame -> features + label
  forecast.pipeline.fit_pipeline        -> trained models
  forecast.pipeline.predict_day         -> P10 / P50 / P90 per 15-min slot
  forecast.metrics.pinball_loss, coverage, mad_per_cell
"""

from forecast.pipeline import fit_pipeline, predict_day, ForecastPipeline
from forecast.tier0 import fit_tier0_model, Tier0Model

__all__ = [
    "fit_pipeline",
    "predict_day",
    "ForecastPipeline",
    "fit_tier0_model",
    "Tier0Model",
]
