"""Backtest forecast-driven battery dispatch over many historical days.

The scheduler sees only P10/P50/P90 forecasts. P&L is evaluated afterwards
against realized DAM prices in the walk-forward forecast file.

Example:
    python -m scripts.backtest_forecast_optimisation --year 2025
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from forecast.features import LABEL_COL
from optimisation.forecast_dispatch import (
    BatteryConfig,
    evaluate_schedule,
    infer_dt_hours,
    load_forecast_csv,
    optimize_forecast_dispatch,
)


DEFAULT_FORECAST = Path("data/processed/forecast_walkforward_v1_with_weather_calibrated.csv")
DEFAULT_OUT_DIR = Path("optimisation/results")


def max_drawdown(values: pd.Series) -> float:
    cumulative = values.cumsum()
    running_max = cumulative.cummax()
    drawdown = cumulative - running_max
    return float(drawdown.min()) if len(drawdown) else 0.0


def cvar(values: pd.Series, alpha: float = 0.05) -> float:
    if values.empty:
        return float("nan")
    threshold = values.quantile(alpha)
    tail = values[values <= threshold]
    return float(tail.mean()) if len(tail) else float("nan")


def summarize_daily(
    daily: pd.DataFrame,
    capex_eur: float = 0.0,
    risk_free_rate_pct: float = 0.0,
) -> dict[str, float | int | str]:
    pnl = daily["realized_profit_eur"].astype(float)
    downside = pnl[pnl < 0.0]
    std = float(pnl.std(ddof=0))
    downside_std = float(downside.std(ddof=0)) if len(downside) else 0.0
    days = int(len(daily))

    if capex_eur > 0:
        ret = pnl / capex_eur
        daily_rf = (risk_free_rate_pct / 100.0) / 365.0
        excess = ret - daily_rf
        ret_downside = ret[ret < 0.0]
        ret_std = float(ret.std(ddof=0))
        ret_dn_std = float(ret_downside.std(ddof=0)) if len(ret_downside) else 0.0
        return_sharpe_d = float(excess.mean() / ret_std) if ret_std > 1e-12 else np.nan
        return_sharpe_a = float(return_sharpe_d * np.sqrt(365.0)) if ret_std > 1e-12 else np.nan
        return_sortino_d = float(excess.mean() / ret_dn_std) if ret_dn_std > 1e-12 else np.nan
        return_sortino_a = float(return_sortino_d * np.sqrt(365.0)) if ret_dn_std > 1e-12 else np.nan
        mean_daily_return_pct = float(ret.mean() * 100)
        annualized_return_pct = float(pnl.sum() / capex_eur * 365.0 / days * 100) if days else 0.0
        annualized_excess_return_pct = annualized_return_pct - risk_free_rate_pct
    else:
        return_sharpe_d = return_sharpe_a = np.nan
        return_sortino_d = return_sortino_a = np.nan
        mean_daily_return_pct = annualized_return_pct = np.nan
        annualized_excess_return_pct = np.nan

    return {
        "days": days,
        "start_date": str(daily["date"].min()),
        "end_date": str(daily["date"].max()),
        "total_realized_profit_eur": float(pnl.sum()),
        "annualized_realized_profit_eur": float(pnl.sum() * 365.0 / days) if days else 0.0,
        "mean_daily_profit_eur": float(pnl.mean()) if days else 0.0,
        "median_daily_profit_eur": float(pnl.median()) if days else 0.0,
        "std_daily_profit_eur": std,
        "daily_pnl_sharpe": float(pnl.mean() / std) if std > 1e-9 else np.nan,
        "annualized_pnl_sharpe": float((pnl.mean() / std) * np.sqrt(365.0)) if std > 1e-9 else np.nan,
        "daily_pnl_sortino": float(pnl.mean() / downside_std) if downside_std > 1e-9 else np.nan,
        "annualized_pnl_sortino": float((pnl.mean() / downside_std) * np.sqrt(365.0))
        if downside_std > 1e-9 else np.nan,
        "capex_eur": float(capex_eur),
        "risk_free_rate_pct": float(risk_free_rate_pct),
        "mean_daily_return_pct": mean_daily_return_pct,
        "annualized_return_pct": annualized_return_pct,
        "annualized_excess_return_pct": annualized_excess_return_pct,
        "daily_return_sharpe": return_sharpe_d,
        "annualized_return_sharpe": return_sharpe_a,
        "daily_return_sortino": return_sortino_d,
        "annualized_return_sortino": return_sortino_a,
        "win_rate": float((pnl > 0.0).mean()) if days else 0.0,
        "loss_rate": float((pnl < 0.0).mean()) if days else 0.0,
        "worst_day_profit_eur": float(pnl.min()) if days else 0.0,
        "best_day_profit_eur": float(pnl.max()) if days else 0.0,
        "cvar5_daily_profit_eur": cvar(pnl, alpha=0.05),
        "max_drawdown_eur": max_drawdown(pnl),
        "total_expected_p50_profit_eur": float(daily["expected_p50_profit_eur"].sum()),
        "forecast_vs_realized_profit_eur": float(
            daily["realized_profit_eur"].sum() - daily["expected_p50_profit_eur"].sum()
        ),
        "total_throughput_mwh": float(daily["throughput_mwh"].sum()),
        "total_energy_bought_mwh": float(daily["energy_bought_mwh"].sum()),
        "total_energy_sold_mwh": float(daily["energy_sold_mwh"].sum()),
        "mean_equivalent_cycles_per_day": float(daily["equivalent_cycles"].mean()) if days else 0.0,
        "total_active_intervals": int(daily["active_intervals"].sum()),
        "total_idle_intervals": int(daily["idle_intervals"].sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecast-csv", type=Path, default=DEFAULT_FORECAST)
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--power-mw", type=float, default=75.0)
    parser.add_argument("--energy-mwh", type=float, default=300.0)
    parser.add_argument("--degradation-eur-mwh", type=float, default=10.0)
    parser.add_argument("--risk-lambda", type=float, default=0.35)
    parser.add_argument("--max-cycles", type=float, default=2.0)
    parser.add_argument(
        "--capex-eur-per-mwh",
        type=float,
        default=220_000.0,
        help="Battery installed cost per MWh (2025-2026 LFP turnkey ~€220k/MWh).",
    )
    parser.add_argument(
        "--risk-free-rate-pct",
        type=float,
        default=3.0,
        help="Annual risk-free rate percentage (subtracted from returns for Sharpe).",
    )
    parser.add_argument(
        "--min-rows-per-day",
        type=int,
        default=20,
        help="Skip incomplete days below this row count. Hourly days have 24 rows; 15-min days have 96.",
    )
    args = parser.parse_args()

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

    config = BatteryConfig(
        power_mw=args.power_mw,
        energy_mwh=args.energy_mwh,
        degradation_eur_mwh=args.degradation_eur_mwh,
        risk_lambda=args.risk_lambda,
        max_cycles=args.max_cycles,
    )

    schedules = []
    daily_rows = []
    for date, day in df.groupby("date", sort=True):
        day = day.drop(columns=["date"]).reset_index(drop=True)
        dt = infer_dt_hours(day)
        schedule, expected_metrics = optimize_forecast_dispatch(day, config=config)
        realized_metrics = evaluate_schedule(
            schedule,
            dt=dt,
            config=config,
            price_col=LABEL_COL,
        )
        schedule["date"] = str(date)
        schedule["interval_realized_pnl_eur"] = (
            schedule[LABEL_COL]
            * (schedule["discharge_mw"] - schedule["charge_mw"])
            * dt
            - config.degradation_eur_mwh
            * (schedule["charge_mw"] + schedule["discharge_mw"])
            * dt
        )
        schedules.append(schedule)

        daily_rows.append(
            {
                "date": str(date),
                "rows": len(day),
                "dt_hours": dt,
                "realized_profit_eur": realized_metrics["profit_eur"],
                "expected_p50_profit_eur": expected_metrics["profit_eur"],
                "realized_revenue_eur": realized_metrics["revenue_eur"],
                "realized_energy_cost_eur": realized_metrics["energy_cost_eur"],
                "degradation_eur": realized_metrics["degradation_eur"],
                "energy_bought_mwh": realized_metrics["energy_bought_mwh"],
                "energy_sold_mwh": realized_metrics["energy_sold_mwh"],
                "throughput_mwh": realized_metrics["throughput_mwh"],
                "equivalent_cycles": realized_metrics["equivalent_cycles"],
                "profit_per_mwh_throughput": realized_metrics["profit_per_mwh_throughput"],
                "avg_buy_price_eur_mwh": realized_metrics["avg_buy_price_eur_mwh"],
                "avg_sell_price_eur_mwh": realized_metrics["avg_sell_price_eur_mwh"],
                "active_intervals": realized_metrics["active_intervals"],
                "idle_intervals": realized_metrics["idle_intervals"],
                "objective_risk_adjusted_eur": expected_metrics["objective_risk_adjusted_eur"],
            }
        )

    schedule_df = pd.concat(schedules, ignore_index=True)
    daily_df = pd.DataFrame(daily_rows)
    capex_eur = args.energy_mwh * args.capex_eur_per_mwh
    summary = summarize_daily(
        daily_df,
        capex_eur=capex_eur,
        risk_free_rate_pct=args.risk_free_rate_pct,
    )
    summary.update(
        {
            "forecast_csv": str(args.forecast_csv),
            "battery_power_mw": args.power_mw,
            "battery_energy_mwh": args.energy_mwh,
            "degradation_eur_mwh": args.degradation_eur_mwh,
            "risk_lambda": args.risk_lambda,
            "max_cycles": args.max_cycles,
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.year}_forecast_optimizer"
    schedule_path = args.output_dir / f"{prefix}_schedule.csv"
    daily_path = args.output_dir / f"{prefix}_daily.csv"
    summary_path = args.output_dir / f"{prefix}_summary.csv"

    schedule_df.to_csv(schedule_path, index=False)
    daily_df.to_csv(daily_path, index=False)
    pd.DataFrame([summary]).to_csv(summary_path, index=False)

    print("\n=== One-year forecast + optimiser backtest ===")
    print(f"Forecast CSV: {args.forecast_csv}")
    print(f"Eligible days: {summary['days']} | {summary['start_date']} -> {summary['end_date']}")
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
        "risk_free_rate_pct",
        "annualized_return_pct",
        "annualized_excess_return_pct",
        "annualized_return_sharpe",
        "annualized_return_sortino",
        "annualized_pnl_sharpe",
        "max_drawdown_eur",
        "cvar5_daily_profit_eur",
        "total_throughput_mwh",
        "mean_equivalent_cycles_per_day",
        "forecast_vs_realized_profit_eur",
    ]:
        value = summary[key]
        if isinstance(value, float):
            print(f"  {key}: {value:,.4f}")
        else:
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
