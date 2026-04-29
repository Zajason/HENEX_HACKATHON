import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pyomo.environ import *

# cuve aware cvar optimiser

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
    risk_aversion = 0.45
    n_scenarios = 200
    seed = 42


class Tier2:
    tightness_penalty = 0.30
    tightness_spike_multiplier = 1.40


# ============================================================
# Data
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

    df["uncertainty"] = (df["p90_eur_mwh"] - df["p10_eur_mwh"]) / 2

    if "market_tightness" not in df.columns:
        df["market_tightness"] = simulate_market_tightness(df)

    df["market_tightness_norm"] = normalize_series(df["market_tightness"])

    return df


def normalize_series(s):
    s = s.astype(float)
    return (s - s.min()) / (s.max() - s.min() + 1e-9)


def simulate_market_tightness(df):
    """
    Stand-in for HEnEx curve-derived dP/dQ.

    Intuition:
    - Tightness high when prices are high
    - Tightness high when uncertainty is wide
    - Tightness high during evening scarcity periods
    """

    hours = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60

    price_component = normalize_series(df["p50_eur_mwh"])
    uncertainty_component = normalize_series(df["p90_eur_mwh"] - df["p10_eur_mwh"])

    evening_component = np.exp(-((hours - 19) ** 2) / 5)
    evening_component = evening_component / (evening_component.max() + 1e-9)

    tightness = (
        0.50 * price_component
        + 0.30 * uncertainty_component
        + 0.20 * evening_component
    )

    # units are synthetic proxy, but comparable across intervals
    return tightness


# ============================================================
# Scenario generation
# ============================================================

def generate_curve_aware_scenarios(df, n_scenarios=200, seed=42):
    """
    Tier 2 scenario generation.

    Compared to Tier 1:
    - uncertainty increases in tight-market periods
    - high tightness creates upward spike risk
    """

    rng = np.random.default_rng(seed)

    p10 = df["p10_eur_mwh"].to_numpy()
    p50 = df["p50_eur_mwh"].to_numpy()
    p90 = df["p90_eur_mwh"].to_numpy()
    tightness = df["market_tightness_norm"].to_numpy()

    sigma_low = (p50 - p10) / 1.2816
    sigma_high = (p90 - p50) / 1.2816
    sigma = np.maximum((sigma_low + sigma_high) / 2, 1e-6)

    # More volatile when curve is steep
    sigma = sigma * (1.0 + Tier2.tightness_spike_multiplier * tightness)

    scenarios = []

    for _ in range(n_scenarios):
        normal_noise = rng.normal(0, sigma)

        # mild time correlation
        for t in range(1, len(normal_noise)):
            normal_noise[t] = 0.65 * normal_noise[t - 1] + 0.35 * normal_noise[t]

        # upward scarcity jump risk
        jump_probability = 0.03 + 0.17 * tightness
        jumps = rng.binomial(1, jump_probability)
        jump_size = rng.gamma(shape=2.0, scale=12.0, size=len(p50)) * tightness * jumps

        scenario = p50 + normal_noise + jump_size
        scenario = np.clip(scenario, -50, 500)

        scenarios.append(scenario)

    return np.array(scenarios)


# ============================================================
# Tier 2 curve-aware stochastic CVaR MILP
# ============================================================

def optimize_tier2_curve_cvar(df, scenarios):
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

    tightness = df["market_tightness_norm"].to_numpy()

    def scenario_profit_rule(m, k):
        return m.profit[k] == sum(
            scenarios[k, t] * (m.P_dis[t] - m.P_ch[t]) * Battery.dt
            - Battery.c_deg * (m.P_ch[t] + m.P_dis[t]) * Battery.dt
            - Tier2.tightness_penalty * tightness[t] * m.P_ch[t] * Battery.dt
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

    # Power limits
    model.charge_limit = Constraint(
        T,
        rule=lambda m, t: m.P_ch[t] <= Battery.P_nom * m.u_ch[t],
    )

    model.discharge_limit = Constraint(
        T,
        rule=lambda m, t: m.P_dis[t] <= Battery.P_nom * m.u_dis[t],
    )

    # No simultaneous charging/discharging
    model.no_simultaneous = Constraint(
        T,
        rule=lambda m, t: m.u_ch[t] + m.u_dis[t] <= 1,
    )

    # SOC dynamics
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

    risk_report = {
        "expected_profit_eur": scenario_profits.mean(),
        "median_profit_eur": np.median(scenario_profits),
        "p10_profit_eur": np.quantile(scenario_profits, 0.10),
        "worst_profit_eur": scenario_profits.min(),
        "profit_std_eur": scenario_profits.std(),
        "cvar_10_profit_eur": scenario_profits[
            scenario_profits <= np.quantile(scenario_profits, Risk.alpha)
        ].mean(),
        "objective_value": value(model.obj),
    }

    return out, scenario_profits, risk_report


# ============================================================
# Baselines and metrics
# ============================================================

def evaluate_schedule_on_prices(schedule, prices):
    profit = (
        prices
        * (schedule["discharge_mw"].to_numpy() - schedule["charge_mw"].to_numpy())
        * Battery.dt
        - Battery.c_deg
        * (schedule["charge_mw"].to_numpy() + schedule["discharge_mw"].to_numpy())
        * Battery.dt
    ).sum()

    return profit


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

            out.loc[i, "charge_mw"] = max(0, p_ch)
            soc += Battery.eta_ch * p_ch * Battery.dt

        elif price >= high and discharged_today < Battery.max_cycles * Battery.E_nom:
            max_remove = soc - Battery.SOC_min

            p_dis = min(
                Battery.P_nom,
                Battery.grid_export_max,
                max_remove * Battery.eta_dis / Battery.dt,
            )

            remaining_discharge = Battery.max_cycles * Battery.E_nom - discharged_today
            p_dis = min(p_dis, remaining_discharge / Battery.dt)

            out.loc[i, "discharge_mw"] = max(0, p_dis)
            soc -= p_dis * Battery.dt / Battery.eta_dis
            discharged_today += p_dis * Battery.dt

        out.loc[i, "soc_mwh"] = soc

    out["net_power_mw"] = out["discharge_mw"] - out["charge_mw"]

    return out


def calculate_metrics(schedule, scenarios, naive_schedule=None):
    scenario_profits = np.array([
        evaluate_schedule_on_prices(schedule, scenarios[k])
        for k in range(scenarios.shape[0])
    ])

    throughput = (
        (schedule["charge_mw"] + schedule["discharge_mw"]) * Battery.dt
    ).sum()

    cycles = throughput / (2 * Battery.E_nom)

    metrics = {
        "expected_profit_eur": scenario_profits.mean(),
        "median_profit_eur": np.median(scenario_profits),
        "p10_profit_eur": np.quantile(scenario_profits, 0.10),
        "worst_profit_eur": scenario_profits.min(),
        "cvar_10_profit_eur": scenario_profits[
            scenario_profits <= np.quantile(scenario_profits, Risk.alpha)
        ].mean(),
        "profit_std_eur": scenario_profits.std(),
        "sharpe_like": (
            scenario_profits.mean() / scenario_profits.std()
            if scenario_profits.std() > 1e-9
            else np.nan
        ),
        "throughput_mwh": throughput,
        "equivalent_cycles": cycles,
        "profit_per_mwh_throughput": (
            scenario_profits.mean() / throughput if throughput > 0 else 0
        ),
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

        spread = scenario_profits - naive_profits

        metrics.update({
            "naive_expected_profit_eur": naive_profits.mean(),
            "profit_improvement_vs_naive_eur": spread.mean(),
            "information_ratio_vs_naive": (
                spread.mean() / spread.std() if spread.std() > 1e-9 else np.nan
            ),
            "naive_cvar_10_profit_eur": naive_profits[
                naive_profits <= np.quantile(naive_profits, Risk.alpha)
            ].mean(),
        })

    return metrics


# ============================================================
# Plotting
# ============================================================

def plot_tier2_results(schedule, scenarios, scenario_profits):
    fig, axes = plt.subplots(5, 1, figsize=(15, 17), sharex=False)

    timestamps = schedule["timestamp"]

    for k in range(min(25, scenarios.shape[0])):
        axes[0].plot(timestamps, scenarios[k], alpha=0.12)

    axes[0].plot(timestamps, schedule["p50_eur_mwh"], linewidth=2, label="P50")
    axes[0].fill_between(
        timestamps,
        schedule["p10_eur_mwh"],
        schedule["p90_eur_mwh"],
        alpha=0.25,
        label="P10-P90",
    )
    axes[0].set_title("Tier 2 Curve-Aware Price Scenarios")
    axes[0].set_ylabel("€/MWh")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(
        timestamps,
        schedule["market_tightness_norm"],
        label="Market tightness",
    )
    axes[1].set_title("Market Tightness Proxy")
    axes[1].set_ylabel("0-1")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].bar(timestamps, schedule["charge_mw"], width=0.008, label="Charge")
    axes[2].bar(timestamps, -schedule["discharge_mw"], width=0.008, label="Discharge")
    axes[2].set_title("Tier 2 Dispatch")
    axes[2].set_ylabel("MW")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    axes[3].plot(timestamps, schedule["soc_mwh"], label="SOC")
    axes[3].axhline(Battery.SOC_min, linestyle="--", alpha=0.7, label="SOC min")
    axes[3].axhline(Battery.SOC_max, linestyle="--", alpha=0.7, label="SOC max")
    axes[3].set_title("State of Charge")
    axes[3].set_ylabel("MWh")
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    axes[4].hist(scenario_profits, bins=30)
    axes[4].axvline(np.mean(scenario_profits), linestyle="--", label="Mean")
    axes[4].axvline(np.quantile(scenario_profits, 0.10), linestyle="--", label="P10")
    axes[4].set_title("Scenario Profit Distribution")
    axes[4].set_xlabel("Profit (€)")
    axes[4].legend()
    axes[4].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    df = load_forecast()

    scenarios = generate_curve_aware_scenarios(
        df,
        n_scenarios=Risk.n_scenarios,
        seed=Risk.seed,
    )

    tier2_schedule, scenario_profits, risk_report = optimize_tier2_curve_cvar(
        df,
        scenarios,
    )

    naive_schedule = naive_rank_strategy(df)

    metrics = calculate_metrics(
        tier2_schedule,
        scenarios,
        naive_schedule=naive_schedule,
    )

    print("\n=== Tier 2 Curve-Aware CVaR Risk Report ===")
    for k, v in risk_report.items():
        print(f"{k}: {v:,.2f}")

    print("\n=== Tier 2 Comparison Metrics ===")
    for k, v in metrics.items():
        print(f"{k}: {v:,.2f}")

    from optimisation._paths import result
    tier2_schedule.to_csv(result("tier2_curve_aware_schedule.csv"), index=False)
    pd.DataFrame(scenarios).to_csv(result("tier2_curve_aware_price_scenarios.csv"), index=False)

    print("\nSaved:")
    print(f"- {result('tier2_curve_aware_schedule.csv')}")
    print(f"- {result('tier2_curve_aware_price_scenarios.csv')}")

    plot_tier2_results(tier2_schedule, scenarios, scenario_profits)