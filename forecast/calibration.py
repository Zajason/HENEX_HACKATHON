"""Post-hoc quantile calibration for forecast outputs.

The LightGBM quantile models can rank the central price structure well while
still producing bands that are too narrow. This module calibrates P10/P50/P90
from historical walk-forward residuals, keyed by delivery hour and weekday.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from forecast.features import LABEL_COL

P10 = "p10_eur_mwh"
P50 = "p50_eur_mwh"
P90 = "p90_eur_mwh"


def build_residual_quantile_table(
    predictions: pd.DataFrame,
    group_cols: tuple[str, ...] = ("hour", "weekday"),
    min_obs: int = 20,
) -> pd.DataFrame:
    """Build residual quantiles of actual price minus predicted P50.

    The returned table includes one global fallback row with `hour = -1` and
    `weekday = -1`.
    """
    df = predictions[[LABEL_COL, P50, "timestamp"]].dropna().copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    df["residual"] = df[LABEL_COL] - df[P50]
    df["hour"] = df["timestamp"].dt.hour
    df["weekday"] = df["timestamp"].dt.weekday

    grouped = (
        df.groupby(list(group_cols))["residual"]
        .agg(
            q10=lambda s: float(np.quantile(s, 0.10)),
            q50=lambda s: float(np.quantile(s, 0.50)),
            q90=lambda s: float(np.quantile(s, 0.90)),
            n_obs="size",
        )
        .reset_index()
    )

    global_row = {
        "hour": -1,
        "weekday": -1,
        "q10": float(np.quantile(df["residual"], 0.10)),
        "q50": float(np.quantile(df["residual"], 0.50)),
        "q90": float(np.quantile(df["residual"], 0.90)),
        "n_obs": int(len(df)),
    }
    out = pd.concat([grouped, pd.DataFrame([global_row])], ignore_index=True)
    out["is_thin"] = out["n_obs"] < min_obs
    return out


def apply_residual_quantile_calibration(
    predictions: pd.DataFrame,
    calibration_table: pd.DataFrame,
) -> pd.DataFrame:
    """Replace raw quantile columns using calibrated residual quantiles."""
    out = predictions.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"]).dt.tz_localize(None)
    out["hour"] = out["timestamp"].dt.hour
    out["weekday"] = out["timestamp"].dt.weekday

    cal = calibration_table.copy()
    global_cal = cal[(cal["hour"] == -1) & (cal["weekday"] == -1)]
    if global_cal.empty:
        raise ValueError("calibration_table must contain global fallback row")
    fallback = global_cal.iloc[0]

    out = out.merge(
        cal[["hour", "weekday", "q10", "q50", "q90"]],
        on=["hour", "weekday"],
        how="left",
    )
    for col in ["q10", "q50", "q90"]:
        out[col] = out[col].fillna(float(fallback[col]))

    raw_p50 = out[P50].astype(float)
    out[P10] = raw_p50 + out["q10"]
    # Keep the central forecast from the model. The calibration layer is for
    # uncertainty width; moving P50 improved same-sample MAE but was less stable
    # in time-split checks.
    out[P50] = raw_p50
    out[P90] = raw_p50 + out["q90"]

    cols = [P10, P50, P90]
    out[cols] = np.sort(out[cols].to_numpy(), axis=1)
    return out.drop(columns=["hour", "weekday", "q10", "q50", "q90"])
