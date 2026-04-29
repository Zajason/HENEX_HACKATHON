#greek structural optimiser

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pyomo.environ import *


# ============================================================
# Battery config
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


# ============================================================
# Helpers
# ============================================================

def normalize(s):
    s = pd.Series(s).astype(float)
    return (s - s.min()) / (s.max() - s.min() + 1e-9)


# ============================================================
# Load + create Greek structural features
# ============================================================

def load_forecast(path=None):
    if path is None:
        from optimisation._paths import synthetic
        path = synthetic("synthetic_forecast_day.csv")
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


def add_structural_features(df):
    """
    If real columns exist, uses them:
      load_forecast_mw
      res_forecast_mw
      solar_forecast_mw
      wind_forecast_mw

    If missing, creates realistic synthetic Greek-like profiles.
    """

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
    df["evening_ramp_mw"] = df["residual_load_mw"] - df["residual_load_mw"].shift(steps_4h)
    df["evening_ramp_mw"] = df["evening_ramp_mw"].fillna(0)

    df["curtailment_proxy"] = np.maximum(
        0,
        df["res_share"] - Tier3.export_capacity_share
    )

    df["scarcity_pressure"] = (
        normalize(df["residual_load_mw"])
        + normalize(np.maximum(df["evening_ramp_mw"], 0))
    ) / 2

    df["surplus_pressure"] = normalize(df["curtailment_proxy"])

    df["market_tightness"] = (
        0.45 * normalize(df["p50_eur_mwh"])
        + 0.30 * normalize(df["uncertainty"])
        + 0.25 * df["scarcity_pressure"]
    )

    df["market_tightness_norm"] = normalize(df["market_tightness"])

    return df


# ============================================================
# Tier 3 scenario generation
# ============================================================

def generate_tier3_scenarios(df, n_scenarios=200, seed=42):
    rng = np.random.default_rng(seed)

    p10 = df["p10_eur_mwh"].to_numpy()
    p50 = df["p50_eur_mwh"].to_numpy()
    p90 = df["p90_eur_mwh"].to_numpy()

    scarcity = df["scarcity_pressure"].to_numpy()
    surplus = df["surplus_pressure"].to_numpy()
    tightness = df["market_tightness_norm"].to_numpy()

    sigma_low = (p50 - p10) / 1.2816
    sigma_high = (p90 - p50) / 1.2816
    sigma = np.maximum((sigma_low + sigma_high) / 2, 1e-6)

    sigma = sigma * (1 + 1.1 * tightness + 0.7 * scarcity + 0.5 * surplus)

    scenarios = []

    for _ in range(n_scenarios):
        noise = rng.normal(0, sigma)

        for t in range(1, len(noise)):
            noise[t] = 0.65 * noise[t - 1] + 0.35 * noise[t]

        # Scarcity upward spike risk
        spike_prob = 0.02 + 0.18 * scarcity + 0.10 * tightness
        spike_event = rng.binomial(1, np.clip(spike_prob, 0, 0.5))
        spike_size = (
            rng.gamma(shape=2.2, scale=14.0, size=len(df))
            * scarcity
            * spike_event
            * Tier3.scarcity_spike_multiplier
        )

        # Surplus / curtailment downside risk
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
# Tier 3 stochastic CVaR MILP
# ============================================================

def optimize_tier3(df, scenarios):
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
    surplus = df["surplus_pressure"].to_numpy()
    tightness = df["market_tightness_norm"].to_numpy()

    # Penalize charging in scarcity/high-tightness periods.
    # Encourage charging in surplus periods indirectly through lower scenarios.
    structural_charge_penalty = Tier3.structural_penalty * (scarcity + tightness)

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

    model.soc_min = Constraint(
        T,
        rule=lambda m, t: m.E[t] >= Battery.SOC_min,
    )

    model.soc_max = Constraint(
        T,
        rule=lambda m, t: m.E[t] <= Battery.SOC_max,
    )

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

    if result.solver.status != SolverStatus.ok:
        raise RuntimeError(result)

    out = df.copy()
    out["charge_mw"] = [value(model.P_ch[t]) for t in T]
    out["discharge_mw"] = [value(model.P_dis[t]) for t in T]
    out["soc_mwh"] = [value(model.E[t]) for t in T]
    out["net_power_mw"] = out["discharge_mw"] - out["charge_mw"]

    scenario_profits = np.array([value(model.profit[k]) for k in K])

    return out, scenario_profits


# ============================================================
# Metrics
# ============================================================

def evaluate_schedule_on_prices(schedule, prices):
    return (
        prices
        * (schedule["discharge_mw"].to_numpy() - schedule["charge_mw"].to_numpy())
        * Battery.dt
        - Battery.c_deg
        * (schedule["charge_mw"].to_numpy() + schedule["discharge_mw"].to_numpy())
        * Battery.dt
    ).sum()


def naive_rank_strategy(df):
    out = df.copy()

    out["charge_mw"] = 0.0
    out["discharge_mw"] = 0.0
    out["soc_mwh"] = Battery.E_init

    low = out["p50_eur_mwh"].quantile(0.25)
    high = out["p50_eur_mwh"].quantile(0.75)

    soc = Battery.E_init
    discharged_today = 0.0

    for i, row in out.iterrows():
        price = row["p50_eur_mwh"]

        if price <= low:
            max_add = Battery.SOC_max - soc
            p_ch = min(
                Battery.P_nom,
                Battery.grid_import_max,
                max_add / (Battery.eta_ch * Battery.dt),
            )
            p_ch = max(0, p_ch)

            out.loc[i, "charge_mw"] = p_ch
            soc += Battery.eta_ch * p_ch * Battery.dt

        elif price >= high and discharged_today < Battery.max_cycles * Battery.E_nom:
            max_remove = soc - Battery.SOC_min
            p_dis = min(
                Battery.P_nom,
                Battery.grid_export_max,
                max_remove * Battery.eta_dis / Battery.dt,
            )

            remaining = Battery.max_cycles * Battery.E_nom - discharged_today
            p_dis = min(p_dis, remaining / Battery.dt)
            p_dis = max(0, p_dis)

            out.loc[i, "discharge_mw"] = p_dis
            soc -= p_dis * Battery.dt / Battery.eta_dis
            discharged_today += p_dis * Battery.dt

        out.loc[i, "soc_mwh"] = soc

    out["net_power_mw"] = out["discharge_mw"] - out["charge_mw"]

    return out


def calculate_metrics(schedule, scenarios, naive_schedule=None):
    profits = np.array([
        evaluate_schedule_on_prices(schedule, scenarios[k])
        for k in range(scenarios.shape[0])
    ])

    throughput = (
        (schedule["charge_mw"] + schedule["discharge_mw"]) * Battery.dt
    ).sum()

    metrics = {
        "expected_profit_eur": profits.mean(),
        "median_profit_eur": np.median(profits),
        "p10_profit_eur": np.quantile(profits, 0.10),
        "worst_profit_eur": profits.min(),
        "cvar_10_profit_eur": profits[
            profits <= np.quantile(profits, Risk.alpha)
        ].mean(),
        "profit_std_eur": profits.std(),
        "sharpe_like": profits.mean() / profits.std() if profits.std() > 1e-9 else np.nan,
        "throughput_mwh": throughput,
        "equivalent_cycles": throughput / (2 * Battery.E_nom),
        "profit_per_mwh_throughput": profits.mean() / throughput if throughput > 0 else 0,
        "active_intervals": int(
            ((schedule["charge_mw"] > 1e-6) | (schedule["discharge_mw"] > 1e-6)).sum()
        ),
        "idle_intervals": int(
            ((schedule["charge_mw"] <= 1e-6) & (schedule["discharge_mw"] <= 1e-6)).sum()
        ),
        "min_soc_mwh": schedule["soc_mwh"].min(),
        "max_soc_mwh": schedule["soc_mwh"].max(),
    }

    if naive_schedule is not None:
        naive_profits = np.array([
            evaluate_schedule_on_prices(naive_schedule, scenarios[k])
            for k in range(scenarios.shape[0])
        ])

        diff = profits - naive_profits

        metrics.update({
            "naive_expected_profit_eur": naive_profits.mean(),
            "profit_improvement_vs_naive_eur": diff.mean(),
            "information_ratio_vs_naive": diff.mean() / diff.std() if diff.std() > 1e-9 else np.nan,
            "naive_cvar_10_profit_eur": naive_profits[
                naive_profits <= np.quantile(naive_profits, Risk.alpha)
            ].mean(),
        })

    return metrics, profits


# ============================================================
# Plotting
# ============================================================

def plot_tier3_results(schedule, scenarios, profits):
    fig, axes = plt.subplots(6, 1, figsize=(15, 20), sharex=False)

    timestamps = schedule["timestamp"]

    for k in range(min(25, scenarios.shape[0])):
        axes[0].plot(timestamps, scenarios[k], alpha=0.10)

    axes[0].plot(timestamps, schedule["p50_eur_mwh"], linewidth=2, label="P50")
    axes[0].fill_between(
        timestamps,
        schedule["p10_eur_mwh"],
        schedule["p90_eur_mwh"],
        alpha=0.25,
        label="P10-P90",
    )
    axes[0].set_title("Tier 3 Greek-Structural Price Scenarios")
    axes[0].set_ylabel("€/MWh")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(timestamps, schedule["residual_load_mw"], label="Residual load")
    axes[1].plot(timestamps, schedule["load_forecast_mw"], alpha=0.5, label="Load")
    axes[1].plot(timestamps, schedule["res_forecast_mw"], alpha=0.5, label="RES")
    axes[1].set_title("Greek Power-System Fundamentals")
    axes[1].set_ylabel("MW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(timestamps, schedule["scarcity_pressure"], label="Scarcity pressure")
    axes[2].plot(timestamps, schedule["surplus_pressure"], label="Surplus pressure")
    axes[2].plot(timestamps, schedule["market_tightness_norm"], label="Market tightness")
    axes[2].set_title("Structural Pressure Signals")
    axes[2].set_ylabel("0-1")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    axes[3].bar(timestamps, schedule["charge_mw"], width=0.008, label="Charge")
    axes[3].bar(timestamps, -schedule["discharge_mw"], width=0.008, label="Discharge")
    axes[3].set_title("Tier 3 Dispatch")
    axes[3].set_ylabel("MW")
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    axes[4].plot(timestamps, schedule["soc_mwh"], label="SOC")
    axes[4].axhline(Battery.SOC_min, linestyle="--", label="SOC min")
    axes[4].axhline(Battery.SOC_max, linestyle="--", label="SOC max")
    axes[4].set_title("State of Charge")
    axes[4].set_ylabel("MWh")
    axes[4].legend()
    axes[4].grid(True, alpha=0.3)

    axes[5].hist(profits, bins=30)
    axes[5].axvline(profits.mean(), linestyle="--", label="Mean")
    axes[5].axvline(np.quantile(profits, 0.10), linestyle="--", label="P10")
    axes[5].set_title("Profit Distribution")
    axes[5].set_xlabel("Profit (€)")
    axes[5].legend()
    axes[5].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    df = load_forecast()

    scenarios = generate_tier3_scenarios(
        df,
        n_scenarios=Risk.n_scenarios,
        seed=Risk.seed,
    )

    schedule, profits = optimize_tier3(df, scenarios)

    naive = naive_rank_strategy(df)

    metrics, evaluated_profits = calculate_metrics(
        schedule,
        scenarios,
        naive_schedule=naive,
    )

    print("\n=== Tier 3 Greek-Structural Metrics ===")
    for k, v in metrics.items():
        print(f"{k}: {v:,.2f}")

    from optimisation._paths import result
    schedule.to_csv(result("tier3_greek_structural_schedule.csv"), index=False)
    pd.DataFrame(scenarios).to_csv(result("tier3_greek_structural_scenarios.csv"), index=False)

    print("\nSaved:")
    print(f"- {result('tier3_greek_structural_schedule.csv')}")
    print(f"- {result('tier3_greek_structural_scenarios.csv')}")

    plot_tier3_results(schedule, scenarios, evaluated_profits)