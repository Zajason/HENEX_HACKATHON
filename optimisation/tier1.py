import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pyomo.environ import *

#regime mixture
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
    alpha = 0.10          # CVaR lower tail: worst 10%
    risk_aversion = 0.35 # higher = more conservative
    n_scenarios = 200
    seed = 42


# ============================================================
# Data
# ============================================================

def load_forecast(path="synthetic_forecast_day.csv"):
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    required = {"timestamp", "p10_eur_mwh", "p50_eur_mwh", "p90_eur_mwh"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    return df


def generate_price_scenarios(df, n_scenarios=200, seed=42):
    """
    Creates realistic scenarios from P10/P50/P90.

    Assumption:
    P10 and P90 are roughly symmetric quantiles.
    For normal distribution:
      P90 - P50 ≈ 1.2816 sigma
      P50 - P10 ≈ 1.2816 sigma
    """

    rng = np.random.default_rng(seed)

    p10 = df["p10_eur_mwh"].to_numpy()
    p50 = df["p50_eur_mwh"].to_numpy()
    p90 = df["p90_eur_mwh"].to_numpy()

    sigma_low = (p50 - p10) / 1.2816
    sigma_high = (p90 - p50) / 1.2816
    sigma = np.maximum((sigma_low + sigma_high) / 2, 1e-6)

    scenarios = []

    for _ in range(n_scenarios):
        noise = rng.normal(0, sigma)

        # Add mild temporal correlation so scenarios are smoother
        for t in range(1, len(noise)):
            noise[t] = 0.65 * noise[t - 1] + 0.35 * noise[t]

        scenario = p50 + noise
        scenario = np.clip(scenario, -50, 400)
        scenarios.append(scenario)

    scenarios = np.array(scenarios)

    return scenarios


# ============================================================
# Tier 1 stochastic MILP with CVaR
# ============================================================

def optimize_tier1_cvar(df, scenarios):
    """
    First-stage schedule:
      One battery schedule is chosen before prices realize.

    Scenarios:
      Used to evaluate profit under many possible future price paths.

    CVaR:
      Penalizes the average loss in the worst alpha fraction of scenarios.
    """

    S, T_len = scenarios.shape
    T = range(T_len)
    K = range(S)

    model = ConcreteModel()

    # Battery variables
    model.P_ch = Var(T, domain=NonNegativeReals)
    model.P_dis = Var(T, domain=NonNegativeReals)
    model.E = Var(T, domain=NonNegativeReals)

    model.u_ch = Var(T, domain=Binary)
    model.u_dis = Var(T, domain=Binary)

    # Scenario profit variables
    model.profit = Var(K, domain=Reals)

    # CVaR loss variables
    model.var_loss = Var(domain=Reals)
    model.excess_loss = Var(K, domain=NonNegativeReals)

    # --------------------------------------------------------
    # Profit per scenario
    # --------------------------------------------------------

    def scenario_profit_rule(m, k):
        return m.profit[k] == sum(
            scenarios[k, t] * (m.P_dis[t] - m.P_ch[t]) * Battery.dt
            - Battery.c_deg * (m.P_ch[t] + m.P_dis[t]) * Battery.dt
            for t in T
        )

    model.scenario_profit = Constraint(K, rule=scenario_profit_rule)

    # --------------------------------------------------------
    # CVaR formulation
    # --------------------------------------------------------
    # loss_k = -profit_k
    # excess_loss_k >= loss_k - var_loss

    def cvar_excess_rule(m, k):
        return m.excess_loss[k] >= -m.profit[k] - m.var_loss

    model.cvar_excess = Constraint(K, rule=cvar_excess_rule)

    def expected_profit(m):
        return sum(m.profit[k] for k in K) / S

    def cvar_loss(m):
        return m.var_loss + (1 / (Risk.alpha * S)) * sum(m.excess_loss[k] for k in K)

    # Max expected profit minus CVaR penalty
    model.obj = Objective(
        expr=expected_profit(model) - Risk.risk_aversion * cvar_loss(model),
        sense=maximize,
    )

    # --------------------------------------------------------
    # Battery constraints
    # --------------------------------------------------------

    def charge_limit(m, t):
        return m.P_ch[t] <= Battery.P_nom * m.u_ch[t]

    def discharge_limit(m, t):
        return m.P_dis[t] <= Battery.P_nom * m.u_dis[t]

    model.charge_limit = Constraint(T, rule=charge_limit)
    model.discharge_limit = Constraint(T, rule=discharge_limit)

    def no_simultaneous(m, t):
        return m.u_ch[t] + m.u_dis[t] <= 1

    model.no_simultaneous = Constraint(T, rule=no_simultaneous)

    def soc_rule(m, t):
        if t == 0:
            return m.E[t] == Battery.E_init \
                + Battery.eta_ch * m.P_ch[t] * Battery.dt \
                - (m.P_dis[t] / Battery.eta_dis) * Battery.dt
        else:
            return m.E[t] == m.E[t - 1] \
                + Battery.eta_ch * m.P_ch[t] * Battery.dt \
                - (m.P_dis[t] / Battery.eta_dis) * Battery.dt

    model.soc = Constraint(T, rule=soc_rule)

    def soc_min(m, t):
        return m.E[t] >= Battery.SOC_min

    def soc_max(m, t):
        return m.E[t] <= Battery.SOC_max

    model.soc_min = Constraint(T, rule=soc_min)
    model.soc_max = Constraint(T, rule=soc_max)

    model.final_soc = Constraint(expr=model.E[T_len - 1] == Battery.E_init)

    def cycle_limit(m):
        return sum(m.P_dis[t] * Battery.dt for t in T) <= Battery.max_cycles * Battery.E_nom

    model.cycle_limit = Constraint(rule=cycle_limit)

    def grid_import(m, t):
        return m.P_ch[t] <= Battery.grid_import_max

    def grid_export(m, t):
        return m.P_dis[t] <= Battery.grid_export_max

    model.grid_import = Constraint(T, rule=grid_import)
    model.grid_export = Constraint(T, rule=grid_export)

    # --------------------------------------------------------
    # Solve
    # --------------------------------------------------------

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
        "cvar_10_loss_eur": value(
            model.var_loss + (1 / (Risk.alpha * S)) * sum(model.excess_loss[k] for k in K)
        ),
        "var_10_loss_eur": value(model.var_loss),
        "objective_value": value(model.obj),
    }

    return out, scenario_profits, risk_report


# ============================================================
# Baselines and metrics
# ============================================================

def evaluate_schedule_on_prices(schedule, prices):
    dt = Battery.dt

    profit = (
        prices * (schedule["discharge_mw"].to_numpy() - schedule["charge_mw"].to_numpy()) * dt
        - Battery.c_deg
        * (schedule["charge_mw"].to_numpy() + schedule["discharge_mw"].to_numpy())
        * dt
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


def calculate_tier_metrics(schedule, scenarios, naive_schedule=None):
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
        "profit_std_eur": scenario_profits.std(),
        "sharpe_like": scenario_profits.mean() / scenario_profits.std()
        if scenario_profits.std() > 1e-9 else np.nan,
        "throughput_mwh": throughput,
        "equivalent_cycles": cycles,
        "profit_per_mwh_throughput": scenario_profits.mean() / throughput
        if throughput > 0 else 0,
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

        alpha = Risk.alpha
        metrics.update({
            "naive_expected_profit_eur": naive_profits.mean(),
            "profit_improvement_vs_naive_eur": scenario_profits.mean() - naive_profits.mean(),
            "information_ratio_vs_naive": (
                (scenario_profits - naive_profits).mean()
                / (scenario_profits - naive_profits).std()
                if (scenario_profits - naive_profits).std() > 1e-9 else np.nan
            ),
            "tier_cvar_profit_10": scenario_profits[scenario_profits <= np.quantile(scenario_profits, alpha)].mean(),
            "naive_cvar_profit_10": naive_profits[naive_profits <= np.quantile(naive_profits, alpha)].mean(),
        })

    return metrics


# ============================================================
# Plotting
# ============================================================

def plot_tier1_results(schedule, scenarios, scenario_profits):
    fig, axes = plt.subplots(4, 1, figsize=(15, 14), sharex=False)

    # Price scenarios
    timestamps = schedule["timestamp"]

    for k in range(min(25, scenarios.shape[0])):
        axes[0].plot(timestamps, scenarios[k], alpha=0.15)

    axes[0].plot(timestamps, schedule["p50_eur_mwh"], linewidth=2, label="P50")
    axes[0].fill_between(
        timestamps,
        schedule["p10_eur_mwh"],
        schedule["p90_eur_mwh"],
        alpha=0.25,
        label="P10-P90",
    )
    axes[0].set_title("Price Scenarios")
    axes[0].set_ylabel("€/MWh")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Dispatch
    axes[1].bar(timestamps, schedule["charge_mw"], width=0.008, label="Charge")
    axes[1].bar(timestamps, -schedule["discharge_mw"], width=0.008, label="Discharge")
    axes[1].set_title("Tier 1 Dispatch")
    axes[1].set_ylabel("MW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    # SOC
    axes[2].plot(timestamps, schedule["soc_mwh"], label="SOC")
    axes[2].axhline(Battery.SOC_min, linestyle="--", alpha=0.7, label="SOC min")
    axes[2].axhline(Battery.SOC_max, linestyle="--", alpha=0.7, label="SOC max")
    axes[2].set_title("State of Charge")
    axes[2].set_ylabel("MWh")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    # Profit distribution
    axes[3].hist(scenario_profits, bins=30)
    axes[3].axvline(np.mean(scenario_profits), linestyle="--", label="Mean")
    axes[3].axvline(np.quantile(scenario_profits, 0.10), linestyle="--", label="P10")
    axes[3].set_title("Scenario Profit Distribution")
    axes[3].set_xlabel("Profit (€)")
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    df = load_forecast("synthetic_forecast_day.csv")

    scenarios = generate_price_scenarios(
        df,
        n_scenarios=Risk.n_scenarios,
        seed=Risk.seed,
    )

    tier1_schedule, scenario_profits, risk_report = optimize_tier1_cvar(df, scenarios)

    naive_schedule = naive_rank_strategy(df)

    metrics = calculate_tier_metrics(
        tier1_schedule,
        scenarios,
        naive_schedule=naive_schedule,
    )

    print("\n=== Tier 1 CVaR Risk Report ===")
    for k, v in risk_report.items():
        print(f"{k}: {v:,.2f}")

    print("\n=== Tier 1 Comparison Metrics ===")
    for k, v in metrics.items():
        print(f"{k}: {v:,.2f}")

    tier1_schedule.to_csv("tier1_cvar_schedule.csv", index=False)
    pd.DataFrame(scenarios).to_csv("tier1_price_scenarios.csv", index=False)

    print("\nSaved:")
    print("- tier1_cvar_schedule.csv")
    print("- tier1_price_scenarios.csv")

    plot_tier1_results(tier1_schedule, scenarios, scenario_profits)