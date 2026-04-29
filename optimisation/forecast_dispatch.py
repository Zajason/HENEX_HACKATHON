"""Forecast-to-dispatch bridge for the battery optimizer.

This module consumes the forecast layer's P10/P50/P90 CSV and solves a
deterministic, risk-adjusted battery LP with SciPy/HiGHS. It is deliberately
small and dependency-light so the forecast layer can feed optimisation even
when the heavier Pyomo tier scripts are not installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linprog


FORECAST_COLS = {"timestamp", "p10_eur_mwh", "p50_eur_mwh", "p90_eur_mwh"}


@dataclass(frozen=True)
class BatteryConfig:
    power_mw: float = 75.0
    energy_mwh: float = 300.0
    eta_ch: float = 0.95
    eta_dis: float = 0.95
    soc_min_frac: float = 0.10
    soc_max_frac: float = 0.90
    soc_init_frac: float = 0.50
    degradation_eur_mwh: float = 10.0
    max_cycles: float = 2.0
    grid_import_mw: float = 75.0
    grid_export_mw: float = 75.0
    risk_lambda: float = 0.35

    @property
    def soc_min_mwh(self) -> float:
        return self.soc_min_frac * self.energy_mwh

    @property
    def soc_max_mwh(self) -> float:
        return self.soc_max_frac * self.energy_mwh

    @property
    def soc_init_mwh(self) -> float:
        return self.soc_init_frac * self.energy_mwh


def load_forecast_csv(path: str | Path, date: str | None = None) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Forecast CSV not found: {path}")

    df = pd.read_csv(path, parse_dates=["timestamp"])
    missing = FORECAST_COLS - set(df.columns)
    if missing:
        raise ValueError(f"Forecast CSV missing required columns: {sorted(missing)}")

    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if date is not None:
        target = pd.Timestamp(date).date()
        df = df[df["timestamp"].dt.date == target].reset_index(drop=True)
        if df.empty:
            raise ValueError(f"No forecast rows found for date {date} in {path}")

    return df


def infer_dt_hours(df: pd.DataFrame) -> float:
    if len(df) < 2:
        raise ValueError("Need at least two forecast rows to infer dispatch interval.")
    diffs = df["timestamp"].diff().dropna().dt.total_seconds() / 3600.0
    dt = float(diffs.median())
    if dt <= 0:
        raise ValueError("Could not infer a positive dispatch interval.")
    return dt


def optimize_forecast_dispatch(
    forecast: pd.DataFrame,
    config: BatteryConfig = BatteryConfig(),
) -> tuple[pd.DataFrame, dict[str, float | str | int]]:
    """Solve a daily risk-adjusted battery dispatch LP.

    Risk adjustment is asymmetric:
    - discharge revenue uses p50 - lambda * uncertainty
    - charge cost uses p50 + lambda * uncertainty

    This turns the forecast band into a spread safety buffer while preserving a
    linear objective.
    """
    df = forecast.copy().sort_values("timestamp").reset_index(drop=True)
    dt = infer_dt_hours(df)
    n = len(df)

    p50 = df["p50_eur_mwh"].astype(float).to_numpy()
    uncertainty = 0.5 * (
        df["p90_eur_mwh"].astype(float).to_numpy()
        - df["p10_eur_mwh"].astype(float).to_numpy()
    )
    uncertainty = np.maximum(uncertainty, 0.0)

    charge_price = p50 + config.risk_lambda * uncertainty
    discharge_price = p50 - config.risk_lambda * uncertainty

    n_vars = 3 * n
    ch = np.arange(0, n)
    dis = np.arange(n, 2 * n)
    soc = np.arange(2 * n, 3 * n)

    c = np.zeros(n_vars)
    c[ch] = dt * (charge_price + config.degradation_eur_mwh)
    c[dis] = -dt * (discharge_price - config.degradation_eur_mwh)

    a_eq = []
    b_eq = []
    for t in range(n):
        row = np.zeros(n_vars)
        row[soc[t]] = 1.0
        row[ch[t]] = -config.eta_ch * dt
        row[dis[t]] = dt / config.eta_dis
        if t > 0:
            row[soc[t - 1]] = -1.0
            rhs = 0.0
        else:
            rhs = config.soc_init_mwh
        a_eq.append(row)
        b_eq.append(rhs)

    terminal = np.zeros(n_vars)
    terminal[soc[-1]] = 1.0
    a_eq.append(terminal)
    b_eq.append(config.soc_init_mwh)

    a_ub = []
    b_ub = []
    discharge_energy = np.zeros(n_vars)
    discharge_energy[dis] = dt
    a_ub.append(discharge_energy)
    b_ub.append(config.max_cycles * config.energy_mwh)

    bounds = []
    charge_max = min(config.power_mw, config.grid_import_mw)
    discharge_max = min(config.power_mw, config.grid_export_mw)
    bounds.extend((0.0, charge_max) for _ in range(n))
    bounds.extend((0.0, discharge_max) for _ in range(n))
    bounds.extend((config.soc_min_mwh, config.soc_max_mwh) for _ in range(n))

    result = linprog(
        c,
        A_ub=np.vstack(a_ub),
        b_ub=np.array(b_ub),
        A_eq=np.vstack(a_eq),
        b_eq=np.array(b_eq),
        bounds=bounds,
        method="highs",
    )
    if not result.success:
        raise RuntimeError(f"Dispatch LP failed: {result.message}")

    x = result.x
    schedule = df.copy()
    schedule["charge_mw"] = x[ch]
    schedule["discharge_mw"] = x[dis]
    schedule["soc_mwh"] = x[soc]
    schedule["net_power_mw"] = schedule["discharge_mw"] - schedule["charge_mw"]
    schedule["uncertainty_eur_mwh"] = uncertainty
    schedule["charge_price_eff_eur_mwh"] = charge_price
    schedule["discharge_price_eff_eur_mwh"] = discharge_price
    schedule["decision"] = "idle"
    schedule.loc[schedule["charge_mw"] > 1e-6, "decision"] = "charge"
    schedule.loc[schedule["discharge_mw"] > 1e-6, "decision"] = "discharge"

    metrics = evaluate_schedule(schedule, dt=dt, config=config)
    metrics.update(
        {
            "solver_status": result.message,
            "objective_risk_adjusted_eur": float(-result.fun),
            "interval_hours": dt,
            "intervals": n,
        }
    )
    return schedule, metrics


def evaluate_schedule(
    schedule: pd.DataFrame,
    dt: float,
    config: BatteryConfig = BatteryConfig(),
    price_col: str = "p50_eur_mwh",
) -> dict[str, float | str | int]:
    charge = schedule["charge_mw"].astype(float)
    discharge = schedule["discharge_mw"].astype(float)
    if price_col not in schedule.columns:
        raise ValueError(f"Schedule missing price column for evaluation: {price_col}")
    prices = schedule[price_col].astype(float)

    energy_bought = float(charge.sum() * dt)
    energy_sold = float(discharge.sum() * dt)
    throughput = energy_bought + energy_sold
    cost = float((charge * prices * dt).sum())
    revenue = float((discharge * prices * dt).sum())
    degradation = float(throughput * config.degradation_eur_mwh)
    profit = revenue - cost - degradation

    daily_pnl = _daily_pnl(schedule, dt=dt, config=config, price_col=price_col)
    downside = daily_pnl[daily_pnl < 0.0]
    pnl_std = float(daily_pnl.std(ddof=0)) if len(daily_pnl) else 0.0
    downside_std = float(downside.std(ddof=0)) if len(downside) else 0.0

    return {
        "profit_eur": float(profit),
        "revenue_eur": revenue,
        "energy_cost_eur": cost,
        "degradation_eur": degradation,
        "energy_bought_mwh": energy_bought,
        "energy_sold_mwh": energy_sold,
        "throughput_mwh": throughput,
        "equivalent_cycles": energy_sold / config.energy_mwh,
        "profit_per_mwh_throughput": profit / throughput if throughput > 1e-9 else 0.0,
        "avg_buy_price_eur_mwh": cost / energy_bought if energy_bought > 1e-9 else np.nan,
        "avg_sell_price_eur_mwh": revenue / energy_sold if energy_sold > 1e-9 else np.nan,
        "active_intervals": int(((charge > 1e-6) | (discharge > 1e-6)).sum()),
        "idle_intervals": int(((charge <= 1e-6) & (discharge <= 1e-6)).sum()),
        "min_soc_mwh": float(schedule["soc_mwh"].min()),
        "max_soc_mwh": float(schedule["soc_mwh"].max()),
        "daily_sharpe": daily_pnl.mean() / pnl_std if pnl_std > 1e-9 else np.nan,
        "daily_sortino": daily_pnl.mean() / downside_std if downside_std > 1e-9 else np.nan,
        "daily_pnl_observations": int(len(daily_pnl)),
        "evaluation_price_col": price_col,
    }


def _daily_pnl(
    schedule: pd.DataFrame,
    dt: float,
    config: BatteryConfig,
    price_col: str = "p50_eur_mwh",
) -> pd.Series:
    tmp = schedule.copy()
    tmp["date"] = pd.to_datetime(tmp["timestamp"]).dt.date
    tmp["interval_pnl_eur"] = (
        tmp[price_col] * (tmp["discharge_mw"] - tmp["charge_mw"]) * dt
        - config.degradation_eur_mwh * (tmp["charge_mw"] + tmp["discharge_mw"]) * dt
    )
    return tmp.groupby("date")["interval_pnl_eur"].sum()
