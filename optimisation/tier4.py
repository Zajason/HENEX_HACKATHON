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


class PHConfig:
    rho = 3.0
    max_iter = 12
    tolerance = 1e-2
    solver_name = "glpk"


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


# ============================================================
# Scenario tree
# ============================================================

def build_tier4_scenario_tree(df):
    """
    3-stage tree:
      Stage 1: root / day-ahead
      Stage 2: morning regime
      Stage 3: afternoon regime

    3 morning branches x 3 afternoon branches = 9 full scenarios.
    """

    p50 = df["p50_eur_mwh"].to_numpy()
    spread = ((df["p90_eur_mwh"] - df["p10_eur_mwh"]) / 2).to_numpy()

    morning_regimes = {
        "low_morning": -0.45,
        "normal_morning": 0.00,
        "high_morning": 0.45,
    }

    afternoon_regimes = {
        "surplus_afternoon": -0.55,
        "normal_afternoon": 0.00,
        "scarcity_afternoon": 0.85,
    }

    morning_probs = {
        "low_morning": 0.25,
        "normal_morning": 0.50,
        "high_morning": 0.25,
    }

    afternoon_probs = {
        "surplus_afternoon": 0.25,
        "normal_afternoon": 0.50,
        "scarcity_afternoon": 0.25,
    }

    scenarios = []

    T = len(df)
    hours = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60

    morning_mask = (hours >= 8) & (hours < 14)
    afternoon_mask = hours >= 14

    for m_name, m_shift in morning_regimes.items():
        for a_name, a_shift in afternoon_regimes.items():
            prices = p50.copy()

            prices[morning_mask] += m_shift * spread[morning_mask]
            prices[afternoon_mask] += a_shift * spread[afternoon_mask]

            # Add some smooth scenario-specific deviation
            seed = abs(hash(m_name + a_name)) % (2**32)
            rng = np.random.default_rng(seed)
            noise = rng.normal(0, spread * 0.15)

            for t in range(1, T):
                noise[t] = 0.7 * noise[t - 1] + 0.3 * noise[t]

            prices = np.clip(prices + noise, -80, 600)

            prob = morning_probs[m_name] * afternoon_probs[a_name]

            scenarios.append({
                "name": f"{m_name}__{a_name}",
                "morning": m_name,
                "afternoon": a_name,
                "prob": prob,
                "prices": prices,
            })

    return scenarios


def consensus_group(scenario, t):
    """
    Non-anticipativity structure.

    Stage 1:
      t < 32: all scenarios share same decision.

    Stage 2:
      32 <= t < 64: scenarios with same morning branch share decision.

    Stage 3:
      t >= 64: scenario-specific recourse; no consensus.
    """

    if t < 32:
        return ("root", t)

    if t < 64:
        return ("morning", scenario["morning"], t)

    return None


# ============================================================
# Scenario subproblem with PH penalties
# ============================================================

def solve_scenario_subproblem(
    scenario,
    xbar,
    multipliers,
    rho,
):
    prices = scenario["prices"]
    T_len = len(prices)
    T = range(T_len)

    model = ConcreteModel()

    model.P_ch = Var(T, domain=NonNegativeReals)
    model.P_dis = Var(T, domain=NonNegativeReals)
    model.E = Var(T, domain=NonNegativeReals)

    model.u_ch = Var(T, domain=Binary)
    model.u_dis = Var(T, domain=Binary)

    # Absolute-deviation variables for linear PH penalty
    model.dev_ch = Var(T, domain=NonNegativeReals)
    model.dev_dis = Var(T, domain=NonNegativeReals)

    # Battery profit
    profit_expr = sum(
        prices[t] * (model.P_dis[t] - model.P_ch[t]) * Battery.dt
        - Battery.c_deg * (model.P_ch[t] + model.P_dis[t]) * Battery.dt
        for t in T
    )

    # PH terms only where non-anticipativity applies
    ph_linear_terms = []
    ph_penalty_terms = []

    for t in T:
        group = consensus_group(scenario, t)
        if group is None:
            continue

        key_ch = (scenario["name"], group, "ch")
        key_dis = (scenario["name"], group, "dis")

        lambda_ch = multipliers.get(key_ch, 0.0)
        lambda_dis = multipliers.get(key_dis, 0.0)

        xbar_ch = xbar.get((group, "ch"), 0.0)
        xbar_dis = xbar.get((group, "dis"), 0.0)

        ph_linear_terms.append(lambda_ch * model.P_ch[t])
        ph_linear_terms.append(lambda_dis * model.P_dis[t])

        # |P_ch - xbar_ch|
        model.add_component(
            f"dev_ch_pos_{t}",
            Constraint(expr=model.dev_ch[t] >= model.P_ch[t] - xbar_ch),
        )
        model.add_component(
            f"dev_ch_neg_{t}",
            Constraint(expr=model.dev_ch[t] >= xbar_ch - model.P_ch[t]),
        )

        # |P_dis - xbar_dis|
        model.add_component(
            f"dev_dis_pos_{t}",
            Constraint(expr=model.dev_dis[t] >= model.P_dis[t] - xbar_dis),
        )
        model.add_component(
            f"dev_dis_neg_{t}",
            Constraint(expr=model.dev_dis[t] >= xbar_dis - model.P_dis[t]),
        )

        ph_penalty_terms.append(rho * model.dev_ch[t])
        ph_penalty_terms.append(rho * model.dev_dis[t])

    model.obj = Objective(
        expr=profit_expr - sum(ph_linear_terms) - sum(ph_penalty_terms),
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

    # No simultaneous charge/discharge
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

    # Terminal SOC
    model.final_soc = Constraint(expr=model.E[T_len - 1] == Battery.E_init)

    # Cycle constraint
    model.cycle_limit = Constraint(
        expr=sum(model.P_dis[t] * Battery.dt for t in T)
        <= Battery.max_cycles * Battery.E_nom
    )

    # Grid limits
    model.grid_import = Constraint(
        T,
        rule=lambda m, t: m.P_ch[t] <= Battery.grid_import_max,
    )

    model.grid_export = Constraint(
        T,
        rule=lambda m, t: m.P_dis[t] <= Battery.grid_export_max,
    )

    solver = SolverFactory(PHConfig.solver_name)
    result = solver.solve(model, tee=False)

    if result.solver.status != SolverStatus.ok:
        raise RuntimeError(result)

    sol = {
        "P_ch": np.array([value(model.P_ch[t]) for t in T]),
        "P_dis": np.array([value(model.P_dis[t]) for t in T]),
        "E": np.array([value(model.E[t]) for t in T]),
    }

    profit = evaluate_profit(sol["P_ch"], sol["P_dis"], prices)

    return sol, profit


# ============================================================
# Progressive Hedging
# ============================================================

def initialize_xbar(scenarios, T_len):
    xbar = {}

    for scenario in scenarios:
        for t in range(T_len):
            group = consensus_group(scenario, t)
            if group is None:
                continue

            xbar[(group, "ch")] = 0.0
            xbar[(group, "dis")] = 0.0

    return xbar


def update_xbar(scenarios, solutions):
    numerator = {}
    denominator = {}

    for scenario in scenarios:
        prob = scenario["prob"]
        name = scenario["name"]
        sol = solutions[name]

        for t in range(len(sol["P_ch"])):
            group = consensus_group(scenario, t)
            if group is None:
                continue

            for var_name, arr_name in [("ch", "P_ch"), ("dis", "P_dis")]:
                key = (group, var_name)

                numerator[key] = numerator.get(key, 0.0) + prob * sol[arr_name][t]
                denominator[key] = denominator.get(key, 0.0) + prob

    xbar = {}

    for key in numerator:
        xbar[key] = numerator[key] / max(denominator[key], 1e-9)

    return xbar


def update_multipliers(scenarios, solutions, xbar, multipliers, rho):
    max_disagreement = 0.0

    for scenario in scenarios:
        name = scenario["name"]
        sol = solutions[name]

        for t in range(len(sol["P_ch"])):
            group = consensus_group(scenario, t)
            if group is None:
                continue

            for var_name, arr_name in [("ch", "P_ch"), ("dis", "P_dis")]:
                key_mult = (name, group, var_name)
                key_xbar = (group, var_name)

                deviation = sol[arr_name][t] - xbar[key_xbar]

                multipliers[key_mult] = multipliers.get(key_mult, 0.0) + rho * deviation

                max_disagreement = max(max_disagreement, abs(deviation))

    return multipliers, max_disagreement


def progressive_hedging(scenarios):
    T_len = len(scenarios[0]["prices"])

    xbar = initialize_xbar(scenarios, T_len)
    multipliers = {}

    all_iteration_logs = []

    for it in range(PHConfig.max_iter):
        print(f"\n[PH ITERATION {it + 1}]")

        solutions = {}
        profits = {}

        for scenario in scenarios:
            sol, profit = solve_scenario_subproblem(
                scenario=scenario,
                xbar=xbar,
                multipliers=multipliers,
                rho=PHConfig.rho,
            )

            solutions[scenario["name"]] = sol
            profits[scenario["name"]] = profit

            print(f"  {scenario['name']}: profit={profit:,.2f}")

        xbar = update_xbar(scenarios, solutions)

        multipliers, max_disagreement = update_multipliers(
            scenarios=scenarios,
            solutions=solutions,
            xbar=xbar,
            multipliers=multipliers,
            rho=PHConfig.rho,
        )

        expected_profit = sum(
            scenario["prob"] * profits[scenario["name"]]
            for scenario in scenarios
        )

        print(f"  Expected scenario profit: {expected_profit:,.2f}")
        print(f"  Max non-anticipativity disagreement: {max_disagreement:.4f}")

        all_iteration_logs.append({
            "iteration": it + 1,
            "expected_profit": expected_profit,
            "max_disagreement": max_disagreement,
        })

        if max_disagreement < PHConfig.tolerance:
            print("\n[PH CONVERGED]")
            break

    return solutions, xbar, pd.DataFrame(all_iteration_logs)


# ============================================================
# Build consensus schedule from PH result
# ============================================================

def build_consensus_schedule(df, scenarios, solutions, xbar):
    """
    Produces one interpretable schedule:
    - Stage 1/2 uses consensus averages
    - Stage 3 uses probability-weighted average of scenario recourse
    """

    T_len = len(df)
    out = df.copy()

    charge = np.zeros(T_len)
    discharge = np.zeros(T_len)

    for t in range(T_len):
        # Try consensus first
        first_group = consensus_group(scenarios[0], t)

        if first_group is not None and t < 32:
            charge[t] = xbar[(first_group, "ch")]
            discharge[t] = xbar[(first_group, "dis")]

        elif t < 64:
            # weighted average across morning branches
            ch_val = 0.0
            dis_val = 0.0
            total_prob = 0.0

            used = set()

            for scenario in scenarios:
                group = consensus_group(scenario, t)

                if group in used:
                    continue

                branch_prob = sum(
                    s["prob"] for s in scenarios
                    if consensus_group(s, t) == group
                )

                ch_val += branch_prob * xbar[(group, "ch")]
                dis_val += branch_prob * xbar[(group, "dis")]
                total_prob += branch_prob

                used.add(group)

            charge[t] = ch_val / max(total_prob, 1e-9)
            discharge[t] = dis_val / max(total_prob, 1e-9)

        else:
            # stage 3 is true recourse, so average across scenarios for visualization
            charge[t] = sum(
                scenario["prob"] * solutions[scenario["name"]]["P_ch"][t]
                for scenario in scenarios
            )
            discharge[t] = sum(
                scenario["prob"] * solutions[scenario["name"]]["P_dis"][t]
                for scenario in scenarios
            )

    out["charge_mw"] = charge
    out["discharge_mw"] = discharge
    out["net_power_mw"] = discharge - charge

    # Reconstruct approximate expected SOC path
    soc = []
    e = Battery.E_init

    for t in range(T_len):
        e = (
            e
            + Battery.eta_ch * charge[t] * Battery.dt
            - discharge[t] * Battery.dt / Battery.eta_dis
        )

        e = min(max(e, Battery.SOC_min), Battery.SOC_max)
        soc.append(e)

    out["soc_mwh"] = soc

    return out


# ============================================================
# Metrics
# ============================================================

def evaluate_profit(P_ch, P_dis, prices):
    return (
        prices * (P_dis - P_ch) * Battery.dt
        - Battery.c_deg * (P_ch + P_dis) * Battery.dt
    ).sum()


def calculate_tier4_metrics(scenarios, solutions):
    profits = []

    for scenario in scenarios:
        name = scenario["name"]
        sol = solutions[name]

        profit = evaluate_profit(
            sol["P_ch"],
            sol["P_dis"],
            scenario["prices"],
        )

        profits.append(profit)

    profits = np.array(profits)
    probs = np.array([s["prob"] for s in scenarios])

    expected_profit = np.sum(probs * profits)

    ordered = np.argsort(profits)
    sorted_profits = profits[ordered]
    sorted_probs = probs[ordered]

    cum_probs = np.cumsum(sorted_probs)
    cvar_mask = cum_probs <= 0.10

    if cvar_mask.sum() == 0:
        cvar_10 = sorted_profits[0]
    else:
        cvar_10 = np.average(sorted_profits[cvar_mask], weights=sorted_probs[cvar_mask])

    return {
        "expected_profit_eur": expected_profit,
        "median_profit_eur": np.median(profits),
        "worst_profit_eur": profits.min(),
        "best_profit_eur": profits.max(),
        "cvar_10_profit_eur": cvar_10,
        "profit_std_eur": profits.std(),
        "scenario_count": len(scenarios),
    }


# ============================================================
# Plotting
# ============================================================

def plot_tier4(df, scenarios, schedule, logs):
    fig, axes = plt.subplots(4, 1, figsize=(15, 15), sharex=False)

    timestamps = df["timestamp"]

    for scenario in scenarios:
        axes[0].plot(
            timestamps,
            scenario["prices"],
            alpha=0.25,
            label=scenario["name"] if scenario["name"].endswith("scarcity_afternoon") else None,
        )

    axes[0].plot(timestamps, df["p50_eur_mwh"], linewidth=2, label="D-1 P50")
    axes[0].fill_between(
        timestamps,
        df["p10_eur_mwh"],
        df["p90_eur_mwh"],
        alpha=0.2,
        label="D-1 P10-P90",
    )
    axes[0].set_title("Tier 4 Scenario Tree Price Paths")
    axes[0].set_ylabel("€/MWh")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].bar(timestamps, schedule["charge_mw"], width=0.008, label="Charge")
    axes[1].bar(timestamps, -schedule["discharge_mw"], width=0.008, label="Discharge")
    axes[1].set_title("Consensus / Expected Recourse Dispatch")
    axes[1].set_ylabel("MW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(timestamps, schedule["soc_mwh"], label="SOC")
    axes[2].axhline(Battery.SOC_min, linestyle="--", label="SOC min")
    axes[2].axhline(Battery.SOC_max, linestyle="--", label="SOC max")
    axes[2].set_title("Expected SOC Path")
    axes[2].set_ylabel("MWh")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    axes[3].plot(logs["iteration"], logs["max_disagreement"], marker="o")
    axes[3].set_title("Progressive Hedging Convergence")
    axes[3].set_xlabel("Iteration")
    axes[3].set_ylabel("Max disagreement")
    axes[3].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    df = load_forecast("synthetic_forecast_day.csv")

    scenarios = build_tier4_scenario_tree(df)

    print("\nScenario tree:")
    for s in scenarios:
        print(f"{s['name']} | probability={s['prob']:.3f}")

    solutions, xbar, logs = progressive_hedging(scenarios)

    schedule = build_consensus_schedule(df, scenarios, solutions, xbar)

    metrics = calculate_tier4_metrics(scenarios, solutions)

    print("\n=== Tier 4 Progressive Hedging Metrics ===")
    for k, v in metrics.items():
        print(f"{k}: {v:,.2f}")

    schedule.to_csv("tier4_progressive_hedging_schedule.csv", index=False)
    logs.to_csv("tier4_progressive_hedging_logs.csv", index=False)

    print("\nSaved:")
    print("- tier4_progressive_hedging_schedule.csv")
    print("- tier4_progressive_hedging_logs.csv")

    plot_tier4(df, scenarios, schedule, logs)