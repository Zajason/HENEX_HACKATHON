# tier_final — Greek structural optimiser with dynamic battery config
#
# Same logic as tier3 but reads battery parameters from
# api/data/battery_config.json (the /api/battery-config endpoint).

import json
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pyomo.environ import *


# ============================================================
# Dynamic battery config loader
# ============================================================

API_CONFIG_PATH = (
    PROJECT_ROOT / "api" / "data" / "battery_config.json"
)


@dataclass
class BatteryGroupParams:
    """One configurable battery block, with quantity already aggregated."""

    name: str
    quantity: int
    P_nom: float
    E_nom: float
    eta_ch: float
    eta_dis: float
    SOC_min: float
    SOC_max: float
    E_init: float
    c_deg: float
    max_cycles: float


@dataclass
class BatteryParams:
    """Aggregated battery parameters derived from the API config."""

    groups: list[BatteryGroupParams]
    P_nom: float
    E_nom: float
    dt: float
    eta_ch: float
    eta_dis: float
    SOC_min: float   # MWh
    SOC_max: float   # MWh
    E_init: float    # MWh
    c_deg: float
    max_cycles: float
    grid_import_max: float
    grid_export_max: float


def load_battery_params(path: Path = API_CONFIG_PATH) -> BatteryParams:
    """Load and aggregate battery parameters from the API config JSON.

    Quantity within a group is aggregated into one equivalent block:
    quantity × capacity and quantity × power. Different groups remain
    separate in the optimiser so they keep their own efficiency,
    degradation, and SOC bounds.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Battery config not found at {path}. "
            "Run the API server or save a config via the frontend first."
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    batteries = data.get("batteries", [])
    if not batteries:
        raise ValueError("No batteries defined in config")

    groups: list[BatteryGroupParams] = []

    for i, b in enumerate(batteries):
        qty = int(b.get("quantity", 1))
        unit_capacity = float(b.get("capacity", 10.0))
        unit_power = float(b.get("power", 5.0))
        cap = unit_capacity * qty
        pwr = unit_power * qty

        if qty <= 0 or cap <= 0 or pwr <= 0:
            raise ValueError(f"Battery group {i + 1} must have positive quantity, capacity, and power.")

        soc_min_pct = float(b.get("socMin", 10.0)) / 100.0
        soc_max_pct = float(b.get("socMax", 90.0)) / 100.0
        soc_init_pct = float(b.get("socInitial", 15.0)) / 100.0
        if soc_min_pct > soc_max_pct:
            raise ValueError(f"Battery group {i + 1} has SOC min above SOC max.")
        if not soc_min_pct <= soc_init_pct <= soc_max_pct:
            raise ValueError(f"Battery group {i + 1} has initial SOC outside min/max bounds.")

        groups.append(
            BatteryGroupParams(
                name=str(b.get("name") or f"Battery group {i + 1}"),
                quantity=qty,
                P_nom=pwr,
                E_nom=cap,
                eta_ch=float(b.get("chargeEff", 92.0)) / 100.0,
                eta_dis=float(b.get("dischargeEff", 90.0)) / 100.0,
                SOC_min=soc_min_pct * cap,
                SOC_max=soc_max_pct * cap,
                E_init=soc_init_pct * cap,
                c_deg=float(b.get("degradationCost", 2.5)),
                max_cycles=2.0,
            )
        )

    total_capacity = sum(group.E_nom for group in groups)
    total_power = sum(group.P_nom for group in groups)
    eta_ch = sum(group.eta_ch * group.E_nom for group in groups) / total_capacity
    eta_dis = sum(group.eta_dis * group.E_nom for group in groups) / total_capacity
    c_deg = sum(group.c_deg * group.E_nom for group in groups) / total_capacity

    dt = 0.25  # 15 minutes — fixed by HEnEx MTU resolution

    return BatteryParams(
        groups=groups,
        P_nom=total_power,
        E_nom=total_capacity,
        dt=dt,
        eta_ch=eta_ch,
        eta_dis=eta_dis,
        SOC_min=sum(group.SOC_min for group in groups),
        SOC_max=sum(group.SOC_max for group in groups),
        E_init=sum(group.E_init for group in groups),
        c_deg=c_deg,
        max_cycles=2.0,
        grid_import_max=total_power,
        grid_export_max=total_power,
    )


def print_battery_params(bp: BatteryParams) -> None:
    print("\n=== Battery Parameters (from API config) ===")
    print(f"  P_nom          = {bp.P_nom:.2f} MW")
    print(f"  E_nom          = {bp.E_nom:.2f} MWh")
    print(f"  η_charge       = {bp.eta_ch:.4f}")
    print(f"  η_discharge    = {bp.eta_dis:.4f}")
    print(f"  RTE            = {bp.eta_ch * bp.eta_dis:.4f}")
    print(f"  SOC_min        = {bp.SOC_min:.2f} MWh ({bp.SOC_min / bp.E_nom * 100:.1f}%)")
    print(f"  SOC_max        = {bp.SOC_max:.2f} MWh ({bp.SOC_max / bp.E_nom * 100:.1f}%)")
    print(f"  E_init         = {bp.E_init:.2f} MWh ({bp.E_init / bp.E_nom * 100:.1f}%)")
    print(f"  c_deg          = {bp.c_deg:.2f} €/MWh throughput")
    print(f"  max_cycles     = {bp.max_cycles}")
    print(f"  grid_import    = {bp.grid_import_max:.2f} MW")
    print(f"  grid_export    = {bp.grid_export_max:.2f} MW")
    print(f"  Δt             = {bp.dt} h (15 min)")
    print("  Groups:")
    for i, group in enumerate(bp.groups):
        print(
            f"    [{i}] {group.name}: qty={group.quantity}, "
            f"{group.P_nom:.2f} MW / {group.E_nom:.2f} MWh, "
            f"SOC {group.SOC_min:.2f}-{group.SOC_max:.2f} MWh, "
            f"E_init={group.E_init:.2f} MWh, "
            f"η={group.eta_ch:.3f}/{group.eta_dis:.3f}, "
            f"c_deg={group.c_deg:.2f}"
        )
    print()


# ============================================================
# Risk & Tier3 structural config (unchanged)
# ============================================================

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

def load_forecast(path=None, bp: BatteryParams | None = None):
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

    dt = bp.dt if bp else 0.25
    df = add_structural_features(df, dt)

    return df


def add_structural_features(df, dt=0.25):
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

    steps_4h = int(4 / dt)
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
# Tier 3 scenario generation (unchanged)
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
# Tier Final stochastic CVaR MILP (uses dynamic BatteryParams)
# ============================================================

def optimize_tier_final(df, scenarios, bp: BatteryParams):
    S, T_len = scenarios.shape
    T = range(T_len)
    K = range(S)
    G = range(len(bp.groups))

    model = ConcreteModel()

    model.P_ch = Var(G, T, domain=NonNegativeReals)
    model.P_dis = Var(G, T, domain=NonNegativeReals)
    model.E = Var(G, T, domain=NonNegativeReals)

    # One fleet-facing market mode per interval; groups can choose how much
    # capacity to contribute, but the fleet cannot charge and discharge at once.
    model.u_ch = Var(T, domain=Binary)
    model.u_dis = Var(T, domain=Binary)

    model.profit = Var(K, domain=Reals)
    model.var_loss = Var(domain=Reals)
    model.excess_loss = Var(K, domain=NonNegativeReals)

    scarcity = df["scarcity_pressure"].to_numpy()
    surplus = df["surplus_pressure"].to_numpy()
    tightness = df["market_tightness_norm"].to_numpy()

    # Penalize charging in scarcity/high-tightness periods.
    structural_charge_penalty = Tier3.structural_penalty * (scarcity + tightness)

    def scenario_profit_rule(m, k):
        return m.profit[k] == sum(
            scenarios[k, t]
            * sum(m.P_dis[g, t] - m.P_ch[g, t] for g in G)
            * bp.dt
            - sum(
                bp.groups[g].c_deg * (m.P_ch[g, t] + m.P_dis[g, t]) * bp.dt
                for g in G
            )
            - structural_charge_penalty[t] * sum(m.P_ch[g, t] for g in G) * bp.dt
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

    out["charge_mw"] = [
        sum(value(model.P_ch[g, t]) for g in G)
        for t in T
    ]
    out["discharge_mw"] = [
        sum(value(model.P_dis[g, t]) for g in G)
        for t in T
    ]
    out["soc_mwh"] = [
        sum(value(model.E[g, t]) for g in G)
        for t in T
    ]
    out["net_power_mw"] = out["discharge_mw"] - out["charge_mw"]

    scenario_profits = np.array([value(model.profit[k]) for k in K])

    return out, scenario_profits


# ============================================================
# Metrics
# ============================================================

def evaluate_schedule_on_prices(schedule, prices, bp: BatteryParams):
    market_revenue = (
        prices
        * (schedule["discharge_mw"].to_numpy() - schedule["charge_mw"].to_numpy())
        * bp.dt
    ).sum()

    group_cost = 0.0
    has_group_columns = all(
        f"group_{g + 1}_charge_mw" in schedule.columns
        and f"group_{g + 1}_discharge_mw" in schedule.columns
        for g in range(len(bp.groups))
    )
    if has_group_columns:
        for g, group in enumerate(bp.groups):
            prefix = f"group_{g + 1}"
            group_cost += (
                group.c_deg
                * (
                    schedule[f"{prefix}_charge_mw"].to_numpy()
                    + schedule[f"{prefix}_discharge_mw"].to_numpy()
                )
                * bp.dt
            ).sum()
    else:
        group_cost = (
            bp.c_deg
            * (schedule["charge_mw"].to_numpy() + schedule["discharge_mw"].to_numpy())
            * bp.dt
        ).sum()

    return market_revenue - group_cost


def naive_rank_strategy(df, bp: BatteryParams):
    out = df.copy()
    G = range(len(bp.groups))

    out["charge_mw"] = 0.0
    out["discharge_mw"] = 0.0
    out["soc_mwh"] = bp.E_init
    for g, group in enumerate(bp.groups):
        prefix = f"group_{g + 1}"
        out[f"{prefix}_name"] = group.name
        out[f"{prefix}_charge_mw"] = 0.0
        out[f"{prefix}_discharge_mw"] = 0.0
        out[f"{prefix}_soc_mwh"] = group.E_init

    low = out["p50_eur_mwh"].quantile(0.25)
    high = out["p50_eur_mwh"].quantile(0.75)

    soc = {g: bp.groups[g].E_init for g in G}
    discharged_today = {g: 0.0 for g in G}

    for i, row in out.iterrows():
        price = row["p50_eur_mwh"]

        if price <= low:
            remaining_grid = bp.grid_import_max
            # Lower degradation and higher charge efficiency groups get filled first.
            order = sorted(G, key=lambda g: (bp.groups[g].c_deg, -bp.groups[g].eta_ch))
            for g in order:
                group = bp.groups[g]
                max_add = group.SOC_max - soc[g]
                p_ch = min(
                    group.P_nom,
                    remaining_grid,
                    max_add / (group.eta_ch * bp.dt),
                )
                p_ch = max(0, p_ch)
                prefix = f"group_{g + 1}"
                out.loc[i, f"{prefix}_charge_mw"] = p_ch
                soc[g] += group.eta_ch * p_ch * bp.dt
                remaining_grid -= p_ch
                if remaining_grid <= 1e-9:
                    break

        elif price >= high:
            remaining_grid = bp.grid_export_max
            # Lower degradation and higher discharge efficiency groups get dispatched first.
            order = sorted(G, key=lambda g: (bp.groups[g].c_deg, -bp.groups[g].eta_dis))
            for g in order:
                group = bp.groups[g]
                if discharged_today[g] >= group.max_cycles * group.E_nom:
                    continue
                max_remove = soc[g] - group.SOC_min
                p_dis = min(
                    group.P_nom,
                    remaining_grid,
                    max_remove * group.eta_dis / bp.dt,
                )

                remaining_cycle = group.max_cycles * group.E_nom - discharged_today[g]
                p_dis = min(p_dis, remaining_cycle / bp.dt)
                p_dis = max(0, p_dis)
                prefix = f"group_{g + 1}"
                out.loc[i, f"{prefix}_discharge_mw"] = p_dis
                soc[g] -= p_dis * bp.dt / group.eta_dis
                discharged_today[g] += p_dis * bp.dt
                remaining_grid -= p_dis
                if remaining_grid <= 1e-9:
                    break

        out.loc[i, "charge_mw"] = sum(out.loc[i, f"group_{g + 1}_charge_mw"] for g in G)
        out.loc[i, "discharge_mw"] = sum(out.loc[i, f"group_{g + 1}_discharge_mw"] for g in G)
        for g in G:
            out.loc[i, f"group_{g + 1}_soc_mwh"] = soc[g]
        out.loc[i, "soc_mwh"] = sum(soc.values())

    out["net_power_mw"] = out["discharge_mw"] - out["charge_mw"]

    return out


def calculate_metrics(schedule, scenarios, bp: BatteryParams, naive_schedule=None):
    profits = np.array([
        evaluate_schedule_on_prices(schedule, scenarios[k], bp)
        for k in range(scenarios.shape[0])
    ])

    throughput = (
        (schedule["charge_mw"] + schedule["discharge_mw"]) * bp.dt
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
        "equivalent_cycles": throughput / (2 * bp.E_nom),
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
            evaluate_schedule_on_prices(naive_schedule, scenarios[k], bp)
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


def calculate_group_metrics(schedule, scenarios, bp: BatteryParams):
    p50 = schedule["p50_eur_mwh"].to_numpy()
    rows = []

    for g, group in enumerate(bp.groups):
        prefix = f"group_{g + 1}"
        charge = schedule[f"{prefix}_charge_mw"].to_numpy()
        discharge = schedule[f"{prefix}_discharge_mw"].to_numpy()
        soc = schedule[f"{prefix}_soc_mwh"].to_numpy()
        throughput = ((charge + discharge) * bp.dt).sum()
        market_profit = (p50 * (discharge - charge) * bp.dt).sum()
        degradation_cost = (group.c_deg * (charge + discharge) * bp.dt).sum()
        rows.append(
            {
                "group": g + 1,
                "name": group.name,
                "quantity": group.quantity,
                "power_mw": group.P_nom,
                "energy_mwh": group.E_nom,
                "charge_mwh": (charge * bp.dt).sum(),
                "discharge_mwh": (discharge * bp.dt).sum(),
                "throughput_mwh": throughput,
                "equivalent_cycles": throughput / (2 * group.E_nom),
                "active_intervals": int(((charge > 1e-6) | (discharge > 1e-6)).sum()),
                "charge_intervals": int((charge > 1e-6).sum()),
                "discharge_intervals": int((discharge > 1e-6).sum()),
                "min_soc_mwh": soc.min(),
                "max_soc_mwh": soc.max(),
                "min_soc_pct": soc.min() / group.E_nom * 100,
                "max_soc_pct": soc.max() / group.E_nom * 100,
                "market_profit_p50_eur": market_profit,
                "degradation_cost_eur": degradation_cost,
                "net_profit_p50_eur": market_profit - degradation_cost,
            }
        )

    return rows


def print_group_metrics(group_metrics):
    print("\n=== Battery Group Dispatch Metrics ===")
    for row in group_metrics:
        print(
            f"  Group {row['group']} — {row['name']} "
            f"(qty={row['quantity']}, {row['power_mw']:.2f} MW / {row['energy_mwh']:.2f} MWh)"
        )
        print(
            f"    charge={row['charge_mwh']:.2f} MWh, "
            f"discharge={row['discharge_mwh']:.2f} MWh, "
            f"throughput={row['throughput_mwh']:.2f} MWh, "
            f"cycles={row['equivalent_cycles']:.3f}"
        )
        print(
            f"    active={row['active_intervals']} intervals "
            f"(charge={row['charge_intervals']}, discharge={row['discharge_intervals']}), "
            f"SoC={row['min_soc_mwh']:.2f}-{row['max_soc_mwh']:.2f} MWh "
            f"({row['min_soc_pct']:.1f}-{row['max_soc_pct']:.1f}%)"
        )
        print(
            f"    P50 market profit=€{row['market_profit_p50_eur']:,.2f}, "
            f"degradation=€{row['degradation_cost_eur']:,.2f}, "
            f"net=€{row['net_profit_p50_eur']:,.2f}"
        )


# ============================================================
# Plotting
# ============================================================

def plot_tier_final_results(schedule, scenarios, profits, bp: BatteryParams):
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
    axes[0].set_title("Tier Final — Greek-Structural Price Scenarios (API config)")
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
    axes[3].set_title(f"Tier Final Dispatch — {bp.P_nom:.1f} MW / {bp.E_nom:.1f} MWh")
    axes[3].set_ylabel("MW")
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    axes[4].plot(timestamps, schedule["soc_mwh"], label="SOC")
    axes[4].axhline(bp.SOC_min, linestyle="--", label=f"SOC min ({bp.SOC_min:.1f})")
    axes[4].axhline(bp.SOC_max, linestyle="--", label=f"SOC max ({bp.SOC_max:.1f})")
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

    from optimisation._paths import plot
    out_path = plot("tier_final_results.png")
    fig.savefig(out_path, dpi=120)
    print(f"Plot saved to: {out_path}")
    plt.close(fig)


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":
    # Load battery parameters from API config
    bp = load_battery_params()
    print_battery_params(bp)

    # Load forecast data
    df = load_forecast(bp=bp)

    # Generate scenarios
    scenarios = generate_tier3_scenarios(
        df,
        n_scenarios=Risk.n_scenarios,
        seed=Risk.seed,
    )

    # Optimize
    print("Running Tier Final optimisation...")
    schedule, profits = optimize_tier_final(df, scenarios, bp)

    # Naive baseline
    naive = naive_rank_strategy(df, bp)

    # Metrics
    metrics, evaluated_profits = calculate_metrics(
        schedule,
        scenarios,
        bp,
        naive_schedule=naive,
    )
    group_metrics = calculate_group_metrics(schedule, scenarios, bp)

    print("\n=== Tier Final Metrics (API battery config) ===")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:,.4f}")
        else:
            print(f"  {k}: {v}")
    print_group_metrics(group_metrics)

    # Save results
    from optimisation._paths import result
    schedule.to_csv(result("tier_final_schedule.csv"), index=False)
    pd.DataFrame(scenarios).to_csv(result("tier_final_scenarios.csv"), index=False)

    print(f"\nSaved:")
    print(f"  - {result('tier_final_schedule.csv')}")
    print(f"  - {result('tier_final_scenarios.csv')}")

    # Plot
    plot_tier_final_results(schedule, scenarios, evaluated_profits, bp)
