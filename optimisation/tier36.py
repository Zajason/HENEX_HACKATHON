#Tier 3.6 — Greek-Structural DAM + Intraday MPC

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pyomo.environ import *


# ============================================================
# CONFIG
# ============================================================

DAM_FILE = "synthetic_forecast_day.csv"
INTRADAY_FILE = "synthetic_intraday_curve_from_dam.csv"

OUTPUT_SCHEDULE = "tier7_greek_structural_intraday_schedule.csv"
OUTPUT_SUMMARY = "tier7_greek_structural_intraday_summary.csv"
OUTPUT_PLOT = "tier7_greek_structural_intraday_plot.png"


# ============================================================
# BATTERY CONFIG
# ============================================================

class Battery:
    P_nom = 75.0
    E_nom = 300.0
    dt = 0.25

    eta_ch = 0.95
    eta_dis = 0.95

    SOC_min = 0.10 * E_nom
    SOC_max = 0.90 * E_nom
    E_init = 0.50 * E_nom

    c_deg = 10.0

    max_cycles = 2.0
    grid_import_max = 75.0
    grid_export_max = 75.0


class Risk:
    alpha = 0.10
    risk_aversion = 0.50
    n_scenarios = 200
    seed = 42


class Tier3:
    export_capacity_share = 0.35
    scarcity_spike_multiplier = 1.60
    curtailment_downside_multiplier = 1.20
    structural_penalty = 0.25


class MPC:
    horizon_steps = 96
    enforce_end_of_day_soc = True
    use_remaining_throughput_limit = True


# ============================================================
# HELPERS
# ============================================================

def normalize(s):
    s = pd.Series(s).astype(float)
    return (s - s.min()) / (s.max() - s.min() + 1e-9)


# ============================================================
# DATA LOADING
# ============================================================

def detect_intraday_price_column(df):
    candidates = [
        "intraday_p50_eur_mwh",
        "intraday_price_eur_mwh",
        "id_price_eur_mwh",
        "price_intraday_eur_mwh",
    ]

    for col in candidates:
        if col in df.columns:
            return col

    raise ValueError(
        "Could not find intraday price column. Expected one of: "
        f"{candidates}. Found: {list(df.columns)}"
    )


def load_dam_and_intraday(
    dam_path=DAM_FILE,
    intraday_path=INTRADAY_FILE,
):
    dam = pd.read_csv(dam_path, parse_dates=["timestamp"])
    intraday = pd.read_csv(intraday_path, parse_dates=["timestamp"])

    dam = dam.sort_values("timestamp").reset_index(drop=True)
    intraday = intraday.sort_values("timestamp").reset_index(drop=True)

    if "p50_eur_mwh" not in dam.columns:
        raise ValueError("DAM file must contain p50_eur_mwh")

    if "hour" not in dam.columns:
        dam["hour"] = dam["timestamp"].dt.hour + dam["timestamp"].dt.minute / 60

    id_price_col = detect_intraday_price_column(intraday)

    df = dam[["timestamp", "hour", "p50_eur_mwh"]].copy()
    df = df.rename(columns={"p50_eur_mwh": "dam_price_eur_mwh"})

    intraday_small = intraday[["timestamp", id_price_col]].copy()
    intraday_small = intraday_small.rename(
        columns={id_price_col: "intraday_price_eur_mwh"}
    )

    df = df.merge(intraday_small, on="timestamp", how="left")

    if df["intraday_price_eur_mwh"].isna().any():
        raise ValueError("DAM and intraday timestamps do not fully match.")

    df["dt_hours"] = Battery.dt

    return df


def load_tier3_forecast(path=DAM_FILE):
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    required = {"timestamp", "p10_eur_mwh", "p50_eur_mwh", "p90_eur_mwh"}
    missing = required - set(df.columns)

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df["hour"] = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60
    df["uncertainty"] = (df["p90_eur_mwh"] - df["p10_eur_mwh"]) / 2

    df = add_structural_features(df)

    return df


# ============================================================
# TIER 3 STRUCTURAL FEATURES
# ============================================================

def add_structural_features(df):
    hours = df["hour"].to_numpy()

    if "load_forecast_mw" not in df.columns:
        base_load = (
            5200
            + 600 * np.exp(-((hours - 9) ** 2) / 8)
            + 1100 * np.exp(-((hours - 20) ** 2) / 10)
            + np.random.default_rng(1).normal(0, 80, len(df))
        )
        df["load_forecast_mw"] = base_load

    if "solar_forecast_mw" not in df.columns:
        solar = 2600 * np.exp(-((hours - 13) ** 2) / 10)
        solar[(hours < 6) | (hours > 20)] = 0
        df["solar_forecast_mw"] = solar

    if "wind_forecast_mw" not in df.columns:
        wind = (
            1000
            + 300 * np.sin((hours - 2) * np.pi / 12)
            + np.random.default_rng(2).normal(0, 80, len(df))
        )
        df["wind_forecast_mw"] = np.clip(wind, 200, None)

    if "res_forecast_mw" not in df.columns:
        df["res_forecast_mw"] = df["solar_forecast_mw"] + df["wind_forecast_mw"]

    df["residual_load_mw"] = df["load_forecast_mw"] - df["res_forecast_mw"]
    df["res_share"] = df["res_forecast_mw"] / df["load_forecast_mw"]

    df["duck_curve_pressure"] = (
        df["solar_forecast_mw"] - 0.45 * df["load_forecast_mw"]
    )

    steps_4h = int(4 / Battery.dt)

    df["evening_ramp_mw"] = (
        df["residual_load_mw"] - df["residual_load_mw"].shift(steps_4h)
    )
    df["evening_ramp_mw"] = df["evening_ramp_mw"].fillna(0)

    df["curtailment_proxy"] = np.maximum(
        0,
        df["res_share"] - Tier3.export_capacity_share,
    )

    df["scarcity_pressure"] = (
        normalize(df["residual_load_mw"])
        + normalize(np.maximum(df["evening_ramp_mw"], 0))
    ) / 2

    df["surplus_pressure"] = normalize(df["curtailment_proxy"])

    df["structural_risk_pressure"] = (
        0.45 * normalize(df["p50_eur_mwh"])
        + 0.30 * normalize(df["uncertainty"])
        + 0.25 * df["scarcity_pressure"]
    )

    df["structural_risk_pressure_norm"] = normalize(df["structural_risk_pressure"])

    # Compatibility with old Tier 3 plotting/logic
    df["market_tightness"] = df["structural_risk_pressure"]
    df["market_tightness_norm"] = df["structural_risk_pressure_norm"]

    return df


# ============================================================
# TIER 3 SCENARIO GENERATION
# ============================================================

def generate_tier3_scenarios(df, n_scenarios=200, seed=42):
    rng = np.random.default_rng(seed)

    p10 = df["p10_eur_mwh"].to_numpy()
    p50 = df["p50_eur_mwh"].to_numpy()
    p90 = df["p90_eur_mwh"].to_numpy()

    scarcity = df["scarcity_pressure"].to_numpy()
    surplus = df["surplus_pressure"].to_numpy()
    risk_pressure = df["structural_risk_pressure_norm"].to_numpy()

    sigma_low = (p50 - p10) / 1.2816
    sigma_high = (p90 - p50) / 1.2816
    sigma = np.maximum((sigma_low + sigma_high) / 2, 1e-6)

    sigma = sigma * (1 + 1.1 * risk_pressure + 0.7 * scarcity + 0.5 * surplus)

    scenarios = []

    for _ in range(n_scenarios):
        noise = rng.normal(0, sigma)

        for t in range(1, len(noise)):
            noise[t] = 0.65 * noise[t - 1] + 0.35 * noise[t]

        spike_prob = 0.02 + 0.18 * scarcity + 0.10 * risk_pressure
        spike_event = rng.binomial(1, np.clip(spike_prob, 0, 0.5))

        spike_size = (
            rng.gamma(shape=2.2, scale=14.0, size=len(df))
            * scarcity
            * spike_event
            * Tier3.scarcity_spike_multiplier
        )

        drop_prob = 0.02 + 0.20 * surplus
        drop_event = rng.binomial(1, np.clip(drop_prob, 0, 0.5))

        drop_size = (
            rng.gamma(shape=2.0, scale=10.0, size=len(df))
            * surplus
            * drop_event
            * Tier3.curtailment_downside_multiplier
        )

        scenario = p50 + noise + spike_size - drop_size
        scenario = np.clip(scenario, -80, 600)

        scenarios.append(scenario)

    return np.array(scenarios)


# ============================================================
# TIER 3 DAM CVaR OPTIMIZER
# ============================================================

def optimize_tier3_dam(df, scenarios):
    S, T_len = scenarios.shape
    T = range(T_len)
    K = range(S)

    model = ConcreteModel()

    model.P_ch = Var(T, domain=NonNegativeReals)
    model.P_dis = Var(T, domain=NonNegativeReals)
    model.E = Var(T, domain=NonNegativeReals)

    model.u_ch = Var(T, domain=Binary)
    model.u_dis = Var(T, domain=Binary)

    model.profit = Var(K, domain=Reals)
    model.var_loss = Var(domain=Reals)
    model.excess_loss = Var(K, domain=NonNegativeReals)

    scarcity = df["scarcity_pressure"].to_numpy()
    risk_pressure = df["structural_risk_pressure_norm"].to_numpy()

    structural_charge_penalty = Tier3.structural_penalty * (
        scarcity + risk_pressure
    )

    def scenario_profit_rule(m, k):
        return m.profit[k] == sum(
            scenarios[k, t] * (m.P_dis[t] - m.P_ch[t]) * Battery.dt
            - Battery.c_deg * (m.P_ch[t] + m.P_dis[t]) * Battery.dt
            - structural_charge_penalty[t] * m.P_ch[t] * Battery.dt
            for t in T
        )

    model.scenario_profit = Constraint(K, rule=scenario_profit_rule)

    def cvar_excess_rule(m, k):
        return m.excess_loss[k] >= -m.profit[k] - m.var_loss

    model.cvar_excess = Constraint(K, rule=cvar_excess_rule)

    expected_profit = sum(model.profit[k] for k in K) / S

    cvar_loss = (
        model.var_loss
        + (1 / (Risk.alpha * S)) * sum(model.excess_loss[k] for k in K)
    )

    model.obj = Objective(
        expr=expected_profit - Risk.risk_aversion * cvar_loss,
        sense=maximize,
    )

    model.charge_limit = Constraint(
        T,
        rule=lambda m, t: m.P_ch[t] <= Battery.P_nom * m.u_ch[t],
    )

    model.discharge_limit = Constraint(
        T,
        rule=lambda m, t: m.P_dis[t] <= Battery.P_nom * m.u_dis[t],
    )

    model.no_simultaneous = Constraint(
        T,
        rule=lambda m, t: m.u_ch[t] + m.u_dis[t] <= 1,
    )

    def soc_rule(m, t):
        if t == 0:
            return m.E[t] == (
                Battery.E_init
                + Battery.eta_ch * m.P_ch[t] * Battery.dt
                - (m.P_dis[t] / Battery.eta_dis) * Battery.dt
            )

        return m.E[t] == (
            m.E[t - 1]
            + Battery.eta_ch * m.P_ch[t] * Battery.dt
            - (m.P_dis[t] / Battery.eta_dis) * Battery.dt
        )

    model.soc = Constraint(T, rule=soc_rule)

    model.soc_min = Constraint(T, rule=lambda m, t: m.E[t] >= Battery.SOC_min)
    model.soc_max = Constraint(T, rule=lambda m, t: m.E[t] <= Battery.SOC_max)

    model.final_soc = Constraint(expr=model.E[T_len - 1] == Battery.E_init)

    model.cycle_limit = Constraint(
        expr=sum(model.P_dis[t] * Battery.dt for t in T)
        <= Battery.max_cycles * Battery.E_nom
    )

    model.grid_import = Constraint(
        T,
        rule=lambda m, t: m.P_ch[t] <= Battery.grid_import_max,
    )

    model.grid_export = Constraint(
        T,
        rule=lambda m, t: m.P_dis[t] <= Battery.grid_export_max,
    )

    solver = SolverFactory("glpk")
    result = solver.solve(model, tee=False)

    if (
        result.solver.status != SolverStatus.ok
        or result.solver.termination_condition != TerminationCondition.optimal
    ):
        raise RuntimeError(result)

    out = df.copy()
    out["charge_mw"] = [value(model.P_ch[t]) for t in T]
    out["discharge_mw"] = [value(model.P_dis[t]) for t in T]
    out["soc_mwh"] = [value(model.E[t]) for t in T]
    out["net_power_mw"] = out["discharge_mw"] - out["charge_mw"]

    scenario_profits = np.array([value(model.profit[k]) for k in K])

    return out, scenario_profits


# ============================================================
# GENERIC BESS MILP FOR MPC
# ============================================================

def solve_bess_milp(
    prices,
    current_soc,
    terminal_soc=None,
    throughput_limit=None,
    solver_name="glpk",
):
    prices = np.asarray(prices, dtype=float)
    T_len = len(prices)
    T = range(T_len)

    if T_len == 0:
        raise ValueError("Empty MILP horizon.")

    m = ConcreteModel()

    m.P_ch = Var(T, domain=NonNegativeReals)
    m.P_dis = Var(T, domain=NonNegativeReals)
    m.E = Var(T, domain=NonNegativeReals)

    m.u_ch = Var(T, domain=Binary)
    m.u_dis = Var(T, domain=Binary)

    m.obj = Objective(
        expr=sum(
            prices[t] * (m.P_dis[t] - m.P_ch[t]) * Battery.dt
            - Battery.c_deg * (m.P_ch[t] + m.P_dis[t]) * Battery.dt
            for t in T
        ),
        sense=maximize,
    )

    m.charge_limit = Constraint(
        T,
        rule=lambda model, t: model.P_ch[t]
        <= min(Battery.P_nom, Battery.grid_import_max) * model.u_ch[t],
    )

    m.discharge_limit = Constraint(
        T,
        rule=lambda model, t: model.P_dis[t]
        <= min(Battery.P_nom, Battery.grid_export_max) * model.u_dis[t],
    )

    m.no_simultaneous = Constraint(
        T,
        rule=lambda model, t: model.u_ch[t] + model.u_dis[t] <= 1,
    )

    def soc_rule(model, t):
        if t == 0:
            return model.E[t] == (
                current_soc
                + Battery.eta_ch * model.P_ch[t] * Battery.dt
                - (model.P_dis[t] / Battery.eta_dis) * Battery.dt
            )

        return model.E[t] == (
            model.E[t - 1]
            + Battery.eta_ch * model.P_ch[t] * Battery.dt
            - (model.P_dis[t] / Battery.eta_dis) * Battery.dt
        )

    m.soc = Constraint(T, rule=soc_rule)

    m.soc_min = Constraint(T, rule=lambda model, t: model.E[t] >= Battery.SOC_min)
    m.soc_max = Constraint(T, rule=lambda model, t: model.E[t] <= Battery.SOC_max)

    if terminal_soc is not None:
        m.final_soc = Constraint(expr=m.E[T_len - 1] == terminal_soc)

    if throughput_limit is not None:
        m.throughput_limit = Constraint(
            expr=sum((m.P_ch[t] + m.P_dis[t]) * Battery.dt for t in T)
            <= throughput_limit
        )

    solver = SolverFactory(solver_name)
    result = solver.solve(m, tee=False)

    if (
        result.solver.status != SolverStatus.ok
        or result.solver.termination_condition != TerminationCondition.optimal
    ):
        raise RuntimeError(
            f"MILP failed: status={result.solver.status}, "
            f"termination={result.solver.termination_condition}"
        )

    charge = np.array([value(m.P_ch[t]) for t in T])
    discharge = np.array([value(m.P_dis[t]) for t in T])
    soc = np.array([value(m.E[t]) for t in T])

    profit = np.array([
        prices[t] * (discharge[t] - charge[t]) * Battery.dt
        - Battery.c_deg * (charge[t] + discharge[t]) * Battery.dt
        for t in T
    ])

    return {
        "charge_mw": charge,
        "discharge_mw": discharge,
        "soc_mwh": soc,
        "net_power_mw": discharge - charge,
        "profit_eur": profit,
        "objective_eur": profit.sum(),
        "throughput_mwh": ((charge + discharge) * Battery.dt).sum(),
    }


# ============================================================
# STAGE 1 — TIER 3 DAM SCHEDULE
# ============================================================

def run_tier3_dam_schedule(base_df, dam_file=DAM_FILE):
    print("Running Stage 1: Tier 3 Greek-structural stochastic DAM optimizer...")

    forecast_df = load_tier3_forecast(dam_file)

    assert len(base_df) == len(forecast_df), "DAM base and Tier 3 forecast length mismatch."
    assert all(
        base_df["timestamp"].reset_index(drop=True)
        == forecast_df["timestamp"].reset_index(drop=True)
    ), "DAM base and Tier 3 forecast timestamps do not match."

    scenarios = generate_tier3_scenarios(
        forecast_df,
        n_scenarios=Risk.n_scenarios,
        seed=Risk.seed,
    )

    tier3_schedule, tier3_profits = optimize_tier3_dam(forecast_df, scenarios)

    out = base_df.copy()

    out["dam_charge_mw"] = tier3_schedule["charge_mw"]
    out["dam_discharge_mw"] = tier3_schedule["discharge_mw"]
    out["dam_net_mw"] = tier3_schedule["net_power_mw"]
    out["dam_soc_mwh"] = tier3_schedule["soc_mwh"]

    out["dam_profit_eur"] = (
        out["dam_price_eur_mwh"] * out["dam_net_mw"] * Battery.dt
        - Battery.c_deg
        * (out["dam_charge_mw"] + out["dam_discharge_mw"])
        * Battery.dt
    )

    out["tier3_expected_dam_profit_eur"] = tier3_profits.mean()
    out["tier3_cvar_10_dam_profit_eur"] = tier3_profits[
        tier3_profits <= np.quantile(tier3_profits, Risk.alpha)
    ].mean()

    return out


# ============================================================
# STAGE 2 — INTRADAY MPC
# ============================================================

def run_intraday_mpc(df):
    T_total = len(df)
    prices_all = df["intraday_price_eur_mwh"].to_numpy(dtype=float)

    soc_current = Battery.E_init
    throughput_used = 0.0
    daily_throughput_limit = 2 * Battery.max_cycles * Battery.E_nom

    rows = []

    for k in range(T_total):
        horizon_end = min(k + MPC.horizon_steps, T_total)
        prices_h = prices_all[k:horizon_end]

        terminal_soc = None
        if MPC.enforce_end_of_day_soc and horizon_end == T_total:
            terminal_soc = Battery.E_init

        throughput_remaining = None
        if MPC.use_remaining_throughput_limit:
            throughput_remaining = max(0.0, daily_throughput_limit - throughput_used)

        sol = solve_bess_milp(
            prices=prices_h,
            current_soc=soc_current,
            terminal_soc=terminal_soc,
            throughput_limit=throughput_remaining,
        )

        charge_now = float(sol["charge_mw"][0])
        discharge_now = float(sol["discharge_mw"][0])

        if abs(charge_now) < 1e-7:
            charge_now = 0.0
        if abs(discharge_now) < 1e-7:
            discharge_now = 0.0

        soc_next = (
            soc_current
            + Battery.eta_ch * charge_now * Battery.dt
            - (discharge_now / Battery.eta_dis) * Battery.dt
        )

        throughput_now = (charge_now + discharge_now) * Battery.dt
        throughput_used += throughput_now

        rows.append({
            "mpc_charge_mw": charge_now,
            "mpc_discharge_mw": discharge_now,
            "mpc_net_mw": discharge_now - charge_now,
            "mpc_soc_start_mwh": soc_current,
            "mpc_soc_mwh": soc_next,
            "mpc_throughput_mwh": throughput_now,
            "mpc_remaining_throughput_mwh": max(
                0.0,
                daily_throughput_limit - throughput_used,
            ),
        })

        soc_current = soc_next

    mpc = pd.DataFrame(rows)
    out = pd.concat([df.reset_index(drop=True), mpc], axis=1)

    return out


# ============================================================
# MARKET ACCOUNTING
# ============================================================

def add_market_accounting(df):
    out = df.copy()

    out["id_adjustment_mw"] = out["mpc_net_mw"] - out["dam_net_mw"]

    out["dam_market_revenue_eur"] = (
        out["dam_price_eur_mwh"] * out["dam_net_mw"] * Battery.dt
    )

    out["intraday_adjustment_revenue_eur"] = (
        out["intraday_price_eur_mwh"] * out["id_adjustment_mw"] * Battery.dt
    )

    out["mpc_degradation_cost_eur"] = (
        Battery.c_deg
        * (out["mpc_charge_mw"] + out["mpc_discharge_mw"])
        * Battery.dt
    )

    out["tier7_total_profit_eur"] = (
        out["dam_market_revenue_eur"]
        + out["intraday_adjustment_revenue_eur"]
        - out["mpc_degradation_cost_eur"]
    )

    out["tier3_dam_only_profit_eur"] = (
        out["dam_price_eur_mwh"] * out["dam_net_mw"] * Battery.dt
        - Battery.c_deg
        * (out["dam_charge_mw"] + out["dam_discharge_mw"])
        * Battery.dt
    )

    out["tier3_dam_schedule_on_intraday_profit_eur"] = (
        out["intraday_price_eur_mwh"] * out["dam_net_mw"] * Battery.dt
        - Battery.c_deg
        * (out["dam_charge_mw"] + out["dam_discharge_mw"])
        * Battery.dt
    )

    out["pure_mpc_intraday_profit_eur"] = (
        out["intraday_price_eur_mwh"] * out["mpc_net_mw"] * Battery.dt
        - out["mpc_degradation_cost_eur"]
    )

    out["dam_net_mwh"] = out["dam_net_mw"] * Battery.dt
    out["mpc_net_mwh"] = out["mpc_net_mw"] * Battery.dt
    out["id_adjustment_mwh"] = out["id_adjustment_mw"] * Battery.dt

    out["mpc_action"] = np.where(
        out["mpc_charge_mw"] > 1e-6,
        "charge",
        np.where(out["mpc_discharge_mw"] > 1e-6, "discharge", "idle"),
    )

    return out


def summarize(df):
    total_tier3_dam = df["tier3_dam_only_profit_eur"].sum()
    total_dam_on_id = df["tier3_dam_schedule_on_intraday_profit_eur"].sum()
    total_tier7 = df["tier7_total_profit_eur"].sum()
    total_pure_mpc = df["pure_mpc_intraday_profit_eur"].sum()

    mpc_throughput = (
        (df["mpc_charge_mw"] + df["mpc_discharge_mw"]) * Battery.dt
    ).sum()

    dam_throughput = (
        (df["dam_charge_mw"] + df["dam_discharge_mw"]) * Battery.dt
    ).sum()

    summary = {
        "expected_profit_eur": total_tier7,
        "realized_profit_eur": total_tier7,
        "tier7_total_profit_eur": total_tier7,
        "tier3_dam_only_profit_eur": total_tier3_dam,
        "tier3_dam_schedule_on_intraday_profit_eur": total_dam_on_id,
        "pure_mpc_intraday_profit_eur_control_benchmark": total_pure_mpc,
        "increment_vs_tier3_dam_only_eur": total_tier7 - total_tier3_dam,
        "increment_vs_tier3_dam_schedule_on_intraday_eur": total_tier7 - total_dam_on_id,
        "dam_throughput_mwh": dam_throughput,
        "mpc_throughput_mwh": mpc_throughput,
        "dam_equivalent_cycles": dam_throughput / (2 * Battery.E_nom),
        "mpc_equivalent_cycles": mpc_throughput / (2 * Battery.E_nom),
        "mpc_final_soc_mwh": df["mpc_soc_mwh"].iloc[-1],
        "dam_final_soc_mwh": df["dam_soc_mwh"].iloc[-1],
        "mpc_active_intervals": int((df["mpc_action"] != "idle").sum()),
        "mpc_idle_intervals": int((df["mpc_action"] == "idle").sum()),
        "total_abs_intraday_adjustment_mwh": df["id_adjustment_mwh"].abs().sum(),
    }

    return pd.DataFrame([summary])


# ============================================================
# PLOTTING
# ============================================================

def plot_results(df):
    fig, axes = plt.subplots(5, 1, figsize=(15, 18), sharex=True)

    ts = df["timestamp"]

    axes[0].plot(ts, df["dam_price_eur_mwh"], label="DAM P50")
    axes[0].plot(ts, df["intraday_price_eur_mwh"], label="Synthetic intraday", alpha=0.85)
    axes[0].set_title("DAM vs Synthetic Intraday Price")
    axes[0].set_ylabel("€/MWh")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].bar(ts, df["dam_charge_mw"], width=0.008, label="Tier 3 DAM charge", alpha=0.6)
    axes[1].bar(ts, -df["dam_discharge_mw"], width=0.008, label="Tier 3 DAM discharge", alpha=0.6)
    axes[1].set_title("Stage 1: Tier 3 Greek-Structural DAM Schedule")
    axes[1].set_ylabel("MW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].bar(ts, df["mpc_charge_mw"], width=0.008, label="MPC charge", alpha=0.6)
    axes[2].bar(ts, -df["mpc_discharge_mw"], width=0.008, label="MPC discharge", alpha=0.6)
    axes[2].set_title("Stage 2: Intraday MPC Physical Dispatch")
    axes[2].set_ylabel("MW")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    axes[3].plot(ts, df["dam_soc_mwh"], label="Tier 3 DAM SOC")
    axes[3].plot(ts, df["mpc_soc_mwh"], label="MPC SOC")
    axes[3].axhline(Battery.SOC_min, linestyle="--", alpha=0.6, label="SOC min")
    axes[3].axhline(Battery.SOC_max, linestyle="--", alpha=0.6, label="SOC max")
    axes[3].set_title("State of Charge")
    axes[3].set_ylabel("MWh")
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    axes[4].plot(ts, df["tier7_total_profit_eur"].cumsum(), label="Tier 7 total")
    axes[4].plot(ts, df["tier3_dam_only_profit_eur"].cumsum(), label="Tier 3 DAM-only")
    axes[4].plot(ts, df["pure_mpc_intraday_profit_eur"].cumsum(), label="Pure MPC intraday benchmark")
    axes[4].set_title("Cumulative Profit")
    axes[4].set_ylabel("€")
    axes[4].legend()
    axes[4].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT, dpi=150)
    plt.show()


# ============================================================
# GENERIC RUNNER SUPPORT
# ============================================================

def run_tier(
    forecast_csv: str,
    capital_base_eur: float | None = None,
    intraday_csv: str = INTRADAY_FILE,
) -> dict:
    base_df = load_dam_and_intraday(
        dam_path=forecast_csv,
        intraday_path=intraday_csv,
    )

    dam_df = run_tier3_dam_schedule(base_df, dam_file=forecast_csv)
    mpc_df = run_intraday_mpc(dam_df)
    result_df = add_market_accounting(mpc_df)
    summary_df = summarize(result_df)

    return summary_df.iloc[0].to_dict()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    print("Loading DAM and synthetic intraday data...")
    base_df = load_dam_and_intraday(DAM_FILE, INTRADAY_FILE)

    dam_df = run_tier3_dam_schedule(base_df, dam_file=DAM_FILE)

    print("Running Stage 2: Intraday MPC / rolling horizon...")
    mpc_df = run_intraday_mpc(dam_df)

    print("Adding simplified market accounting...")
    result_df = add_market_accounting(mpc_df)

    summary_df = summarize(result_df)

    print("\n=== Tier 7 Greek-Structural DAM + Intraday MPC Summary ===")
    for col in summary_df.columns:
        print(f"{col}: {summary_df.loc[0, col]:,.2f}")

    result_df.to_csv(OUTPUT_SCHEDULE, index=False)
    summary_df.to_csv(OUTPUT_SUMMARY, index=False)

    print("\nSaved:")
    print(f"- {OUTPUT_SCHEDULE}")
    print(f"- {OUTPUT_SUMMARY}")
    print(f"- {OUTPUT_PLOT}")

    plot_results(result_df)