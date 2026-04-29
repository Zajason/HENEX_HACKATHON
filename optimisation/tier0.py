import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pyomo.environ import *


# ============================================================
# CONFIG (your exact assumptions)
# ============================================================

class Battery:
    P_nom = 75
    E_nom = 300
    dt = 0.25

    eta_ch = 0.95
    eta_dis = 0.95

    SOC_min = 0.10 * E_nom
    SOC_max = 0.90 * E_nom

    E_init = 0.50 * E_nom

    c_deg = 10  # €/MWh
    max_cycles = 2

    grid_limit = 75

    lambda_risk = 0.35  # Tier 0 risk buffer


# ============================================================
# LOAD DATA
# ============================================================

def load_data(path=None):
    if path is None:
        from optimisation._paths import synthetic
        path = synthetic("synthetic_forecast_day.csv")
    df = pd.read_csv(path, parse_dates=["timestamp"])

    df["uncertainty"] = (df["p90_eur_mwh"] - df["p10_eur_mwh"]) / 2

    # Tier 0 risk-adjusted price
    df["price_eff"] = df["p50_eur_mwh"] - Battery.lambda_risk * df["uncertainty"]

    return df


# ============================================================
# OPTIMIZATION MODEL
# ============================================================

def optimize_battery(df):

    T = range(len(df))

    model = ConcreteModel()

    # VARIABLES
    model.P_ch = Var(T, domain=NonNegativeReals)
    model.P_dis = Var(T, domain=NonNegativeReals)
    model.E = Var(T, domain=NonNegativeReals)

    model.u_ch = Var(T, domain=Binary)
    model.u_dis = Var(T, domain=Binary)

    # --------------------------------------------------------
    # OBJECTIVE
    # --------------------------------------------------------
    def objective(m):
        return sum(
            df.loc[t, "price_eff"] * (m.P_dis[t] - m.P_ch[t]) * Battery.dt
            - Battery.c_deg * (m.P_ch[t] + m.P_dis[t]) * Battery.dt
            for t in T
        )

    model.obj = Objective(rule=objective, sense=maximize)

    # --------------------------------------------------------
    # CONSTRAINTS
    # --------------------------------------------------------

    # Power limits
    def charge_limit(m, t):
        return m.P_ch[t] <= Battery.P_nom * m.u_ch[t]

    def discharge_limit(m, t):
        return m.P_dis[t] <= Battery.P_nom * m.u_dis[t]

    model.charge_limit = Constraint(T, rule=charge_limit)
    model.discharge_limit = Constraint(T, rule=discharge_limit)

    # No simultaneous charge/discharge
    def no_simultaneous(m, t):
        return m.u_ch[t] + m.u_dis[t] <= 1

    model.no_simultaneous = Constraint(T, rule=no_simultaneous)

    # SOC dynamics
    def soc_rule(m, t):
        if t == 0:
            return m.E[t] == Battery.E_init \
                + Battery.eta_ch * m.P_ch[t] * Battery.dt \
                - (m.P_dis[t] / Battery.eta_dis) * Battery.dt
        else:
            return m.E[t] == m.E[t-1] \
                + Battery.eta_ch * m.P_ch[t] * Battery.dt \
                - (m.P_dis[t] / Battery.eta_dis) * Battery.dt

    model.soc = Constraint(T, rule=soc_rule)

    # SOC bounds
    def soc_min(m, t):
        return m.E[t] >= Battery.SOC_min

    def soc_max(m, t):
        return m.E[t] <= Battery.SOC_max

    model.soc_min = Constraint(T, rule=soc_min)
    model.soc_max = Constraint(T, rule=soc_max)

    # Terminal SOC
    model.final_soc = Constraint(expr=model.E[len(df)-1] == Battery.E_init)

    # Cycle constraint
    def cycle_limit(m):
        return sum(m.P_dis[t] * Battery.dt for t in T) <= Battery.max_cycles * Battery.E_nom

    model.cycle_limit = Constraint(rule=cycle_limit)

    # Grid limits
    def grid_import(m, t):
        return m.P_ch[t] <= Battery.grid_limit

    def grid_export(m, t):
        return m.P_dis[t] <= Battery.grid_limit

    model.grid_import = Constraint(T, rule=grid_import)
    model.grid_export = Constraint(T, rule=grid_export)

    # --------------------------------------------------------
    # SOLVE
    # --------------------------------------------------------
    solver = SolverFactory("glpk")
    solver.solve(model)

    # --------------------------------------------------------
    # EXTRACT RESULTS
    # --------------------------------------------------------
    df["charge_mw"] = [value(model.P_ch[t]) for t in T]
    df["discharge_mw"] = [value(model.P_dis[t]) for t in T]
    df["soc_mwh"] = [value(model.E[t]) for t in T]

    return df


# ============================================================
# METRICS (VERY IMPORTANT FOR TIERS)
# ============================================================

def evaluate(df):

    dt = Battery.dt

    revenue = (df["discharge_mw"] * df["p50_eur_mwh"] * dt).sum()
    cost = (df["charge_mw"] * df["p50_eur_mwh"] * dt).sum()

    throughput = ((df["charge_mw"] + df["discharge_mw"]) * dt).sum()

    degradation = throughput * Battery.c_deg

    profit = revenue - cost - degradation

    cycles = throughput / (2 * Battery.E_nom)

    return {
        "profit (€)": profit,
        "revenue (€)": revenue,
        "energy_cost (€)": cost,
        "throughput (MWh)": throughput,
        "cycles": cycles,
        "profit_per_MWh": profit / throughput if throughput > 0 else 0,
    }


# ============================================================
# PLOTS
# ============================================================

def plot_results(df):

    fig, ax = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    # Price
    ax[0].plot(df["timestamp"], df["p50_eur_mwh"])
    ax[0].fill_between(df["timestamp"], df["p10_eur_mwh"], df["p90_eur_mwh"], alpha=0.2)
    ax[0].set_title("Price")

    # Power
    ax[1].bar(df["timestamp"], df["charge_mw"], label="charge")
    ax[1].bar(df["timestamp"], -df["discharge_mw"], label="discharge")
    ax[1].legend()
    ax[1].set_title("Dispatch")

    # SOC
    ax[2].plot(df["timestamp"], df["soc_mwh"])
    ax[2].set_title("SOC")

    plt.tight_layout()
    plt.show()
def run_tier(df):
    """
    Standard interface so test_tiers.py can call this tier.
    """

    # --- YOUR EXISTING LOGIC HERE ---
    # Replace this part depending on tier

    schedule = naive_rank_strategy(df)   # example (Tier 0/1)

    profit = evaluate_schedule_on_prices(
        schedule,
        df["p50_eur_mwh"].to_numpy()
    )

    # Return %
    capital = 1_750_000  # or whatever you use globally
    ret = 100 * profit / capital

    return {
        "profit_eur": float(profit),
        "return_pct": float(ret),
        "schedule": schedule,
    }

 
# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    df = load_data()
    df = optimize_battery(df)

    metrics = evaluate(df)

    print("\n=== Tier 0 Results ===")
    for k, v in metrics.items():
        print(k, ":", round(v, 2))

    plot_results(df)

    from optimisation._paths import result
    df.to_csv(result("tier0_results.csv"), index=False)