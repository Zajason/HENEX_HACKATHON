"""Forecast-quality metrics.

Pinball loss is the primary metric for Tier 0 / Tier 1 comparison.
Coverage and per-cell MAD feed into the spread filter at the optimizer.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, q: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(q * diff, (q - 1.0) * diff)))


def average_pinball_loss(
    y_true: np.ndarray,
    quantile_preds: dict[float, np.ndarray],
) -> float:
    losses = [pinball_loss(y_true, p, q) for q, p in quantile_preds.items()]
    return float(np.mean(losses))


def coverage(y_true: np.ndarray, p_low: np.ndarray, p_high: np.ndarray) -> float:
    return float(np.mean((y_true >= p_low) & (y_true <= p_high)))


def mad_per_cell(
    df: pd.DataFrame,
    price_col: str = "dam_price_eur_mwh",
    p50_col: str = "p50_eur_mwh",
) -> pd.DataFrame:
    """Median absolute deviation of |price - p50| keyed on (hour, weekday)."""
    d = df[[price_col, p50_col, "timestamp"]].dropna().copy()
    d["abs_err"] = (d[price_col] - d[p50_col]).abs()
    d["hour"] = d["timestamp"].dt.hour
    d["weekday"] = d["timestamp"].dt.weekday
    out = (
        d.groupby(["hour", "weekday"])["abs_err"]
        .median()
        .reset_index()
        .rename(columns={"abs_err": "mad_eur_mwh"})
    )
    return out
