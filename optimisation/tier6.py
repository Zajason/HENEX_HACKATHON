"""
Tier 6 — DAM + Synthetic Intraday MPC / Rolling-Horizon BESS Optimizer
======================================================================

This script uses:
    1. synthetic_forecast_day.csv as the DAM forecast curve
    2. synthetic_intraday_curve_from_dam.csv as the synthetic intraday curve

It runs:
    Stage 1: DAM one-shot MILP schedule
    Stage 2: Intraday MPC / rolling-horizon re-optimization

Battery base case:
    75 MW / 300 MWh, 4-hour BESS
    SOC range: 10%–90%
    Initial/final SOC: 50%
    eta_ch = eta_dis = 0.95
    degradation = 10 EUR/MWh throughput
    max cycles/day = 2

Market accounting:
    - DAM schedule creates the initial committed position q_DAM[t]
    - MPC creates final physical position q_MPC[t]
    - Simplified intraday adjustment is:
          delta_q_ID[t] = q_MPC[t] - q_DAM[t]
    - Total market revenue is:
          DAM_price[t] * q_DAM[t] * dt
        + ID_price[t]  * delta_q_ID[t] * dt
    - Degradation cost is charged on actual MPC physical throughput.

Important:
    This is a synthetic intraday simulation, not a real intraday backtest.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pyomo.environ import *


# ============================================================
# CONFIG
# ============================================================

DAM_FILE = "synthetic_forecast_day.csv"
INTRADAY_FILE = "synthetic_intraday_curve_from_dam.csv"

OUTPUT_SCHEDULE = "tier6_mpc_intraday_schedule.csv"
OUTPUT_SUMMARY = "tier6_mpc_intraday_summary.csv"
OUTPUT_PLOT = "tier6_mpc_intraday_plot.png"


class Battery:
    P_nom = 75.0
    E_nom = 300.0
    dt = 0.25

    eta_ch = 0.95
    eta_dis = 0.95

    SOC_min = 0.10 * E_nom
    SOC_max = 0.90 * E_nom
    E_init = 0.50 * E_nom

    c_deg = 10.0  # EUR/MWh throughput

    max_cycles = 2.0
    grid_import_max = 75.0
    grid_export_max = 75.0


class MPC:
    # Use remaining-day rolling horizon by default.
    # If horizon_steps=96, at each step we optimize from now to end of day.
    horizon_steps = 96

    # Enforce E_end = E_init whenever the horizon reaches the end of the day.
    enforce_end_of_day_soc = True

    # Track already used throughput so daily cycle limit is respected.
    use_remaining_throughput_limit = True


# ============================================================
# DATA LOADING
# ============================================================

def load_dam_and_intraday(
    dam_path=DAM_FILE,
    intraday_path=INTRADAY_FILE,
):
    dam = pd.read_csv(dam_path, parse_dates=["timestamp"])
    intraday = pd.read_csv(intraday_path, parse_dates=["timestamp"])

    dam = dam.sort_values("timestamp").reset_index(drop=True)
    intraday = intraday.sort_values("timestamp").reset_index(drop=True)
    if "hour" not in dam.columns:
     dam["hour"] = dam["timestamp"].dt.hour + dam["timestamp"].dt.minute / 60

    if "p50_eur_mwh" not in dam.columns:
        raise ValueError(
            f"DAM file must contain 'p50_eur_mwh'. Found: {list(dam.columns)}"
        )

    id_price_col = detect_intraday_price_column(intraday)

    df = dam[["timestamp", "hour", "p50_eur_mwh"]].copy()
    df = df.rename(columns={"p50_eur_mwh": "dam_price_eur_mwh"})

    intraday_small = intraday[["timestamp", id_price_col]].copy()
    intraday_small = intraday_small.rename(columns={id_price_col: "intraday_price_eur_mwh"})

    df = df.merge(intraday_small, on="timestamp", how="left")

    if df["intraday_price_eur_mwh"].isna().any():
        missing = df[df["intraday_price_eur_mwh"].isna()]
        raise ValueError(
            "Some timestamps in DAM file do not match intraday file. "
            f"Missing rows: {len(missing)}"
        )

    df["dt_hours"] = Battery.dt

    return df


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


# ============================================================
# CORE MILP SOLVER
# ============================================================

def solve_bess_milp(
    prices,
    current_soc,
    terminal_soc=None,
    throughput_limit=None,
    solver_name="glpk",
):
    """
    Solves a BESS MILP over a given horizon.

    Variables per interval:
        P_ch[t], P_dis[t], E[t], u_ch[t], u_dis[t]

    E[t] is energy stored at the END of interval t.
    """

    prices = np.asarray(prices, dtype=float)
    T_len = len(prices)
    T = range(T_len)

    if T_len == 0:
        raise ValueError("Empty MILP horizon.")

    m = ConcreteModel()

    # Variables
    m.P_ch = Var(T, domain=NonNegativeReals)
    m.P_dis = Var(T, domain=NonNegativeReals)
    m.E = Var(T, domain=NonNegativeReals)

    m.u_ch = Var(T, domain=Binary)
    m.u_dis = Var(T, domain=Binary)

    # Objective
    def objective_rule(model):
        return sum(
            prices[t] * (model.P_dis[t] - model.P_ch[t]) * Battery.dt
            - Battery.c_deg * (model.P_ch[t] + model.P_dis[t]) * Battery.dt
            for t in T
        )

    m.obj = Objective(rule=objective_rule, sense=maximize)

    # Power + mode constraints
    m.charge_limit = Constraint(
        T,
        rule=lambda model, t: model.P_ch[t] <= min(Battery.P_nom, Battery.grid_import_max) * model.u_ch[t],
    )

    m.discharge_limit = Constraint(
        T,
        rule=lambda model, t: model.P_dis[t] <= min(Battery.P_nom, Battery.grid_export_max) * model.u_dis[t],
    )

    m.no_simultaneous = Constraint(
        T,
        rule=lambda model, t: model.u_ch[t] + model.u_dis[t] <= 1,
    )

    # SOC dynamics
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

    # Optional terminal SOC
    if terminal_soc is not None:
        m.final_soc = Constraint(expr=m.E[T_len - 1] == terminal_soc)

    # Optional throughput limit
    # Throughput-based cycles:
    # sum((P_ch + P_dis)dt) <= 2 * cycles * E_nom
    if throughput_limit is not None:
        m.throughput_limit = Constraint(
            expr=sum((m.P_ch[t] + m.P_dis[t]) * Battery.dt for t in T)
            <= throughput_limit
        )

    # Solve
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
# STAGE 1 — DAM ONE-SHOT SCHEDULE
# ============================================================

def run_dam_schedule(df):
    prices = df["dam_price_eur_mwh"].to_numpy(dtype=float)

    daily_throughput_limit = 2 * Battery.max_cycles * Battery.E_nom

    sol = solve_bess_milp(
        prices=prices,
        current_soc=Battery.E_init,
        terminal_soc=Battery.E_init,
        throughput_limit=daily_throughput_limit,
    )

    out = df.copy()
    out["dam_charge_mw"] = sol["charge_mw"]
    out["dam_discharge_mw"] = sol["discharge_mw"]
    out["dam_net_mw"] = sol["net_power_mw"]
    out["dam_soc_mwh"] = sol["soc_mwh"]
    out["dam_profit_eur"] = sol["profit_eur"]

    return out


# ============================================================
# STAGE 2 — INTRADAY MPC / ROLLING HORIZON
# ============================================================

def run_intraday_mpc(df):
    """
    Rolling-horizon MPC using intraday prices.

    At each interval k:
        - observe current SOC
        - solve MILP from k to end/horizon
        - execute only first action
        - update SOC and throughput used
    """

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

        # Execute only the first action
        charge_now = float(sol["charge_mw"][0])
        discharge_now = float(sol["discharge_mw"][0])

        # Numerical cleanup
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
            "mpc_remaining_throughput_mwh": max(0.0, daily_throughput_limit - throughput_used),
        })

        soc_current = soc_next

    mpc = pd.DataFrame(rows)
    out = pd.concat([df.reset_index(drop=True), mpc], axis=1)

    return out


# ============================================================
# MARKET ACCOUNTING
# ============================================================

def add_market_accounting(df):
    """
    Simplified DAM + intraday settlement.

    q_DAM[t] = initial committed position from DAM schedule.
    q_MPC[t] = final physical position from MPC.
    delta_ID[t] = q_MPC[t] - q_DAM[t].

    Revenue:
        DAM_price * q_DAM * dt
      + ID_price * delta_ID * dt

    Degradation:
        c_deg * actual MPC throughput
    """

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

    out["tier6_total_profit_eur"] = (
        out["dam_market_revenue_eur"]
        + out["intraday_adjustment_revenue_eur"]
        - out["mpc_degradation_cost_eur"]
    )

    # DAM-only profit evaluated on DAM schedule and DAM prices
    out["dam_only_profit_eur"] = (
        out["dam_price_eur_mwh"] * out["dam_net_mw"] * Battery.dt
        - Battery.c_deg
        * (out["dam_charge_mw"] + out["dam_discharge_mw"])
        * Battery.dt
    )

    # DAM schedule physically evaluated at intraday prices, for comparison
    out["dam_schedule_on_intraday_profit_eur"] = (
        out["intraday_price_eur_mwh"] * out["dam_net_mw"] * Battery.dt
        - Battery.c_deg
        * (out["dam_charge_mw"] + out["dam_discharge_mw"])
        * Battery.dt
    )

    # Pure MPC profit if no DAM commitment existed, just for control benchmark
    out["pure_mpc_intraday_profit_eur"] = (
        out["intraday_price_eur_mwh"] * out["mpc_net_mw"] * Battery.dt
        - out["mpc_degradation_cost_eur"]
    )

    # Energy per 15-min interval
    out["dam_net_mwh"] = out["dam_net_mw"] * Battery.dt
    out["mpc_net_mwh"] = out["mpc_net_mw"] * Battery.dt
    out["id_adjustment_mwh"] = out["id_adjustment_mw"] * Battery.dt

    out["mpc_charge_mwh_grid"] = out["mpc_charge_mw"] * Battery.dt
    out["mpc_discharge_mwh_grid"] = out["mpc_discharge_mw"] * Battery.dt

    out["mpc_charge_mwh_stored"] = Battery.eta_ch * out["mpc_charge_mw"] * Battery.dt
    out["mpc_discharge_mwh_from_battery"] = out["mpc_discharge_mw"] * Battery.dt / Battery.eta_dis

    out["mpc_action"] = np.where(
        out["mpc_charge_mw"] > 1e-6,
        "charge",
        np.where(out["mpc_discharge_mw"] > 1e-6, "discharge", "idle"),
    )

    return out


def summarize(df):
    total_dam_only = df["dam_only_profit_eur"].sum()
    total_dam_on_id = df["dam_schedule_on_intraday_profit_eur"].sum()
    total_tier6 = df["tier6_total_profit_eur"].sum()
    total_pure_mpc = df["pure_mpc_intraday_profit_eur"].sum()

    mpc_throughput = (
        (df["mpc_charge_mw"] + df["mpc_discharge_mw"]) * Battery.dt
    ).sum()

    dam_throughput = (
        (df["dam_charge_mw"] + df["dam_discharge_mw"]) * Battery.dt
    ).sum()

    summary = {
        "dam_only_profit_eur": total_dam_only,
        "dam_schedule_on_intraday_profit_eur": total_dam_on_id,
        "tier6_dam_plus_intraday_adjustment_profit_eur": total_tier6,
        "pure_mpc_intraday_profit_eur_control_benchmark": total_pure_mpc,
        "increment_vs_dam_only_eur": total_tier6 - total_dam_only,
        "increment_vs_dam_schedule_on_intraday_eur": total_tier6 - total_dam_on_id,
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

    axes[0].plot(ts, df["dam_price_eur_mwh"], label="DAM")
    axes[0].plot(ts, df["intraday_price_eur_mwh"], label="Synthetic intraday", alpha=0.85)
    axes[0].set_title("DAM vs Synthetic Intraday Price")
    axes[0].set_ylabel("€/MWh")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].bar(ts, df["dam_charge_mw"], width=0.008, label="DAM charge", alpha=0.6)
    axes[1].bar(ts, -df["dam_discharge_mw"], width=0.008, label="DAM discharge", alpha=0.6)
    axes[1].set_title("Stage 1 DAM Schedule")
    axes[1].set_ylabel("MW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].bar(ts, df["mpc_charge_mw"], width=0.008, label="MPC charge", alpha=0.6)
    axes[2].bar(ts, -df["mpc_discharge_mw"], width=0.008, label="MPC discharge", alpha=0.6)
    axes[2].set_title("Stage 2 Intraday MPC Physical Dispatch")
    axes[2].set_ylabel("MW")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    axes[3].plot(ts, df["dam_soc_mwh"], label="DAM SOC")
    axes[3].plot(ts, df["mpc_soc_mwh"], label="MPC SOC")
    axes[3].axhline(Battery.SOC_min, linestyle="--", alpha=0.6, label="SOC min")
    axes[3].axhline(Battery.SOC_max, linestyle="--", alpha=0.6, label="SOC max")
    axes[3].set_title("State of Charge")
    axes[3].set_ylabel("MWh")
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    axes[4].plot(ts, df["tier6_total_profit_eur"].cumsum(), label="Tier 6 DAM + ID adjustment")
    axes[4].plot(ts, df["dam_only_profit_eur"].cumsum(), label="DAM-only")
    axes[4].plot(ts, df["pure_mpc_intraday_profit_eur"].cumsum(), label="Pure MPC intraday benchmark")
    axes[4].set_title("Cumulative Profit")
    axes[4].set_ylabel("€")
    axes[4].legend()
    axes[4].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT, dpi=150)
    plt.show()


def run_tier(
    forecast_csv: str,
    capital_base_eur: float | None = None,
    intraday_csv: str = INTRADAY_FILE,
) -> dict:
    df = load_dam_and_intraday(
        dam_path=forecast_csv,
        intraday_path=intraday_csv,
    )

    dam_df = run_dam_schedule(df)
    mpc_df = run_intraday_mpc(dam_df)
    result_df = add_market_accounting(mpc_df)
    summary_df = summarize(result_df)

    metrics = summary_df.iloc[0].to_dict()

    # Needed by run_all_tiers.py
    metrics["expected_profit_eur"] = metrics["tier6_dam_plus_intraday_adjustment_profit_eur"]
    metrics["realized_profit_eur"] = metrics["tier6_dam_plus_intraday_adjustment_profit_eur"]
    metrics["profit_eur"] = metrics["tier6_dam_plus_intraday_adjustment_profit_eur"]

    return metrics

# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    print("Loading DAM and synthetic intraday data...")
    df = load_dam_and_intraday(DAM_FILE, INTRADAY_FILE)

    print("Running Stage 1: DAM one-shot MILP...")
    dam_df = run_dam_schedule(df)

    print("Running Stage 2: Intraday MPC / rolling horizon...")
    mpc_df = run_intraday_mpc(dam_df)

    print("Adding simplified market accounting...")
    result_df = add_market_accounting(mpc_df)

    summary_df = summarize(result_df)

    print("\n=== Tier 6 Summary ===")
    for col in summary_df.columns:
        print(f"{col}: {summary_df.loc[0, col]:,.2f}")

    result_df.to_csv(OUTPUT_SCHEDULE, index=False)
    summary_df.to_csv(OUTPUT_SUMMARY, index=False)

    print("\nSaved:")
    print(f"- {OUTPUT_SCHEDULE}")
    print(f"- {OUTPUT_SUMMARY}")
    print(f"- {OUTPUT_PLOT}")

    plot_results(result_df)
