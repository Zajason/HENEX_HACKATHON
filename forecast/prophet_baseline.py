"""Prophet baseline.

Used as the trend + seasonality + holiday + exogenous-regressor backbone, NOT
as an autoregressive predictor. Prophet's per-component decomposition is
genuinely good at calendar effects in noisy series with limited history; we
let it own that, then hand the residual to LightGBM.

Inputs contract: every regressor passed here must be forecast-vintage
(available before D-1 gate closure). Realized values forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from forecast.features import PROPHET_REGRESSOR_COLS, LABEL_COL


@dataclass
class ProphetBaseline:
    model: object
    regressor_cols: list[str]

    def predict(self, df: pd.DataFrame) -> pd.Series:
        prophet_in = df[["timestamp"] + self.regressor_cols].rename(
            columns={"timestamp": "ds"}
        )
        out = self.model.predict(prophet_in)
        return out["yhat"].to_numpy()


def fit_prophet_baseline(
    df: pd.DataFrame,
    regressors: list[str] | None = None,
    weekly_seasonality: bool = True,
    yearly_seasonality: bool = True,
    daily_seasonality: bool = True,
) -> ProphetBaseline:
    """Fit Prophet on (timestamp, price) with the listed exogenous regressors.

    Greek bank-holiday flags are passed via the `holidays` argument.
    """
    try:
        from prophet import Prophet
    except ImportError as e:
        raise ImportError(
            "prophet is required: `pip install prophet`. "
            "On Windows, see https://facebook.github.io/prophet/docs/installation.html."
        ) from e

    regressors = regressors or [c for c in PROPHET_REGRESSOR_COLS if c in df.columns]

    train = df[["timestamp", LABEL_COL] + regressors].dropna().copy()
    train = train.rename(columns={"timestamp": "ds", LABEL_COL: "y"})

    holidays = _build_greek_holidays(train["ds"])

    m = Prophet(
        weekly_seasonality=weekly_seasonality,
        yearly_seasonality=yearly_seasonality,
        daily_seasonality=daily_seasonality,
        seasonality_mode="additive",
        changepoint_prior_scale=0.05,
        holidays=holidays,
    )
    for col in regressors:
        m.add_regressor(col, standardize=True)

    m.fit(train)
    return ProphetBaseline(model=m, regressor_cols=regressors)


def _build_greek_holidays(timestamps: pd.Series) -> pd.DataFrame:
    """Greek public holidays + Orthodox Easter window for the years observed."""
    from forecast.features import (
        _orthodox_easter_date,
        GREEK_BANK_HOLIDAYS_FIXED,
    )

    years = sorted({int(y) for y in timestamps.dt.year.unique()})
    rows = []
    for y in years:
        for (m, d), name in GREEK_BANK_HOLIDAYS_FIXED.items():
            rows.append({"holiday": name, "ds": pd.Timestamp(year=y, month=m, day=d)})
        easter = _orthodox_easter_date(y)
        rows.append({"holiday": "orthodox_easter", "ds": easter})
        rows.append({"holiday": "easter_monday", "ds": easter + pd.Timedelta(days=1)})
        rows.append({"holiday": "good_friday", "ds": easter - pd.Timedelta(days=2)})
    h = pd.DataFrame(rows)
    h["lower_window"] = -1
    h["upper_window"] = 1
    return h
