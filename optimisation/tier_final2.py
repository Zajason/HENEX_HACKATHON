# tier_final2 — Tier 1 CVaR optimiser with dynamic grouped battery config
#
# Uses Tier 1 price-scenario/CVaR logic, but treats battery groups like
# tier_final: quantity is aggregated within a block, different blocks keep
# separate power, SoC, efficiency, and degradation constraints.

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pyomo.environ import *

from optimisation.tier_final import (
    BatteryParams,
    calculate_group_metrics,
    load_battery_params,
    naive_rank_strategy,
    print_battery_params,
    print_group_metrics,
)


class Risk:
    alpha = 0.10
    risk_aversion = 0.35
    n_scenarios = 200
    seed = 42


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

    return df


def generate_price_scenarios(df, n_scenarios=200, seed=42):
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
        for t in range(1, len(noise)):
            noise[t] = 0.65 * noise[t - 1] + 0.35 * noise[t]

        scenario = p50 + noise
        scenario = np.clip(scenario, -50, 400)
        scenarios.append(scenario)

    return np.array(scenarios)


def optimize_tier_final2_cvar(df, scenarios, bp: BatteryParams):
    S, T_len = scenarios.shape
    T = range(T_len)
    K = range(S)
    G = range(len(bp.groups))

    model = ConcreteModel()

    model.P_ch = Var(G, T, domain=NonNegativeReals)
    model.P_dis = Var(G, T, domain=NonNegativeReals)
    model.E = Var(G, T, domain=NonNegativeReals)

    model.u_ch = Var(T, domain=Binary)
    model.u_dis = Var(T, domain=Binary)

    model.profit = Var(K, domain=Reals)
    model.var_loss = Var(domain=Reals)
    model.excess_loss = Var(K, domain=NonNegativeReals)

    def scenario_profit_rule(m, k):
        return m.profit[k] == sum(
            scenarios[k, t]
            * sum(m.P_dis[g, t] - m.P_ch[g, t] for g in G)
            * bp.dt
            - sum(
                bp.groups[g].c_deg * (m.P_ch[g, t] + m.P_dis[g, t]) * bp.dt
                for g in G
            )
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
        G,
        T,
        rule=lambda m, g, t: m.P_ch[g, t] <= bp.groups[g].P_nom * m.u_ch[t],
    )
    model.discharge_limit = Constraint(
        G,
        T,
        rule=lambda m, g, t: m.P_dis[g, t] <= bp.groups[g].P_nom * m.u_dis[t],
    )
    model.no_simultaneous = Constraint(
        T,
        rule=lambda m, t: m.u_ch[t] + m.u_dis[t] <= 1,
    )

    def soc_rule(m, g, t):
        group = bp.groups[g]
        if t == 0:
            return m.E[g, t] == (
                group.E_init
                + group.eta_ch * m.P_ch[g, t] * bp.dt
                - (m.P_dis[g, t] / group.eta_dis) * bp.dt
            )

        return m.E[g, t] == (
            m.E[g, t - 1]
            + group.eta_ch * m.P_ch[g, t] * bp.dt
            - (m.P_dis[g, t] / group.eta_dis) * bp.dt
        )

    model.soc = Constraint(G, T, rule=soc_rule)
    model.soc_min = Constraint(
        G,
        T,
        rule=lambda m, g, t: m.E[g, t] >= bp.groups[g].SOC_min,
    )
    model.soc_max = Constraint(
        G,
        T,
        rule=lambda m, g, t: m.E[g, t] <= bp.groups[g].SOC_max,
    )
    model.final_soc = Constraint(
        G,
        rule=lambda m, g: m.E[g, T_len - 1] == bp.groups[g].E_init,
    )
    model.cycle_limit = Constraint(
        G,
        rule=lambda m, g: sum(m.P_dis[g, t] * bp.dt for t in T)
        <= bp.groups[g].max_cycles * bp.groups[g].E_nom,
    )
    model.grid_import = Constraint(
        T,
        rule=lambda m, t: sum(m.P_ch[g, t] for g in G) <= bp.grid_import_max,
    )
    model.grid_export = Constraint(
        T,
        rule=lambda m, t: sum(m.P_dis[g, t] for g in G) <= bp.grid_export_max,
    )

    solver = SolverFactory("appsi_highs")
    result = solver.solve(model, tee=False)
    if result.solver.status != SolverStatus.ok:
        raise RuntimeError(result)

    out = df.copy()
    for g, group in enumerate(bp.groups):
        prefix = f"group_{g + 1}"
        out[f"{prefix}_name"] = group.name
        out[f"{prefix}_charge_mw"] = [value(model.P_ch[g, t]) for t in T]
        out[f"{prefix}_discharge_mw"] = [value(model.P_dis[g, t]) for t in T]
        out[f"{prefix}_soc_mwh"] = [value(model.E[g, t]) for t in T]

    out["charge_mw"] = [sum(value(model.P_ch[g, t]) for g in G) for t in T]
    out["discharge_mw"] = [sum(value(model.P_dis[g, t]) for g in G) for t in T]
    out["soc_mwh"] = [sum(value(model.E[g, t]) for g in G) for t in T]
    out["net_power_mw"] = out["discharge_mw"] - out["charge_mw"]

    scenario_profits = np.array([value(model.profit[k]) for k in K])
    risk_report = {
        "expected_profit_eur": scenario_profits.mean(),
        "median_profit_eur": np.median(scenario_profits),
        "p10_profit_eur": np.quantile(scenario_profits, 0.10),
        "worst_profit_eur": scenario_profits.min(),
        "cvar_10_loss_eur": value(cvar_loss),
        "var_10_loss_eur": value(model.var_loss),
        "objective_value": value(model.obj),
    }

    return out, scenario_profits, risk_report


def evaluate_schedule_on_prices(schedule, prices, bp: BatteryParams):
    market_revenue = (
        prices
        * (schedule["discharge_mw"].to_numpy() - schedule["charge_mw"].to_numpy())
        * bp.dt
    ).sum()

    degradation_cost = 0.0
    for g, group in enumerate(bp.groups):
        prefix = f"group_{g + 1}"
        degradation_cost += (
            group.c_deg
            * (
                schedule[f"{prefix}_charge_mw"].to_numpy()
                + schedule[f"{prefix}_discharge_mw"].to_numpy()
            )
            * bp.dt
        ).sum()

    return market_revenue - degradation_cost


def calculate_tier_metrics(schedule, scenarios, bp: BatteryParams, naive_schedule=None):
    scenario_profits = np.array([
        evaluate_schedule_on_prices(schedule, scenarios[k], bp)
        for k in range(scenarios.shape[0])
    ])

    throughput = ((schedule["charge_mw"] + schedule["discharge_mw"]) * bp.dt).sum()
    metrics = {
        "expected_profit_eur": scenario_profits.mean(),
        "median_profit_eur": np.median(scenario_profits),
        "p10_profit_eur": np.quantile(scenario_profits, 0.10),
        "worst_profit_eur": scenario_profits.min(),
        "profit_std_eur": scenario_profits.std(),
        "sharpe_like": (
            scenario_profits.mean() / scenario_profits.std()
            if scenario_profits.std() > 1e-9
            else np.nan
        ),
        "throughput_mwh": throughput,
        "equivalent_cycles": throughput / (2 * bp.E_nom),
        "profit_per_mwh_throughput": scenario_profits.mean() / throughput if throughput > 0 else 0,
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
            evaluate_schedule_on_prices(naive_schedule, scenarios[k], bp)
            for k in range(scenarios.shape[0])
        ])
        diff = scenario_profits - naive_profits
        metrics.update({
            "naive_expected_profit_eur": naive_profits.mean(),
            "profit_improvement_vs_naive_eur": diff.mean(),
            "information_ratio_vs_naive": diff.mean() / diff.std() if diff.std() > 1e-9 else np.nan,
            "tier_cvar_profit_10": scenario_profits[
                scenario_profits <= np.quantile(scenario_profits, Risk.alpha)
            ].mean(),
            "naive_cvar_profit_10": naive_profits[
                naive_profits <= np.quantile(naive_profits, Risk.alpha)
            ].mean(),
        })

    return metrics


def plot_tier_final2_results(schedule, scenarios, scenario_profits, bp: BatteryParams):
    fig, axes = plt.subplots(4, 1, figsize=(15, 14), sharex=False)
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
    axes[0].set_title("Tier Final 2 — Tier 1 Price Scenarios")
    axes[0].set_ylabel("EUR/MWh")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].bar(timestamps, schedule["charge_mw"], width=0.008, label="Charge")
    axes[1].bar(timestamps, -schedule["discharge_mw"], width=0.008, label="Discharge")
    axes[1].set_title(f"Tier Final 2 Dispatch — {bp.P_nom:.1f} MW / {bp.E_nom:.1f} MWh")
    axes[1].set_ylabel("MW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(timestamps, schedule["soc_mwh"], label="Fleet SOC")
    for g, group in enumerate(bp.groups):
        axes[2].plot(timestamps, schedule[f"group_{g + 1}_soc_mwh"], alpha=0.8, label=f"{group.name} SOC")
    axes[2].axhline(bp.SOC_min, linestyle="--", alpha=0.7, label="Fleet SOC min")
    axes[2].axhline(bp.SOC_max, linestyle="--", alpha=0.7, label="Fleet SOC max")
    axes[2].set_title("State of Charge")
    axes[2].set_ylabel("MWh")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    axes[3].hist(scenario_profits, bins=30)
    axes[3].axvline(np.mean(scenario_profits), linestyle="--", label="Mean")
    axes[3].axvline(np.quantile(scenario_profits, 0.10), linestyle="--", label="P10")
    axes[3].set_title("Scenario Profit Distribution")
    axes[3].set_xlabel("Profit EUR")
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    plt.tight_layout()
    from optimisation._paths import plot
    out_path = plot("tier_final2_results.png")
    fig.savefig(out_path, dpi=120)
    print(f"Plot saved to: {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    bp = load_battery_params()
    print_battery_params(bp)

    df = load_forecast()
    scenarios = generate_price_scenarios(
        df,
        n_scenarios=Risk.n_scenarios,
        seed=Risk.seed,
    )

    print("Running Tier Final 2 optimisation...")
    schedule, scenario_profits, risk_report = optimize_tier_final2_cvar(df, scenarios, bp)
    naive_schedule = naive_rank_strategy(df, bp)
    metrics = calculate_tier_metrics(schedule, scenarios, bp, naive_schedule=naive_schedule)
    group_metrics = calculate_group_metrics(schedule, scenarios, bp)

    print("\n=== Tier Final 2 CVaR Risk Report ===")
    for k, v in risk_report.items():
        print(f"  {k}: {v:,.4f}")

    print("\n=== Tier Final 2 Comparison Metrics ===")
    for k, v in metrics.items():
        print(f"  {k}: {v:,.4f}")
    print_group_metrics(group_metrics)

    from optimisation._paths import result
    schedule.to_csv(result("tier_final2_schedule.csv"), index=False)
    pd.DataFrame(scenarios).to_csv(result("tier_final2_price_scenarios.csv"), index=False)

    print("\nSaved:")
    print(f"  - {result('tier_final2_schedule.csv')}")
    print(f"  - {result('tier_final2_price_scenarios.csv')}")

    plot_tier_final2_results(schedule, scenarios, scenario_profits, bp)
