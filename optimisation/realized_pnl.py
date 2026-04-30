# realized_pnl — post-DAM realized PnL evaluator for the tier_final schedule.
#
# Loads the schedule produced by tier_final.py, matches it against actual
# DAM clearing prices on a 15-min MTU basis, and reports realized cashflows,
# degradation, SOC trajectory, constraint violations, and daily summary.
#
# Does NOT re-optimise. Does NOT submit DAM orders.

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from optimisation._paths import plot, result
from optimisation.tier_final import (
    BatteryParams,
    load_battery_params,
    print_battery_params,
)


SCHEDULE_PATH_DEFAULT = result("tier_final_schedule.csv")
MTU_OUT_PATH = result("realized_pnl_mtu.csv")
SUMMARY_OUT_PATH = result("realized_pnl_summary.csv")
PLOT_OUT_PATH = plot("realized_pnl.png")


# ============================================================
# Inputs
# ============================================================

def load_schedule(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)

    required = {"timestamp", "charge_mw", "discharge_mw", "soc_mwh", "p50_eur_mwh"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Schedule missing columns: {missing}")

    return df


def load_actual_prices(path: Path | None, schedule: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """Load actual DAM clearing prices, or synthesise demo actuals from the
    forecast P50 with realistic noise if no file is supplied."""
    if path is not None:
        df = pd.read_csv(path, parse_dates=["timestamp"])
        if "price_eur_mwh" not in df.columns:
            raise ValueError(
                "Actual prices CSV must have columns: timestamp, price_eur_mwh"
            )
        return df[["timestamp", "price_eur_mwh"]].sort_values("timestamp").reset_index(drop=True)

    rng = np.random.default_rng(seed)
    p50 = schedule["p50_eur_mwh"].to_numpy()
    band = (
        (schedule["p90_eur_mwh"].to_numpy() - schedule["p10_eur_mwh"].to_numpy()) / 2
        if {"p90_eur_mwh", "p10_eur_mwh"}.issubset(schedule.columns)
        else np.full_like(p50, 5.0)
    )
    noise = rng.normal(0, band * 0.45)
    actual = np.clip(p50 + noise, -50, 600)

    return pd.DataFrame({
        "timestamp": schedule["timestamp"].to_numpy(),
        "price_eur_mwh": actual,
    })


# ============================================================
# Evaluation
# ============================================================

def evaluate(
    schedule: pd.DataFrame,
    actual: pd.DataFrame,
    bp: BatteryParams,
) -> tuple[pd.DataFrame, dict]:
    merged = schedule.merge(actual, on="timestamp", how="left")
    missing = int(merged["price_eur_mwh"].isna().sum())
    merged["price_eur_mwh"] = merged["price_eur_mwh"].fillna(merged["p50_eur_mwh"])

    p_ch = merged["charge_mw"].to_numpy()
    p_dis = merged["discharge_mw"].to_numpy()
    price = merged["price_eur_mwh"].to_numpy()
    forecast = merged["p50_eur_mwh"].to_numpy()
    dt = bp.dt

    charge_cost = price * p_ch * dt
    discharge_revenue = price * p_dis * dt
    net_cashflow = discharge_revenue - charge_cost
    degradation = bp.c_deg * (p_ch + p_dis) * dt
    realized_pnl = net_cashflow - degradation

    soc = np.empty(len(merged))
    soc[0] = bp.E_init + bp.eta_ch * p_ch[0] * dt - (p_dis[0] / bp.eta_dis) * dt
    for t in range(1, len(merged)):
        soc[t] = soc[t - 1] + bp.eta_ch * p_ch[t] * dt - (p_dis[t] / bp.eta_dis) * dt

    eps = 1e-6
    flag_soc_below = soc < bp.SOC_min - eps
    flag_soc_above = soc > bp.SOC_max + eps
    flag_simul = (p_ch > eps) & (p_dis > eps)
    flag_power = (p_ch > bp.P_nom + eps) | (p_dis > bp.P_nom + eps)
    flag_import = p_ch > bp.grid_import_max + eps
    flag_export = p_dis > bp.grid_export_max + eps

    out = merged[["timestamp", "p50_eur_mwh", "charge_mw", "discharge_mw"]].copy()
    out["actual_price_eur_mwh"] = price
    out["price_error_eur_mwh"] = price - forecast
    out["charge_cost_eur"] = charge_cost
    out["discharge_revenue_eur"] = discharge_revenue
    out["net_cashflow_eur"] = net_cashflow
    out["degradation_eur"] = degradation
    out["realized_pnl_eur"] = realized_pnl
    out["cum_realized_pnl_eur"] = np.cumsum(realized_pnl)
    out["soc_mwh_recomputed"] = soc
    out["soc_mwh_schedule"] = merged["soc_mwh"].to_numpy()
    out["flag_soc_below_min"] = flag_soc_below
    out["flag_soc_above_max"] = flag_soc_above
    out["flag_simultaneous"] = flag_simul
    out["flag_power_exceeded"] = flag_power
    out["flag_grid_import"] = flag_import
    out["flag_grid_export"] = flag_export

    throughput = float(((p_ch + p_dis) * dt).sum())
    cycles = throughput / (2 * bp.E_nom) if bp.E_nom > 0 else 0.0
    expected_pnl_p50 = float(((forecast * (p_dis - p_ch)) * dt - bp.c_deg * (p_ch + p_dis) * dt).sum())

    delivery_day = (
        pd.Timestamp(merged["timestamp"].iloc[0]).strftime("%Y-%m-%d")
        if len(merged) else None
    )

    summary = {
        "delivery_day": delivery_day,
        "mtus_total": int(len(merged)),
        "mtus_missing_actual": missing,
        "total_charge_cost_eur": float(charge_cost.sum()),
        "total_discharge_revenue_eur": float(discharge_revenue.sum()),
        "net_arbitrage_profit_eur": float(net_cashflow.sum()),
        "degradation_cost_eur": float(degradation.sum()),
        "realized_pnl_eur": float(realized_pnl.sum()),
        "expected_pnl_on_p50_eur": expected_pnl_p50,
        "forecast_vs_realized_delta_eur": float(realized_pnl.sum()) - expected_pnl_p50,
        "throughput_mwh": throughput,
        "equivalent_cycles": cycles,
        "mean_abs_price_error_eur_mwh": float(np.abs(price - forecast).mean()),
        "min_soc_mwh": float(soc.min()),
        "max_soc_mwh": float(soc.max()),
        "violations_total": int(
            flag_soc_below.sum() + flag_soc_above.sum() + flag_simul.sum()
            + flag_power.sum() + flag_import.sum() + flag_export.sum()
        ),
        "viol_soc_below_min": int(flag_soc_below.sum()),
        "viol_soc_above_max": int(flag_soc_above.sum()),
        "viol_simultaneous": int(flag_simul.sum()),
        "viol_power_exceeded": int(flag_power.sum()),
        "viol_grid_import": int(flag_import.sum()),
        "viol_grid_export": int(flag_export.sum()),
        "cycle_limit_breach": bool(cycles > bp.max_cycles + 1e-6),
    }

    return out, summary


# ============================================================
# Reporting
# ============================================================

def print_report(summary: dict) -> None:
    print(f"\n=== Realized PnL Evaluation (delivery day {summary['delivery_day']}) ===")
    print(f"  MTUs evaluated:           {summary['mtus_total'] - summary['mtus_missing_actual']} / {summary['mtus_total']}")
    if summary["mtus_missing_actual"]:
        print(f"  ! Missing actual prices:  {summary['mtus_missing_actual']} (filled from P50)")
    print(f"  Total charge cost:        {summary['total_charge_cost_eur']:>12,.2f} €")
    print(f"  Total discharge revenue:  {summary['total_discharge_revenue_eur']:>12,.2f} €")
    print(f"  Net arbitrage profit:     {summary['net_arbitrage_profit_eur']:>12,.2f} €")
    print(f"  Degradation cost:         {summary['degradation_cost_eur']:>12,.2f} €")
    print(f"  Realized PnL (net):       {summary['realized_pnl_eur']:>12,.2f} €")
    print(f"  Throughput:               {summary['throughput_mwh']:>12,.2f} MWh   ({summary['equivalent_cycles']:.2f} cycles)")
    print(f"  Mean abs price error:     {summary['mean_abs_price_error_eur_mwh']:>12,.2f} €/MWh")
    print(f"  Forecast vs realized PnL: {summary['forecast_vs_realized_delta_eur']:>+12,.2f} €")
    print(f"  Constraint violations:    {summary['violations_total']}")
    print(f"    SOC<min: {summary['viol_soc_below_min']}   SOC>max: {summary['viol_soc_above_max']}"
          f"   simul: {summary['viol_simultaneous']}   power: {summary['viol_power_exceeded']}"
          f"   import: {summary['viol_grid_import']}   export: {summary['viol_grid_export']}")
    if summary["cycle_limit_breach"]:
        print("    ! Daily cycle limit breached")


def plot_results(mtu: pd.DataFrame, summary: dict, bp: BatteryParams) -> None:
    fig, axes = plt.subplots(4, 1, figsize=(15, 14), sharex=True)
    ts = mtu["timestamp"]

    axes[0].plot(ts, mtu["p50_eur_mwh"], label="Forecast P50", linestyle="--")
    axes[0].plot(ts, mtu["actual_price_eur_mwh"], label="Actual DAM", linewidth=2)
    axes[0].set_title(f"DAM Prices — Forecast vs Actual ({summary['delivery_day']})")
    axes[0].set_ylabel("€/MWh")
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    axes[1].bar(ts, mtu["charge_mw"], width=0.008, label="Charge")
    axes[1].bar(ts, -mtu["discharge_mw"], width=0.008, label="Discharge")
    axes[1].set_title(f"Dispatch — {bp.P_nom:.1f} MW / {bp.E_nom:.1f} MWh")
    axes[1].set_ylabel("MW")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(ts, mtu["soc_mwh_recomputed"], label="SOC (recomputed)")
    axes[2].axhline(bp.SOC_min, linestyle="--", label=f"SOC min ({bp.SOC_min:.1f})")
    axes[2].axhline(bp.SOC_max, linestyle="--", label=f"SOC max ({bp.SOC_max:.1f})")
    axes[2].set_title("State of Charge")
    axes[2].set_ylabel("MWh")
    axes[2].legend()
    axes[2].grid(True, alpha=0.3)

    axes[3].fill_between(ts, 0, mtu["cum_realized_pnl_eur"], alpha=0.4)
    axes[3].plot(ts, mtu["cum_realized_pnl_eur"], linewidth=2)
    axes[3].axhline(0, color="black", linewidth=0.6)
    axes[3].set_title(f"Cumulative Realized PnL — Total {summary['realized_pnl_eur']:,.2f} €")
    axes[3].set_ylabel("€")
    axes[3].grid(True, alpha=0.3)

    plt.tight_layout()
    fig.savefig(PLOT_OUT_PATH, dpi=120)
    plt.close(fig)
    print(f"Plot saved to: {PLOT_OUT_PATH}")


# ============================================================
# CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Post-DAM realized PnL evaluator for tier_final schedule."
    )
    parser.add_argument(
        "--schedule",
        type=Path,
        default=SCHEDULE_PATH_DEFAULT,
        help="Path to tier_final schedule CSV.",
    )
    parser.add_argument(
        "--actual",
        type=Path,
        default=None,
        help="Path to actual DAM prices CSV (timestamp, price_eur_mwh). "
             "If omitted (and --henex not given), demo actuals are synthesised.",
    )
    parser.add_argument(
        "--henex",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Fetch actual DAM prices live from enexgroup.gr for this delivery "
             "day (YYYY-MM-DD). Mutually exclusive with --actual.",
    )
    args = parser.parse_args()

    if args.henex is not None and args.actual is not None:
        parser.error("--henex and --actual are mutually exclusive")

    if args.henex is not None:
        from optimisation.henex_dam import fetch_actual_prices
        _, url, csv_path = fetch_actual_prices(args.henex)
        print(f"Fetched HEnEx DAM for {args.henex}: {url}")
        args.actual = csv_path

    bp = load_battery_params()
    print_battery_params(bp)

    schedule = load_schedule(args.schedule)
    actual = load_actual_prices(args.actual, schedule)

    mtu, summary = evaluate(schedule, actual, bp)

    mtu.to_csv(MTU_OUT_PATH, index=False)
    pd.DataFrame([summary]).to_csv(SUMMARY_OUT_PATH, index=False)

    print_report(summary)
    print(f"\nSaved:")
    print(f"  - {MTU_OUT_PATH}")
    print(f"  - {SUMMARY_OUT_PATH}")

    plot_results(mtu, summary, bp)


if __name__ == "__main__":
    main()
