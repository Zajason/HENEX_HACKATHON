"""Day-by-day walk-forward backtest for Tier 1 / Tier 2 / Tier 3 optimisers.

Mirrors the Tier-0 harness in `scripts/backtest_forecast_optimisation.py`,
but dispatches to the Pyomo-based tier scripts in `optimisation/tier{1,2,3}.py`.

Each tier:
  - generates N price scenarios from P10/P50/P90 (Tier 1 plain, Tier 2 curve-aware,
    Tier 3 Greek-structural)
  - solves a CVaR-penalised stochastic MILP for that day
  - produces a (charge_mw, discharge_mw, soc_mwh) schedule
Realized PnL is evaluated against `dam_price_eur_mwh` using the same formula as
Tier 0, so summary metrics line up apples-to-apples.

Examples:
    # Smoke test on 7 days, Tier 1, 50 scenarios
    python -m scripts.backtest_tiers --tier 1 \
        --start-date 2025-06-01 --end-date 2025-06-07 --n-scenarios 50

    # Full year, Tier 2
    python -m scripts.backtest_tiers --tier 2 --year 2025 --n-scenarios 200
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd

from forecast.features import LABEL_COL
from optimisation.forecast_dispatch import infer_dt_hours, load_forecast_csv

# Tier modules
from optimisation import tier1 as tier1_mod
from optimisation import tier2 as tier2_mod
from optimisation import tier3 as tier3_mod

# Reuse Tier-0's summary builder so metrics names match
from scripts.backtest_forecast_optimisation import summarize_daily


DEFAULT_FORECAST = Path("data/processed/forecast_walkforward_v1_with_weather_calibrated.csv")
DEFAULT_OUT_DIR = Path("optimisation/results")


# ---------------------------------------------------------------------------
# Tier dispatchers
# ---------------------------------------------------------------------------

def _prep_tier2(day: pd.DataFrame) -> pd.DataFrame:
    out = day.copy()
    out["uncertainty"] = (out["p90_eur_mwh"] - out["p10_eur_mwh"]) / 2
    if "market_tightness" not in out.columns:
        out["market_tightness"] = tier2_mod.simulate_market_tightness(out)
    out["market_tightness_norm"] = tier2_mod.normalize_series(out["market_tightness"])
    return out


def _prep_tier3(day: pd.DataFrame) -> pd.DataFrame:
    out = day.copy()
    out["hour"] = out["timestamp"].dt.hour + out["timestamp"].dt.minute / 60
    out["uncertainty"] = (out["p90_eur_mwh"] - out["p10_eur_mwh"]) / 2
    out = tier3_mod.add_structural_features(out)
    return out


def run_tier_day(tier: int, day: pd.DataFrame, n_scenarios: int, seed: int):
    """Returns (schedule_df, expected_profit_eur, risk_report). Schedule has charge_mw,
    discharge_mw, soc_mwh and the original timestamp + dam_price columns."""
    if tier == 1:
        prep = day
        scenarios = tier1_mod.generate_price_scenarios(prep, n_scenarios=n_scenarios, seed=seed)
        schedule, scenario_profits, risk = tier1_mod.optimize_tier1_cvar(prep, scenarios)
    elif tier == 2:
        prep = _prep_tier2(day)
        scenarios = tier2_mod.generate_curve_aware_scenarios(prep, n_scenarios=n_scenarios, seed=seed)
        schedule, scenario_profits, risk = tier2_mod.optimize_tier2_curve_cvar(prep, scenarios)
    elif tier == 3:
        prep = _prep_tier3(day)
        scenarios = tier3_mod.generate_tier3_scenarios(prep, n_scenarios=n_scenarios, seed=seed)
        schedule, scenario_profits = tier3_mod.optimize_tier3(prep, scenarios)
        risk = {"expected_profit_eur": float(np.mean(scenario_profits))}
    else:
        raise ValueError(f"Unknown tier: {tier}")

    expected_profit = float(risk.get("expected_profit_eur", np.nan))
    return schedule, expected_profit, risk


# ---------------------------------------------------------------------------
# Realized P&L evaluation (mirrors Tier-0's evaluate_schedule)
# ---------------------------------------------------------------------------

def evaluate_day(
    schedule: pd.DataFrame,
    dt_hours: float,
    degradation_eur_mwh: float,
    energy_mwh: float,
) -> dict[str, float]:
    price = schedule[LABEL_COL].to_numpy()
    charge = schedule["charge_mw"].to_numpy()
    discharge = schedule["discharge_mw"].to_numpy()

    revenue = float((price * discharge * dt_hours).sum())
    energy_cost = float((price * charge * dt_hours).sum())
    degradation = float(degradation_eur_mwh * (charge + discharge).sum() * dt_hours)
    profit = revenue - energy_cost - degradation

    energy_bought = float(charge.sum() * dt_hours)
    energy_sold = float(discharge.sum() * dt_hours)
    throughput = energy_bought + energy_sold

    avg_buy = float((price * charge).sum() / charge.sum()) if charge.sum() > 0 else float("nan")
    avg_sell = float((price * discharge).sum() / discharge.sum()) if discharge.sum() > 0 else float("nan")

    active_intervals = int(((charge > 1e-6) | (discharge > 1e-6)).sum())
    idle_intervals = int(len(price) - active_intervals)
    equivalent_cycles = throughput / (2.0 * energy_mwh) if energy_mwh > 0 else float("nan")
    profit_per_throughput = profit / throughput if throughput > 0 else float("nan")

    return {
        "profit_eur": profit,
        "revenue_eur": revenue,
        "energy_cost_eur": energy_cost,
        "degradation_eur": degradation,
        "energy_bought_mwh": energy_bought,
        "energy_sold_mwh": energy_sold,
        "throughput_mwh": throughput,
        "equivalent_cycles": equivalent_cycles,
        "profit_per_mwh_throughput": profit_per_throughput,
        "avg_buy_price_eur_mwh": avg_buy,
        "avg_sell_price_eur_mwh": avg_sell,
        "active_intervals": active_intervals,
        "idle_intervals": idle_intervals,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", type=int, choices=[1, 2, 3], required=True)
    parser.add_argument("--forecast-csv", type=Path, default=DEFAULT_FORECAST)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--n-scenarios", type=int, default=50,
                        help="Scenarios per day. 50 for backtest, 200 for production.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--energy-mwh", type=float, default=300.0,
                        help="Battery energy capacity (used for cycles & CAPEX).")
    parser.add_argument("--degradation-eur-mwh", type=float, default=10.0,
                        help="Per-MWh throughput degradation cost; matches Battery.c_deg in tier scripts.")
    parser.add_argument("--capex-eur-per-mwh", type=float, default=220_000.0,
                        help="Battery installed cost per MWh (2025-2026 LFP turnkey ~€220k/MWh).")
    parser.add_argument("--risk-free-rate-pct", type=float, default=3.0)
    parser.add_argument("--min-rows-per-day", type=int, default=20)
    parser.add_argument("--max-days", type=int, default=None,
                        help="Stop after N days (debug / time-budgeted runs).")
    parser.add_argument("--risk-lambda", type=float, default=None,
                        help="Override Risk.risk_aversion (CVaR penalty weight) on the tier module.")
    parser.add_argument("--cvar-alpha", type=float, default=None,
                        help="Override Risk.alpha (CVaR confidence level, e.g. 0.05 / 0.10).")
    args = parser.parse_args()

    tier_module = {1: tier1_mod, 2: tier2_mod, 3: tier3_mod}[args.tier]
    if args.risk_lambda is not None:
        tier_module.Risk.risk_aversion = args.risk_lambda
    if args.cvar_alpha is not None:
        tier_module.Risk.alpha = args.cvar_alpha

    df = load_forecast_csv(args.forecast_csv)
    if LABEL_COL not in df.columns:
        raise SystemExit(
            f"{args.forecast_csv} must include realized {LABEL_COL} for a money backtest."
        )

    df = df[df["timestamp"].dt.year == args.year].copy()
    if args.start_date:
        df = df[df["timestamp"] >= pd.Timestamp(args.start_date)]
    if args.end_date:
        df = df[df["timestamp"] < pd.Timestamp(args.end_date) + pd.Timedelta(days=1)]

    df["date"] = df["timestamp"].dt.date
    counts = df.groupby("date").size()
    keep_dates = counts[counts >= args.min_rows_per_day].index
    df = df[df["date"].isin(keep_dates)].copy()
    if df.empty:
        raise SystemExit("No eligible forecast days after filtering.")

    schedules: list[pd.DataFrame] = []
    daily_rows: list[dict] = []
    failed_days: list[tuple[str, str]] = []

    days_iter = list(df.groupby("date", sort=True))
    if args.max_days is not None:
        days_iter = days_iter[: args.max_days]

    print(f"Tier {args.tier} backtest | {len(days_iter)} days | n_scenarios={args.n_scenarios}")
    t_start = time.time()

    for idx, (date, day) in enumerate(days_iter, start=1):
        day = day.drop(columns=["date"]).reset_index(drop=True)
        dt = infer_dt_hours(day)

        try:
            schedule, expected_profit, _ = run_tier_day(
                args.tier, day, n_scenarios=args.n_scenarios, seed=args.seed
            )
        except Exception as exc:  # solver / build failures
            failed_days.append((str(date), repr(exc)))
            continue

        realized = evaluate_day(
            schedule,
            dt_hours=dt,
            degradation_eur_mwh=args.degradation_eur_mwh,
            energy_mwh=args.energy_mwh,
        )

        schedule["date"] = str(date)
        schedule["interval_realized_pnl_eur"] = (
            schedule[LABEL_COL]
            * (schedule["discharge_mw"] - schedule["charge_mw"])
            * dt
            - args.degradation_eur_mwh
            * (schedule["charge_mw"] + schedule["discharge_mw"])
            * dt
        )
        schedules.append(schedule)

        daily_rows.append(
            {
                "date": str(date),
                "rows": len(day),
                "dt_hours": dt,
                "realized_profit_eur": realized["profit_eur"],
                "expected_p50_profit_eur": expected_profit,
                "realized_revenue_eur": realized["revenue_eur"],
                "realized_energy_cost_eur": realized["energy_cost_eur"],
                "degradation_eur": realized["degradation_eur"],
                "energy_bought_mwh": realized["energy_bought_mwh"],
                "energy_sold_mwh": realized["energy_sold_mwh"],
                "throughput_mwh": realized["throughput_mwh"],
                "equivalent_cycles": realized["equivalent_cycles"],
                "profit_per_mwh_throughput": realized["profit_per_mwh_throughput"],
                "avg_buy_price_eur_mwh": realized["avg_buy_price_eur_mwh"],
                "avg_sell_price_eur_mwh": realized["avg_sell_price_eur_mwh"],
                "active_intervals": realized["active_intervals"],
                "idle_intervals": realized["idle_intervals"],
                "objective_risk_adjusted_eur": expected_profit,
            }
        )

        if idx % 10 == 0 or idx == len(days_iter):
            elapsed = time.time() - t_start
            avg = elapsed / idx
            eta = avg * (len(days_iter) - idx)
            print(
                f"  [{idx}/{len(days_iter)}] {date} avg={avg:.1f}s/day eta={eta/60:.1f}min",
                flush=True,
            )

    if not daily_rows:
        raise SystemExit("All days failed; nothing to summarise.")

    daily_df = pd.DataFrame(daily_rows)
    schedule_df = pd.concat(schedules, ignore_index=True) if schedules else pd.DataFrame()

    capex_eur = args.energy_mwh * args.capex_eur_per_mwh
    summary = summarize_daily(
        daily_df,
        capex_eur=capex_eur,
        risk_free_rate_pct=args.risk_free_rate_pct,
    )
    summary.update(
        {
            "tier": args.tier,
            "n_scenarios": args.n_scenarios,
            "forecast_csv": str(args.forecast_csv),
            "battery_energy_mwh": args.energy_mwh,
            "degradation_eur_mwh": args.degradation_eur_mwh,
            "failed_days": len(failed_days),
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.year}_tier{args.tier}_optimizer"
    schedule_path = args.output_dir / f"{prefix}_schedule.csv"
    daily_path = args.output_dir / f"{prefix}_daily.csv"
    summary_path = args.output_dir / f"{prefix}_summary.csv"

    if not schedule_df.empty:
        schedule_df.to_csv(schedule_path, index=False)
    daily_df.to_csv(daily_path, index=False)
    pd.DataFrame([summary]).to_csv(summary_path, index=False)

    print(f"\n=== Tier {args.tier} backtest done ===")
    print(f"Eligible days: {summary['days']} | failed: {len(failed_days)}")
    print(f"Schedule: {schedule_path}")
    print(f"Daily:    {daily_path}")
    print(f"Summary:  {summary_path}")
    print("\nKey realized metrics:")
    for key in [
        "total_realized_profit_eur",
        "annualized_realized_profit_eur",
        "mean_daily_profit_eur",
        "win_rate",
        "capex_eur",
        "annualized_return_pct",
        "annualized_excess_return_pct",
        "annualized_return_sharpe",
        "annualized_return_sortino",
        "max_drawdown_eur",
        "cvar5_daily_profit_eur",
        "total_throughput_mwh",
        "mean_equivalent_cycles_per_day",
        "forecast_vs_realized_profit_eur",
    ]:
        value = summary.get(key, "n/a")
        if isinstance(value, float):
            print(f"  {key}: {value:,.4f}")
        else:
            print(f"  {key}: {value}")

    if failed_days:
        print(f"\n{len(failed_days)} days failed. First 5:")
        for d, err in failed_days[:5]:
            print(f"  {d}: {err}")


if __name__ == "__main__":
    main()
