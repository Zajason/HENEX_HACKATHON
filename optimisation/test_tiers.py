from __future__ import annotations

import argparse
import importlib.util
import inspect
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "synthetic_many_days"


EXCLUDE_FILES = {
    "run_all_tiers.py",
    "run_synthetic_multiday_backtest.py",
    "__init__.py",
}


def generate_forecast_day(date: str, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    ts = pd.date_range(date, periods=96, freq="15min")
    hour = (ts.hour + ts.minute / 60).to_numpy()

    base = (
        42
        + 18 * np.exp(-((hour - 8) ** 2) / 5)
        - 12 * np.exp(-((hour - 13) ** 2) / 7)
        + 48 * np.exp(-((hour - 18.7) ** 2) / 5)
        + 4 * np.sin(2 * np.pi * hour / 24)
    )

    noise = rng.normal(0, 4.0, len(ts))
    p50 = np.clip(base + noise, -20, 250)

    uncertainty = (
        14
        + 10 * np.exp(-((hour - 12.5) ** 2) / 10)
        + 24 * np.exp(-((hour - 18.8) ** 2) / 5)
        + rng.normal(0, 1.2, len(ts))
    )
    uncertainty = np.clip(uncertainty, 8, 55)

    p10 = p50 - uncertainty / 2
    p90 = p50 + uncertainty / 2

    # Structural fundamentals for Tier 3
    load = (
        5200
        + 600 * np.exp(-((hour - 9) ** 2) / 8)
        + 1100 * np.exp(-((hour - 20) ** 2) / 10)
        + rng.normal(0, 100, len(ts))
    )

    solar = 2600 * np.exp(-((hour - 13) ** 2) / 10)
    solar[(hour < 6) | (hour > 20)] = 0

    wind = 1000 + 300 * np.sin((hour - 2) * np.pi / 12) + rng.normal(0, 90, len(ts))
    wind = np.clip(wind, 200, None)

    res = solar + wind

    return pd.DataFrame({
        "timestamp": ts,
        "hour": hour,
        "p10_eur_mwh": p10,
        "p50_eur_mwh": p50,
        "p90_eur_mwh": p90,
        "uncertainty_band": p90 - p10,
        "load_forecast_mw": load,
        "solar_forecast_mw": solar,
        "wind_forecast_mw": wind,
        "res_forecast_mw": res,
    })


def generate_intraday_from_forecast(forecast: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    p50 = forecast["p50_eur_mwh"].to_numpy()
    hour = forecast["hour"].to_numpy()
    uncertainty = forecast["uncertainty_band"].to_numpy()

    noise = rng.normal(0, 0.22 * uncertainty)

    # Mild autocorrelation
    for t in range(1, len(noise)):
        noise[t] = 0.70 * noise[t - 1] + 0.30 * noise[t]

    evening_surprise = rng.normal(0, 8) * np.exp(-((hour - 18.8) ** 2) / 4)
    midday_surprise = rng.normal(0, 5) * np.exp(-((hour - 13) ** 2) / 6)

    intraday = p50 + noise + evening_surprise - midday_surprise
    intraday = np.clip(intraday, -80, 600)

    return pd.DataFrame({
        "timestamp": forecast["timestamp"],
        "hour": forecast["hour"],
        "intraday_p50_eur_mwh": intraday,
    })


def discover_tiers() -> list[Path]:
    files = []
    for path in ROOT.glob("tier*.py"):
        if path.name in EXCLUDE_FILES:
            continue
        files.append(path)
    return sorted(files)


def import_module_from_path(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_one_tier(module, forecast_csv: str, intraday_csv: str, capital_base_eur: float) -> dict:
    if not hasattr(module, "run_tier"):
        raise AttributeError("No run_tier() function found.")

    fn = module.run_tier
    sig = inspect.signature(fn)

    kwargs = {}

    if "forecast_csv" in sig.parameters:
        kwargs["forecast_csv"] = forecast_csv
    elif "forecast_path" in sig.parameters:
        kwargs["forecast_path"] = forecast_csv

    if "capital_base_eur" in sig.parameters:
        kwargs["capital_base_eur"] = capital_base_eur

    if "intraday_csv" in sig.parameters:
        kwargs["intraday_csv"] = intraday_csv

    result = fn(**kwargs)

    if not isinstance(result, dict):
        raise TypeError("run_tier() must return a dict.")

    return result


def extract_profit(metrics: dict) -> float:
    for key in [
        "realized_profit_eur",
        "expected_profit_eur",
        "profit_eur",
        "tier7_total_profit_eur",
        "tier6_dam_plus_intraday_adjustment_profit_eur",
    ]:
        if key in metrics and pd.notna(metrics[key]):
            return float(metrics[key])

    raise KeyError(f"No profit key found. Available keys: {list(metrics.keys())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--start-date", default="2026-04-29")
    parser.add_argument("--capital-base-eur", type=float, default=347_913.057241)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tier_files = discover_tiers()

    print("\nDiscovered tiers:")
    for f in tier_files:
        print(f"  - {f.name}")

    all_rows = []

    dates = pd.date_range(args.start_date, periods=args.days, freq="D")

    for day_idx, date in enumerate(dates):
        date_str = date.strftime("%Y-%m-%d")
        print(f"\n=== Synthetic day {day_idx + 1}/{args.days}: {date_str} ===")

        forecast = generate_forecast_day(date_str, seed=args.seed + day_idx)
        intraday = generate_intraday_from_forecast(forecast, seed=args.seed + 10_000 + day_idx)

        forecast_path = OUT_DIR / f"forecast_{date_str}.csv"
        intraday_path = OUT_DIR / f"intraday_{date_str}.csv"

        forecast.to_csv(forecast_path, index=False)
        intraday.to_csv(intraday_path, index=False)

        for tier_file in tier_files:
            tier_name = tier_file.stem

            try:
                module = import_module_from_path(tier_file)

                metrics = run_one_tier(
                    module=module,
                    forecast_csv=str(forecast_path),
                    intraday_csv=str(intraday_path),
                    capital_base_eur=args.capital_base_eur,
                )

                profit = extract_profit(metrics)
                final_value = args.capital_base_eur + profit
                return_pct = 100 * profit / args.capital_base_eur

                row = {
                    "date": date_str,
                    "tier": tier_name,
                    "capital_base_eur": args.capital_base_eur,
                    "profit_eur": profit,
                    "final_value_eur": final_value,
                    "return_pct": return_pct,
                    "status": "ok",
                }

                row.update({
                    f"metric_{k}": v
                    for k, v in metrics.items()
                    if isinstance(v, (int, float, np.integer, np.floating))
                })

                print(f"{tier_name:35s} profit={profit:>10,.2f} return={return_pct:>7.3f}%")

            except Exception as e:
                row = {
                    "date": date_str,
                    "tier": tier_name,
                    "capital_base_eur": args.capital_base_eur,
                    "profit_eur": np.nan,
                    "final_value_eur": np.nan,
                    "return_pct": np.nan,
                    "status": f"failed: {type(e).__name__}: {e}",
                }

                print(f"{tier_name:35s} FAILED: {type(e).__name__}: {e}")

            all_rows.append(row)

    daily_df = pd.DataFrame(all_rows)
    daily_path = OUT_DIR / "tier_multiday_daily_results.csv"
    daily_df.to_csv(daily_path, index=False)

    ok_df = daily_df[daily_df["status"].eq("ok")].copy()

    summary = (
        ok_df.groupby("tier", as_index=False)
        .agg(
            days_tested=("date", "count"),
            total_profit_eur=("profit_eur", "sum"),
            mean_daily_profit_eur=("profit_eur", "mean"),
            std_daily_profit_eur=("profit_eur", "std"),
            mean_daily_return_pct=("return_pct", "mean"),
            total_return_pct=("profit_eur", lambda x: 100 * x.sum() / (args.capital_base_eur * len(x))),
        )
        .sort_values("total_profit_eur", ascending=False)
    )

    summary["final_value_eur"] = args.capital_base_eur * summary["days_tested"] + summary["total_profit_eur"]

    summary_path = OUT_DIR / "tier_multiday_summary.csv"
    summary.to_csv(summary_path, index=False)

    print("\n=== MULTI-DAY SUMMARY ===")
    print(summary.to_string(index=False, float_format=lambda x: f"{x:,.3f}"))

    print("\nSaved:")
    print(f"- {daily_path}")
    print(f"- {summary_path}")
    print(f"- synthetic forecast/intraday files in {OUT_DIR}")


if __name__ == "__main__":
    main()