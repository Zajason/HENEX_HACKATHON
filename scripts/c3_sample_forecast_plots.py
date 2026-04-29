"""
C3: Sample forecast plots — winter day, summer day, 2025 negative-price day.

Visual sanity check on the forecast layer. For each chosen day we plot:
  - Realized DAM price (solid line)
  - Forecast P10/P50/P90 fan
  - Twin axis: load_forecast_mw and res_forecast_mw (from history.parquet)

Day selection:
  - Winter:           --winter-date YYYY-MM-DD     (default: search Jan)
  - Summer:           --summer-date YYYY-MM-DD     (default: search Jul)
  - Negative-price:   automatic — picks the 2025 day with the most rows
                      where realized price < 0; if none exists, picks the
                      day with the lowest realized minimum and labels it
                      "lowest 2025 price day".

Source variant defaults to v1_with_weather; falls back to v0_no_weather.

Output: reports/plots/<date>_<label>_<variant>.png
"""

import sys
sys.path.insert(0, ".")

import argparse
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

LABEL = "dam_price_eur_mwh"

VARIANTS = {
    "v1_with_weather": Path("data/processed/forecast_walkforward_v1_with_weather.parquet"),
    "v0_no_weather": Path("data/processed/forecast_walkforward_v0_no_weather.parquet"),
}
HISTORY_PATH = Path("data/processed/history.parquet")
PLOTS_DIR = Path("reports/plots")


def pick_variant(preferred: str | None) -> tuple[str, Path]:
    if preferred:
        path = VARIANTS.get(preferred)
        if path is None or not path.exists():
            raise SystemExit(f"variant {preferred} not on disk")
        return preferred, path
    for name, path in VARIANTS.items():
        if path.exists():
            return name, path
    raise SystemExit("no walk-forward parquet found. run B4 / B6 first.")


def load_predictions(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    return df.sort_values("timestamp").reset_index(drop=True)


def attach_history(preds: pd.DataFrame) -> pd.DataFrame:
    if not HISTORY_PATH.exists():
        return preds
    cols_needed = ["timestamp", "load_forecast_mw", "res_forecast_mw"]
    hist = pd.read_parquet(HISTORY_PATH, columns=cols_needed)
    hist["timestamp"] = pd.to_datetime(hist["timestamp"]).dt.tz_localize(None)
    return preds.merge(hist, on="timestamp", how="left")


def find_winter_day(preds: pd.DataFrame, hint: str | None) -> str:
    if hint:
        return hint
    winter = preds[preds["timestamp"].dt.month.isin([12, 1, 2])]
    if winter.empty:
        return preds["timestamp"].dt.normalize().iloc[0].strftime("%Y-%m-%d")
    return winter["timestamp"].dt.normalize().mode().iloc[0].strftime("%Y-%m-%d")


def find_summer_day(preds: pd.DataFrame, hint: str | None) -> str:
    if hint:
        return hint
    summer = preds[preds["timestamp"].dt.month.isin([6, 7, 8])]
    if summer.empty:
        return preds["timestamp"].dt.normalize().iloc[-1].strftime("%Y-%m-%d")
    return summer["timestamp"].dt.normalize().mode().iloc[0].strftime("%Y-%m-%d")


def find_negative_price_day(preds: pd.DataFrame) -> tuple[str, str]:
    """Returns (date_iso, label) — label notes whether it's truly negative."""
    p25 = preds[preds["timestamp"].dt.year == 2025].copy()
    if p25.empty:
        p25 = preds.copy()
    p25["date"] = p25["timestamp"].dt.normalize()

    neg = p25[p25[LABEL] < 0]
    if not neg.empty:
        counts = neg.groupby("date").size().sort_values(ascending=False)
        return counts.index[0].strftime("%Y-%m-%d"), "negative"

    # fallback: pick the day with the lowest realized minimum
    daily_min = p25.groupby("date")[LABEL].min().sort_values()
    return daily_min.index[0].strftime("%Y-%m-%d"), "lowest"


def plot_day(day_df: pd.DataFrame, date_iso: str, label: str,
             variant: str, out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    ts = day_df["timestamp"]

    ax.fill_between(ts, day_df["p10_eur_mwh"], day_df["p90_eur_mwh"],
                    alpha=0.18, color="#3b82f6", label="P10-P90")
    ax.plot(ts, day_df["p50_eur_mwh"], color="#1d4ed8", lw=1.5, label="P50")
    ax.plot(ts, day_df[LABEL], color="black", lw=1.4, label="realized")
    ax.axhline(0.0, color="grey", lw=0.7, ls="--")
    ax.set_ylabel("EUR / MWh")
    ax.set_xlabel("delivery time (Europe/Athens)")
    ax.set_title(f"{date_iso} — {label} day — {variant}")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.3)

    if "load_forecast_mw" in day_df.columns and day_df["load_forecast_mw"].notna().any():
        ax2 = ax.twinx()
        ax2.plot(ts, day_df["load_forecast_mw"], color="#dc2626",
                 lw=1.0, alpha=0.7, label="load fcst")
        if "res_forecast_mw" in day_df.columns:
            ax2.plot(ts, day_df["res_forecast_mw"], color="#16a34a",
                     lw=1.0, alpha=0.7, label="RES fcst")
        ax2.set_ylabel("MW", color="#525252")
        ax2.tick_params(axis="y", colors="#525252")
        ax2.legend(loc="upper right")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    print(f"[C3] wrote {out_path}")


def slice_day(preds: pd.DataFrame, date_iso: str) -> pd.DataFrame:
    day_start = pd.Timestamp(date_iso)
    day_end = day_start + pd.Timedelta(days=1)
    out = preds[(preds["timestamp"] >= day_start) & (preds["timestamp"] < day_end)]
    if out.empty:
        raise SystemExit(f"no predictions for {date_iso} in chosen variant.")
    return out.copy()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--variant", choices=list(VARIANTS), default=None)
    p.add_argument("--winter-date", default=None,
                   help="ISO date for winter sample; default auto-pick from Dec/Jan/Feb")
    p.add_argument("--summer-date", default=None,
                   help="ISO date for summer sample; default auto-pick from Jun/Jul/Aug")
    p.add_argument("--out-dir", type=Path, default=PLOTS_DIR)
    args = p.parse_args()

    variant, path = pick_variant(args.variant)
    print(f"[C3] reading {variant} from {path}")
    preds = attach_history(load_predictions(path))
    print(f"[C3] {len(preds):,} prediction rows")

    days = []
    days.append((find_winter_day(preds, args.winter_date), "winter"))
    days.append((find_summer_day(preds, args.summer_date), "summer"))
    neg_date, neg_label = find_negative_price_day(preds)
    days.append((neg_date, f"{neg_label}_2025"))

    for date_iso, kind in days:
        try:
            day_df = slice_day(preds, date_iso)
        except SystemExit as e:
            print(f"[C3] skip {kind} {date_iso}: {e}")
            continue
        out_path = args.out_dir / f"{date_iso}_{kind}_{variant}.png"
        plot_day(day_df, date_iso, kind, variant, out_path)


if __name__ == "__main__":
    main()
