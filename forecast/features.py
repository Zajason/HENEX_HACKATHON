"""Feature engineering for the forecast layer.

Builds the feature matrix consumed by both the Prophet baseline and the
LightGBM-quantile residual model. Single-stage; no two-stage prediction
stacking. Kink features handle the curtailment / scarcity nonlinearity.

Inputs contract (Option B): every feature listed here must be available
*before* DAM gate closure (D-1, ~12:00 EET). Realized values are forbidden.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------
# Calendar
# ----------------------------------------------------------------------

GREEK_BANK_HOLIDAYS_FIXED = {
    (1, 1): "new_year",
    (1, 6): "epiphany",
    (3, 25): "independence_day",
    (5, 1): "labour_day",
    (8, 15): "assumption",
    (10, 28): "ohi_day",
    (12, 25): "christmas",
    (12, 26): "synaxis_theotokos",
}


def _orthodox_easter_date(year: int) -> pd.Timestamp:
    """Meeus / Julian algorithm for the Orthodox Easter date (Gregorian)."""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    julian = pd.Timestamp(year=year, month=month, day=day)
    # Gregorian offset: +13 days for the 21st century
    return julian + pd.Timedelta(days=13)


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    ts = out["timestamp"]
    out["hour"] = ts.dt.hour
    out["minute"] = ts.dt.minute
    out["weekday"] = ts.dt.weekday
    out["is_weekend"] = (out["weekday"] >= 5).astype(int)
    out["month"] = ts.dt.month
    out["dayofyear"] = ts.dt.dayofyear

    # Cyclical hour-of-day (24h period) and time-of-day (96 slots)
    out["hour_sin"] = np.sin(2 * np.pi * out["hour"] / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * out["hour"] / 24.0)
    tod_idx = out["hour"] * 4 + out["minute"] // 15
    out["tod_sin"] = np.sin(2 * np.pi * tod_idx / 96.0)
    out["tod_cos"] = np.cos(2 * np.pi * tod_idx / 96.0)

    out["is_jja_cooling"] = out["month"].isin([6, 7, 8]).astype(int)
    out["is_aug_vacation"] = out["month"].eq(8).astype(int)

    fixed_hol = ts.dt.normalize().apply(
        lambda d: int((d.month, d.day) in GREEK_BANK_HOLIDAYS_FIXED)
    )
    out["is_fixed_holiday"] = fixed_hol

    years = ts.dt.year.unique()
    easter_by_year = {y: _orthodox_easter_date(int(y)) for y in years}
    easter_dates = ts.dt.year.map(easter_by_year)
    days_to_easter = (ts.dt.normalize() - easter_dates).dt.days
    out["is_easter_window"] = days_to_easter.between(-7, 7).astype(int)

    return out


# ----------------------------------------------------------------------
# Residual load + kinks
# ----------------------------------------------------------------------

def add_residual_load(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["residual_load_mw"] = out["load_forecast_mw"] - out["res_forecast_mw"]
    out["res_share"] = out["res_forecast_mw"] / out["load_forecast_mw"].clip(lower=1.0)
    return out


def add_kink_and_ramp_features(
    df: pd.DataFrame, q_low: float = 0.20, q_high: float = 0.80
) -> pd.DataFrame:
    """Add piecewise RL kinks computed against rolling quantiles, plus 4h ramp."""
    out = df.copy()
    rl = out["residual_load_mw"]
    rl_q_low = rl.rolling(window=96 * 30, min_periods=96).quantile(q_low)
    rl_q_high = rl.rolling(window=96 * 30, min_periods=96).quantile(q_high)
    rl_q_low = rl_q_low.bfill().fillna(rl.median())
    rl_q_high = rl_q_high.bfill().fillna(rl.median())

    out["rl_q_low"] = rl_q_low
    out["rl_q_high"] = rl_q_high
    out["rl_low_kink"] = (rl_q_low - rl).clip(lower=0.0)
    out["rl_high_kink"] = (rl - rl_q_high).clip(lower=0.0)

    # 4-hour ramp = current RL - RL 16 quarter-hours ago (or 4 hours back).
    step = 16 if (out["timestamp"].diff().median() <= pd.Timedelta("20min")) else 4
    out["rl_ramp_4h_mw"] = rl - rl.shift(step)
    out["rl_ramp_4h_mw"] = out["rl_ramp_4h_mw"].fillna(0.0)
    return out


# ----------------------------------------------------------------------
# Feature schemas
# ----------------------------------------------------------------------

PROPHET_REGRESSOR_COLS = [
    "load_forecast_mw",
    "res_forecast_mw",
    "residual_load_mw",
    "res_share",
    "ttf_gas_proxy",
    "eua_carbon_proxy",
]

LGBM_FEATURE_COLS = [
    "load_forecast_mw",
    "res_forecast_mw",
    "residual_load_mw",
    "res_share",
    "rl_low_kink",
    "rl_high_kink",
    "rl_ramp_4h_mw",
    "hour",
    "weekday",
    "is_weekend",
    "month",
    "hour_sin",
    "hour_cos",
    "tod_sin",
    "tod_cos",
    "is_jja_cooling",
    "is_aug_vacation",
    "is_fixed_holiday",
    "is_easter_window",
    "ttf_gas_proxy",
    "eua_carbon_proxy",
    "temperature_2m_c",
    "wind_speed_10m",
    "shortwave_radiation",
    "solar_weighted_temperature_2m_c",
    "solar_weighted_wind_speed_10m",
    "solar_weighted_ssrd_wm2",
    "solar_weighted_total_cloud_cover",
    "solar_weighted_total_precipitation_m",
    "wind_weighted_temperature_2m_c",
    "wind_weighted_wind_speed_10m",
    "wind_weighted_ssrd_wm2",
    "wind_weighted_total_cloud_cover",
    "wind_weighted_total_precipitation_m",
    "load_weighted_temperature_2m_c",
    "load_weighted_wind_speed_10m",
    "load_weighted_ssrd_wm2",
    "load_weighted_total_cloud_cover",
    "load_weighted_total_precipitation_m",
]

LABEL_COL = "dam_price_eur_mwh"


def build_feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the full feature pipeline. Caller must already have joined
    forecast-vintage load / RES / weather and macro drivers onto `df`.
    """
    out = df.copy().sort_values("timestamp").reset_index(drop=True)
    out = add_residual_load(out)
    out = add_kink_and_ramp_features(out)
    out = add_calendar_features(out)
    return out


def select_lgbm_features(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in LGBM_FEATURE_COLS if c in df.columns]
    return df[cols].copy()
