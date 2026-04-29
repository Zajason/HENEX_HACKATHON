"""Hourly -> 15-min disaggregation.

The pre-2025-10-01 era is hourly; the post-Oct-2025 era is 15-min. We train
the main model on hourly history (longer span) and disaggregate hourly
predictions to 15-min slots using a multiplicative shape learned from the
post-Oct-2025 sample.

Shape:
    s[h, w, q] = mean_observed_15min_price[h, w, q]
               / mean_observed_hourly_avg_price[h, w]
indexed by (hour-of-day, weekday-bucket, slot-within-hour).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def fit_intra_hour_shape(
    df_15min: pd.DataFrame,
    price_col: str = "dam_price_eur_mwh",
) -> pd.DataFrame:
    """Compute intra-hour multiplicative shape.

    `df_15min` must contain only post-2025-10-01 rows at 15-min resolution
    with a non-null `price_col`.
    """
    if df_15min.empty:
        return _identity_shape()

    d = df_15min.copy()
    d["hour"] = d["timestamp"].dt.hour
    d["weekday_bucket"] = d["timestamp"].dt.weekday.map(
        lambda w: "weekend" if w >= 5 else "weekday"
    )
    d["slot"] = d["timestamp"].dt.minute // 15

    by_slot = d.groupby(["hour", "weekday_bucket", "slot"])[price_col].mean()
    by_hour = d.groupby(["hour", "weekday_bucket"])[price_col].mean()

    by_slot = by_slot.reset_index().rename(columns={price_col: "p_slot"})
    by_hour = by_hour.reset_index().rename(columns={price_col: "p_hour"})

    shape = by_slot.merge(by_hour, on=["hour", "weekday_bucket"])
    shape["multiplier"] = shape["p_slot"] / shape["p_hour"].replace(0.0, np.nan)
    shape["multiplier"] = shape["multiplier"].fillna(1.0)
    return shape[["hour", "weekday_bucket", "slot", "multiplier"]]


def _identity_shape() -> pd.DataFrame:
    rows = []
    for h in range(24):
        for wb in ["weekday", "weekend"]:
            for s in range(4):
                rows.append({"hour": h, "weekday_bucket": wb, "slot": s, "multiplier": 1.0})
    return pd.DataFrame(rows)


def apply_intra_hour_shape(
    hourly_df: pd.DataFrame,
    shape: pd.DataFrame,
    quantile_cols: tuple[str, ...] = ("p10_eur_mwh", "p50_eur_mwh", "p90_eur_mwh"),
) -> pd.DataFrame:
    """Broadcast hourly quantile predictions to 15-min slots via the shape table."""
    expanded = []
    for _, row in hourly_df.iterrows():
        ts = row["timestamp"]
        for slot in range(4):
            new = row.copy()
            new["timestamp"] = ts + pd.Timedelta(minutes=15 * slot)
            new["slot"] = slot
            expanded.append(new)
    expanded_df = pd.DataFrame(expanded).reset_index(drop=True)

    expanded_df["hour"] = expanded_df["timestamp"].dt.hour
    expanded_df["weekday_bucket"] = expanded_df["timestamp"].dt.weekday.map(
        lambda w: "weekend" if w >= 5 else "weekday"
    )
    expanded_df = expanded_df.merge(
        shape, on=["hour", "weekday_bucket", "slot"], how="left"
    )
    expanded_df["multiplier"] = expanded_df["multiplier"].fillna(1.0)

    for q in quantile_cols:
        if q in expanded_df.columns:
            expanded_df[q] = expanded_df[q] * expanded_df["multiplier"]

    return expanded_df.drop(columns=["hour", "weekday_bucket", "slot", "multiplier"])
