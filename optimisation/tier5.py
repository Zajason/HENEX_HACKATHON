import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pyomo.environ import (
    ConcreteModel,
    Var,
    Constraint,
    Objective,
    NonNegativeReals,
    Reals,
    SolverFactory,
    SolverStatus,
    maximize,
    value,
)


# ============================================================
# Battery config (ίδιο με Tier 1)
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


class Robust:
    # "box"     -> protect against any realization in [pi_lo, pi_hi]
    # "budget"  -> Bertsimas-Sim: only Gamma MTUs allowed to deviate at once
    uncertainty_type = "budget"
    gamma = 10.0  # ~ sqrt(96)

    quantile_low = "p10_eur_mwh"
    quantile_high = "p90_eur_mwh"
    quantile_med = "p50_eur_mwh"


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

    return df


def build_uncertainty_set(df):
    """
    Box uncertainty: pi_t in [p10, p90].
    center  = (p_lo + p_hi) / 2
    half_w  = (p_hi - p_lo) / 2

    Worst-case profit (closed form for box):
        sum_t [ center_t * net_t  -  half_w_t * |net_t| ] * dt - C_deg
    """
    p_lo = df[Robust.quantile_low].to_numpy()
    p_hi = df[Robust.quantile_high].to_numpy()
    p_med = df[Robust.quantile_med].to_numpy()

    center = 0.5 * (p_lo + p_hi)
    half_width = np.maximum(0.5 * (p_hi - p_lo), 1e-9)

    return {
        "p_lo": p_lo,
        "p_hi": p_hi,
        "p_med": p_med,
        "center": center,
        "half_width": half_width,
    }


# ============================================================
# Tier 5 Robust LP
# ============================================================

def optimize_tier5_robust(df, robust_cfg=Robust):
    unc = build_uncertainty_set(df)
    center = unc["center"]
    half_w = unc["half_width"]

    T_len = len(df)
    T = range(T_len)

    model = ConcreteModel()

    # Battery decisions
    model.P_ch = Var(T, domain=NonNegativeReals)
    model.P_dis = Var(T, domain=NonNegativeReals)
    model.E = Var(T, domain=NonNegativeReals)

    # Auxiliary for |net_t| linearization
    model.abs_net = Var(T, domain=NonNegativeReals)

    # --- absolute value linearization ---
    def abs_pos(m, t):
        return m.abs_net[t] >= (m.P_dis[t] - m.P_ch[t])

    def abs_neg(m, t):
        return m.abs_net[t] >= (m.P_ch[t] - m.P_dis[t])

    model.abs_pos = Constraint(T, rule=abs_pos)
    model.abs_neg = Constraint(T, rule=abs_neg)

    # --- Robust objective ---
    if robust_cfg.uncertainty_type == "box":
        # Static box: every MTU can hit worst-case independently
        def robust_obj(m):
            revenue = sum(
                center[t] * (m.P_dis[t] - m.P_ch[t]) * Battery.dt
                for t in T
            )
            worst_case_loss = sum(
                half_w[t] * m.abs_net[t] * Battery.dt
                for t in T
            )
            degradation = sum(
                Battery.c_deg * (m.P_ch[t] + m.P_dis[t]) * Battery.dt
                for t in T
            )
            return revenue - worst_case_loss - degradation

        model.obj = Objective(rule=robust_obj, sense=maximize)

    elif robust_cfg.uncertainty_type == "budget":
        # Bertsimas-Sim: only Gamma MTUs at once
        # Dual reformulation:
        #   max  Σ center * net * dt  -  Γ*λ  -  Σ z_t  -  C_deg
        #   s.t. λ + z_t >= half_w_t * |net_t| * dt
        #        λ >= 0, z_t >= 0
        model.lam = Var(domain=NonNegativeReals)
        model.z = Var(T, domain=NonNegativeReals)

        def budget_dual(m, t):
            return m.lam + m.z[t] >= half_w[t] * m.abs_net[t] * Battery.dt

        model.budget_dual = Constraint(T, rule=budget_dual)

        def robust_obj(m):
            revenue = sum(
                center[t] * (m.P_dis[t] - m.P_ch[t]) * Battery.dt
                for t in T
            )
            worst_case_loss = robust_cfg.gamma * m.lam + sum(m.z[t] for t in T)
            degradation = sum(
                Battery.c_deg * (m.P_ch[t] + m.P_dis[t]) * Battery.dt
                for t in T
            )
            return revenue - worst_case_loss - degradation

        model.obj = Objective(rule=robust_obj, sense=maximize)

    else:
        raise ValueError(f"Unknown uncertainty_type: {robust_cfg.uncertainty_type}")

    # --- Standard battery constraints (όπως Tier 1) ---
    def charge_limit(m, t):
        return m.P_ch[t] <= Battery.P_nom

    def discharge_limit(m, t):
        return m.P_dis[t] <= Battery.P_nom

    model.charge_limit = Constraint(T, rule=charge_limit)
    model.discharge_limit = Constraint(T, rule=discharge_limit)

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

    # --- Solve ---
    solver = SolverFactory("appsi_highs")
    result = solver.solve(model, tee=False)

    if result.solver.status != SolverStatus.ok:
        raise RuntimeError(result)

    # --- Extract schedule ---
    out = df.copy()
    out["charge_mw"] = [value(model.P_ch[t]) for t in T]
    out["discharge_mw"] = [value(model.P_dis[t]) for t in T]
    out["soc_mwh"] = [value(model.E[t]) for t in T]
    out["net_power_mw"] = out["discharge_mw"] - out["charge_mw"]

    eps = 1e-3
    out["decision"] = "idle"
    out.loc[out["charge_mw"] > eps, "decision"] = "charge"
    out.loc[out["discharge_mw"] > eps, "decision"] = "discharge"

    return out, model, unc


# ============================================================
# Reporting
# ============================================================

def evaluate_schedule(schedule, prices, label):
    """Realized profit για ένα schedule σε δοθείσες τιμές.

    Επιστρέφει:
      - cost_of_energy_bought_eur: αξία ενέργειας που αγοράσαμε (charging spend)
      - revenue_from_energy_sold_eur: έσοδα από εκφόρτιση
      - degradation_eur: κόστος degradation
      - profit_eur: net profit
      - return_on_cost_pct: profit / cost_of_energy_bought * 100
      - return_on_throughput_eur_per_mwh: profit / throughput
    """
    charge = schedule["charge_mw"].to_numpy()
    discharge = schedule["discharge_mw"].to_numpy()
    prices = np.asarray(prices)

    energy_bought_mwh = float(charge.sum() * Battery.dt)
    energy_sold_mwh = float(discharge.sum() * Battery.dt)
    throughput = energy_bought_mwh + energy_sold_mwh

    cost_of_energy_bought = float(np.sum(prices * charge) * Battery.dt)
    revenue_from_energy_sold = float(np.sum(prices * discharge) * Battery.dt)
    deg = float(Battery.c_deg * throughput)
    profit = revenue_from_energy_sold - cost_of_energy_bought - deg

    if cost_of_energy_bought > 1e-6:
        return_on_cost_pct = 100.0 * profit / cost_of_energy_bought
    else:
        return_on_cost_pct = float("nan")

    if throughput > 1e-6:
        return_per_mwh = profit / throughput
        avg_buy_price = cost_of_energy_bought / energy_bought_mwh if energy_bought_mwh > 1e-6 else float("nan")
        avg_sell_price = revenue_from_energy_sold / energy_sold_mwh if energy_sold_mwh > 1e-6 else float("nan")
    else:
        return_per_mwh = float("nan")
        avg_buy_price = float("nan")
        avg_sell_price = float("nan")

    return {
        "scenario": label,
        "energy_bought_mwh": energy_bought_mwh,
        "energy_sold_mwh": energy_sold_mwh,
        "cost_of_energy_bought_eur": cost_of_energy_bought,
        "revenue_from_energy_sold_eur": revenue_from_energy_sold,
        "degradation_eur": deg,
        "profit_eur": profit,
        "return_on_cost_pct": return_on_cost_pct,
        "return_per_mwh_throughput_eur": return_per_mwh,
        "avg_buy_price_eur_mwh": avg_buy_price,
        "avg_sell_price_eur_mwh": avg_sell_price,
    }


def report_metrics(schedule, unc, robust_cfg):
    p_lo = unc["p_lo"]
    p_hi = unc["p_hi"]
    p_med = unc["p_med"]

    net = schedule["discharge_mw"].to_numpy() - schedule["charge_mw"].to_numpy()

    # Worst-case price realization (adversary)
    pi_worst = np.where(net >= 0, p_lo, p_hi)
    # Best-case price realization
    pi_best = np.where(net >= 0, p_hi, p_lo)

    profit_p50 = evaluate_schedule(schedule, p_med, "expected_p50")
    profit_worst = evaluate_schedule(schedule, pi_worst, "worst_case")
    profit_best = evaluate_schedule(schedule, pi_best, "best_case")

    throughput = (schedule["charge_mw"] + schedule["discharge_mw"]).sum() * Battery.dt
    cycles = (schedule["discharge_mw"].sum() * Battery.dt) / Battery.E_nom

    active = ((schedule["charge_mw"] > 1e-3) | (schedule["discharge_mw"] > 1e-3)).sum()
    idle = len(schedule) - active

    return {
        "uncertainty_type": robust_cfg.uncertainty_type,
        "gamma_used": robust_cfg.gamma if robust_cfg.uncertainty_type == "budget" else None,

        # Profit (3 σενάρια)
        "expected_profit_eur": profit_p50["profit_eur"],
        "worst_case_profit_eur": profit_worst["profit_eur"],
        "best_case_profit_eur": profit_best["profit_eur"],
        "robust_buffer_eur": profit_p50["profit_eur"] - profit_worst["profit_eur"],

        # Cost / αξία ενέργειας που αγοράσαμε (charging spend)
        "energy_bought_mwh": profit_p50["energy_bought_mwh"],
        "energy_sold_mwh": profit_p50["energy_sold_mwh"],
        "cost_of_energy_bought_eur_p50": profit_p50["cost_of_energy_bought_eur"],
        "cost_of_energy_bought_eur_worst": profit_worst["cost_of_energy_bought_eur"],
        "cost_of_energy_bought_eur_best": profit_best["cost_of_energy_bought_eur"],
        "revenue_from_energy_sold_eur_p50": profit_p50["revenue_from_energy_sold_eur"],
        "revenue_from_energy_sold_eur_worst": profit_worst["revenue_from_energy_sold_eur"],
        "revenue_from_energy_sold_eur_best": profit_best["revenue_from_energy_sold_eur"],

        # Avg prices
        "avg_buy_price_eur_mwh_p50": profit_p50["avg_buy_price_eur_mwh"],
        "avg_sell_price_eur_mwh_p50": profit_p50["avg_sell_price_eur_mwh"],

        # Ποσοστιαία απόδοση (return on cost)
        "return_on_cost_pct_p50": profit_p50["return_on_cost_pct"],
        "return_on_cost_pct_worst": profit_worst["return_on_cost_pct"],
        "return_on_cost_pct_best": profit_best["return_on_cost_pct"],

        # Per-MWh return
        "return_per_mwh_throughput_eur_p50": profit_p50["return_per_mwh_throughput_eur"],

        # Operational
        "throughput_mwh": float(throughput),
        "equivalent_cycles": float(cycles),
        "active_intervals": int(active),
        "idle_intervals": int(idle),
        "min_soc_mwh": float(schedule["soc_mwh"].min()),
        "max_soc_mwh": float(schedule["soc_mwh"].max()),
    }


# ============================================================
# Plot
# ============================================================

def plot_schedule(schedule, unc, title="Tier 5 — Robust schedule"):
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

    ax1 = axes[0]
    ax1.fill_between(
        schedule["timestamp"],
        unc["p_lo"], unc["p_hi"],
        alpha=0.20, label="P10–P90 uncertainty band",
    )
    ax1.plot(schedule["timestamp"], unc["p_med"], linewidth=1.8, label="P50 (point forecast)")
    ax1.set_ylabel("Price (€/MWh)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)
    ax1.set_title(title)

    ax2 = axes[1]
    ax2.bar(schedule["timestamp"], schedule["charge_mw"], width=0.01,
            label="Charge", alpha=0.8)
    ax2.bar(schedule["timestamp"], -schedule["discharge_mw"], width=0.01,
            label="Discharge", alpha=0.8)
    ax2.axhline(0, color="black", linewidth=0.5)
    ax2.set_ylabel("Power (MW)")
    ax2.legend(loc="upper left")
    ax2.grid(True, alpha=0.3)

    ax3 = axes[2]
    ax3.plot(schedule["timestamp"], schedule["soc_mwh"], linewidth=1.8, label="SOC")
    ax3.axhline(Battery.SOC_min, linestyle="--", alpha=0.5, label="SOC bounds")
    ax3.axhline(Battery.SOC_max, linestyle="--", alpha=0.5)
    ax3.set_ylabel("Energy (MWh)")
    ax3.set_xlabel("Time")
    ax3.legend(loc="upper left")
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()
    return fig


def run_tier(
    forecast_csv: str,
    capital_base_eur: float | None = None,
    gamma: float = 10.0,
) -> dict:
    df = load_forecast(forecast_csv)

    class BudgetCfg(Robust):
        uncertainty_type = "budget"

    BudgetCfg.gamma = gamma

    schedule, _, unc = optimize_tier5_robust(df, BudgetCfg)
    metrics = report_metrics(schedule, unc, BudgetCfg)

    # run_all_tiers.py looks for expected_profit_eur / realized_profit_eur / profit_eur
    metrics["realized_profit_eur"] = metrics["expected_profit_eur"]
    metrics["profit_eur"] = metrics["expected_profit_eur"]

    return metrics
# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    df = load_forecast()

    print("=" * 60)
    print("Tier 5 — Robust Optimization")
    print("=" * 60)

    # ---------------------------------------------------------
    # Run 1: Box uncertainty (most conservative)
    # ---------------------------------------------------------
    class BoxCfg(Robust):
        uncertainty_type = "box"

    sched_box, _, unc = optimize_tier5_robust(df, BoxCfg)
    metrics_box = report_metrics(sched_box, unc, BoxCfg)

    print("\n--- Box uncertainty (no budget) ---")
    for k, v in metrics_box.items():
        if isinstance(v, float):
            print(f"  {k:30s}: {v:>12,.2f}")
        else:
            print(f"  {k:30s}: {v}")

    from optimisation._paths import result, plot
    sched_box.to_csv(result("tier5_robust_box_schedule.csv"), index=False)

    # ---------------------------------------------------------
    # Run 2: Budget uncertainty (Bertsimas-Sim, Γ=10)
    # ---------------------------------------------------------
    class BudgetCfg(Robust):
        uncertainty_type = "budget"
        gamma = 10.0

    sched_bud, _, unc_b = optimize_tier5_robust(df, BudgetCfg)
    metrics_bud = report_metrics(sched_bud, unc_b, BudgetCfg)

    print(f"\n--- Budget uncertainty (Γ={BudgetCfg.gamma}) ---")
    for k, v in metrics_bud.items():
        if isinstance(v, float):
            print(f"  {k:30s}: {v:>12,.2f}")
        else:
            print(f"  {k:30s}: {v}")

    sched_bud.to_csv(result("tier5_robust_budget_schedule.csv"), index=False)

    # ---------------------------------------------------------
    # Run 3: Pareto curve over Γ
    # ---------------------------------------------------------
    print("\n--- Pareto curve over Γ ---")
    pareto_rows = []
    for gamma in [0.0, 2.0, 5.0, 10.0, 20.0, 50.0, 96.0]:
        class Cfg(Robust):
            uncertainty_type = "budget"
        Cfg.gamma = gamma

        sched_g, _, unc_g = optimize_tier5_robust(df, Cfg)
        m = report_metrics(sched_g, unc_g, Cfg)
        pareto_rows.append({
            "gamma": gamma,
            "expected_profit_eur": m["expected_profit_eur"],
            "worst_case_profit_eur": m["worst_case_profit_eur"],
            "best_case_profit_eur": m["best_case_profit_eur"],
            "energy_bought_mwh": m["energy_bought_mwh"],
            "cost_of_energy_bought_eur_p50": m["cost_of_energy_bought_eur_p50"],
            "revenue_from_energy_sold_eur_p50": m["revenue_from_energy_sold_eur_p50"],
            "avg_buy_price_p50": m["avg_buy_price_eur_mwh_p50"],
            "avg_sell_price_p50": m["avg_sell_price_eur_mwh_p50"],
            "return_on_cost_pct_p50": m["return_on_cost_pct_p50"],
            "return_on_cost_pct_worst": m["return_on_cost_pct_worst"],
            "return_per_mwh_throughput_eur": m["return_per_mwh_throughput_eur_p50"],
            "throughput_mwh": m["throughput_mwh"],
            "cycles": m["equivalent_cycles"],
            "idle_intervals": m["idle_intervals"],
        })

    pareto_df = pd.DataFrame(pareto_rows)
    pareto_df.to_csv(result("tier5_pareto.csv"), index=False)

    print(pareto_df.to_string(index=False, float_format=lambda x: f"{x:>10,.2f}"))

    # ---------------------------------------------------------
    # Plots
    # ---------------------------------------------------------
    fig1 = plot_schedule(sched_bud, unc_b,
                         title=f"Tier 5 Robust schedule (Γ={BudgetCfg.gamma})")
    fig1.savefig(plot("tier5_robust_schedule.png"), dpi=110)
    print(f"\nSaved: {plot('tier5_robust_schedule.png')}")

    fig2, ax = plt.subplots(figsize=(10, 6))
    ax.plot(pareto_df["gamma"], pareto_df["expected_profit_eur"],
            "o-", label="Expected profit (P50)", linewidth=2)
    ax.plot(pareto_df["gamma"], pareto_df["worst_case_profit_eur"],
            "s--", label="Worst-case profit", linewidth=2)
    ax.plot(pareto_df["gamma"], pareto_df["best_case_profit_eur"],
            "^:", label="Best-case profit", linewidth=2, alpha=0.7)
    ax.set_xlabel("Robustness budget Γ")
    ax.set_ylabel("Profit (€)")
    ax.set_title("Tier 5 — Profit vs robustness budget")
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig2.savefig(plot("tier5_pareto.png"), dpi=110)
    print(f"Saved: {plot('tier5_pareto.png')}")

    print("\nSaved CSVs:")
    print(f"  - {result('tier5_robust_box_schedule.csv')}")
    print(f"  - {result('tier5_robust_budget_schedule.csv')}")
    print(f"  - {result('tier5_pareto.csv')}")
