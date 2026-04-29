from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_E_NOM_MWH = 300.0
DEFAULT_CAPITAL_MULTIPLIER = 20.0


def tier_number_from_name(path: Path) -> int:
    match = re.search(r"tier[_-]?(\d+)", path.stem.lower())
    return int(match.group(1)) if match else 9999


def load_module_from_path(path: Path):
    module_name = f"_tier_module_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)

    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    return module


def discover_tier_files(tiers_dir: Path) -> list[Path]:
    files = []

    for path in tiers_dir.iterdir():
        if not path.is_file():
            continue

        if path.name.startswith("run_all_tiers"):
            continue

        if re.match(r"tier[_-]?\d+", path.stem.lower()) and path.suffix in [".py", ""]:
            files.append(path)

    return sorted(files, key=tier_number_from_name)


def estimate_battery_capital(
    forecast_csv: str | Path,
    e_nom_mwh: float = DEFAULT_E_NOM_MWH,
    capital_multiplier: float = DEFAULT_CAPITAL_MULTIPLIER,
) -> float:
    df = pd.read_csv(forecast_csv)

    if "p50_eur_mwh" not in df.columns:
        raise ValueError("Forecast CSV must contain p50_eur_mwh to estimate capital.")

    avg_price = df["p50_eur_mwh"].mean()

    energy_value = e_nom_mwh * avg_price

    return energy_value * capital_multiplier


def normalize_metrics(
    tier_name: str,
    metrics: dict[str, Any],
    capital_base_eur: float,
) -> dict[str, Any]:
    profit_keys = [
        "realized_profit_eur",
        "expected_profit_eur",
        "profit (€)",
        "profit_eur",
        "expected_profit",
    ]

    profit = None

    for key in profit_keys:
        if key in metrics:
            profit = float(metrics[key])
            break

    if profit is None:
        raise ValueError(
            f"{tier_name}: could not find profit metric. "
            f"Available metrics: {list(metrics.keys())}"
        )

    final_value = capital_base_eur + profit
    return_pct = (profit / capital_base_eur) * 100

    row = {
        "tier": tier_name,
        "capital_base_eur": capital_base_eur,
        "profit_eur": profit,
        "final_value_eur": final_value,
        "return_pct": return_pct,
    }

    for k, v in metrics.items():
        if isinstance(v, (int, float)):
            row[k] = float(v)
        else:
            row[k] = v

    return row


def run_tier_module(module, forecast_csv: str, capital_base_eur: float):
    if hasattr(module, "run_tier"):
        return module.run_tier(
            forecast_csv=forecast_csv,
            capital_base_eur=capital_base_eur,
        )

    if all(hasattr(module, name) for name in ["load_data", "optimize_battery", "evaluate"]):
        df = module.load_data(forecast_csv)
        result_df = module.optimize_battery(df)
        return module.evaluate(result_df)

    if all(
        hasattr(module, name)
        for name in [
            "load_forecast",
            "generate_price_scenarios",
            "optimize_tier1_cvar",
            "naive_rank_strategy",
            "calculate_tier_metrics",
        ]
    ):
        df = module.load_forecast(forecast_csv)
        scenarios = module.generate_price_scenarios(
            df,
            n_scenarios=module.Risk.n_scenarios,
            seed=module.Risk.seed,
        )
        schedule, _, _ = module.optimize_tier1_cvar(df, scenarios)
        naive = module.naive_rank_strategy(df)
        return module.calculate_tier_metrics(schedule, scenarios, naive_schedule=naive)

    if all(
        hasattr(module, name)
        for name in [
            "load_forecast",
            "generate_curve_aware_scenarios",
            "optimize_tier2_curve_cvar",
            "naive_rank_strategy",
            "calculate_metrics",
        ]
    ):
        df = module.load_forecast(forecast_csv)
        scenarios = module.generate_curve_aware_scenarios(
            df,
            n_scenarios=module.Risk.n_scenarios,
            seed=module.Risk.seed,
        )
        schedule, _, _ = module.optimize_tier2_curve_cvar(df, scenarios)
        naive = module.naive_rank_strategy(df)
        return module.calculate_metrics(schedule, scenarios, naive_schedule=naive)

    if all(
        hasattr(module, name)
        for name in [
            "load_forecast",
            "generate_tier3_scenarios",
            "optimize_tier3",
            "naive_rank_strategy",
            "calculate_metrics",
        ]
    ):
        df = module.load_forecast(forecast_csv)
        scenarios = module.generate_tier3_scenarios(
            df,
            n_scenarios=module.Risk.n_scenarios,
            seed=module.Risk.seed,
        )
        schedule, _ = module.optimize_tier3(df, scenarios)
        naive = module.naive_rank_strategy(df)
        metrics, _ = module.calculate_metrics(schedule, scenarios, naive_schedule=naive)
        return metrics

    if all(
        hasattr(module, name)
        for name in [
            "load_forecast",
            "build_tier4_scenario_tree",
            "progressive_hedging",
            "calculate_tier4_metrics",
        ]
    ):
        df = module.load_forecast(forecast_csv)
        scenarios = module.build_tier4_scenario_tree(df)
        solutions, _, _ = module.progressive_hedging(scenarios)
        return module.calculate_tier4_metrics(scenarios, solutions)

    raise RuntimeError(
        f"Could not run module {module.__name__}. "
        f"Add run_tier(forecast_csv, capital_base_eur) to the file."
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--forecast-csv", default="synthetic_forecast_day.csv")
    parser.add_argument("--tiers-dir", default="optimisation")
    parser.add_argument("--output", default="tier_comparison_results.csv")

    parser.add_argument(
        "--capital-base",
        type=float,
        default=None,
        help="Manual capital base in EUR. If omitted, it is estimated from battery size and prices.",
    )

    parser.add_argument("--e-nom-mwh", type=float, default=DEFAULT_E_NOM_MWH)

    parser.add_argument(
        "--capital-multiplier",
        type=float,
        default=DEFAULT_CAPITAL_MULTIPLIER,
        help="Multiplier applied to E_nom × avg_price to create realistic capital base.",
    )

    args = parser.parse_args()

    tiers_dir = Path(args.tiers_dir)
    forecast_csv = Path(args.forecast_csv)

    if args.capital_base is not None:
        capital_base_eur = args.capital_base
    else:
        capital_base_eur = estimate_battery_capital(
            forecast_csv=forecast_csv,
            e_nom_mwh=args.e_nom_mwh,
            capital_multiplier=args.capital_multiplier,
        )

    tier_files = discover_tier_files(tiers_dir)

    if not tier_files:
        raise RuntimeError(f"No tier files found in {tiers_dir}")

    rows = []

    print("\n=== Running all tiers ===")
    print(f"Forecast CSV: {forecast_csv}")
    print(f"Capital base: €{capital_base_eur:,.2f}")
    print()

    for path in tier_files:
        tier_name = path.stem
        print(f"[RUNNING] {tier_name}")

        try:
            module = load_module_from_path(path)

            metrics = run_tier_module(
                module=module,
                forecast_csv=str(forecast_csv),
                capital_base_eur=capital_base_eur,
            )

            row = normalize_metrics(
                tier_name=tier_name,
                metrics=metrics,
                capital_base_eur=capital_base_eur,
            )

            rows.append(row)

            print(
                f"  profit: €{row['profit_eur']:,.2f} | "
                f"return: {row['return_pct']:,.3f}% | "
                f"final value: €{row['final_value_eur']:,.2f}"
            )

        except Exception as e:
            print(f"  FAILED: {e}")

            rows.append({
                "tier": tier_name,
                "capital_base_eur": capital_base_eur,
                "profit_eur": None,
                "final_value_eur": None,
                "return_pct": None,
                "error": str(e),
            })

    results = pd.DataFrame(rows)

    results = results.sort_values(
        by="return_pct",
        ascending=False,
        na_position="last",
    )

    output_path = Path(args.output)
    results.to_csv(output_path, index=False)

    print("\n=== Tier comparison ===")

    display_cols = [
        "tier",
        "capital_base_eur",
        "profit_eur",
        "final_value_eur",
        "return_pct",
    ]

    available_cols = [c for c in display_cols if c in results.columns]
    print(results[available_cols].to_string(index=False))

    print(f"\nSaved results to: {output_path}")


if __name__ == "__main__":
    main()