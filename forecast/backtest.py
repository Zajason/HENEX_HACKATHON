"""Rolling-origin backtest utilities for forecast models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any

import pandas as pd

from forecast.features import LABEL_COL
from forecast.metrics import pinball_loss, coverage

QUANTILE_COLS = {
    0.1: "p10_eur_mwh",
    0.5: "p50_eur_mwh",
    0.9: "p90_eur_mwh",
}


@dataclass
class BacktestResult:
    predictions: pd.DataFrame
    summary: pd.DataFrame
    by_year: pd.DataFrame
    by_hour: pd.DataFrame
    by_regime: pd.DataFrame | None


def load_history_frame(path: Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"History file not found: {path}")
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    else:
        raise ValueError(f"Unsupported history format: {path.suffix}")
    if "timestamp" not in df.columns:
        raise ValueError("History frame must contain a timestamp column.")
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_localize(None)
    return df.sort_values("timestamp").reset_index(drop=True)


def run_walk_forward_backtest(
    df: pd.DataFrame,
    model_factory: Callable[[pd.DataFrame], Any],
    initial_window: pd.Timedelta,
    step: pd.Timedelta,
    horizon: pd.Timedelta,
    min_train_rows: int = 1000,
) -> BacktestResult:
    """Train on [start, origin), predict [origin, origin + horizon), slide."""
    data = _clean_history(df)
    start = data["timestamp"].min()
    end = data["timestamp"].max()
    origin = start + initial_window

    frames: list[pd.DataFrame] = []
    fold = 0
    while origin <= end:
        holdout_end = origin + horizon
        train = data[data["timestamp"] < origin].copy()
        holdout = data[
            (data["timestamp"] >= origin) & (data["timestamp"] < holdout_end)
        ].copy()

        if len(train) >= min_train_rows and not holdout.empty:
            model = model_factory(train)
            pred = _predict_model(model, holdout)
            merged = holdout[["timestamp", LABEL_COL]].merge(
                pred, on="timestamp", how="inner"
            )
            if not merged.empty:
                merged["fold"] = fold
                merged["train_end"] = origin
                frames.append(merged)
                fold += 1

        origin = origin + step

    if not frames:
        raise ValueError(
            "Walk-forward backtest produced no folds. "
            "Use a smaller initial window/min_train_rows or wait for more history."
        )

    predictions = pd.concat(frames, ignore_index=True)
    return summarize_backtest(predictions)


def summarize_backtest(predictions: pd.DataFrame) -> BacktestResult:
    preds = predictions.copy()
    preds["timestamp"] = pd.to_datetime(preds["timestamp"])
    summary = _metric_frame(preds)

    by_year = _group_metric_frame(
        preds.assign(year=preds["timestamp"].dt.year), "year"
    )

    by_hour = _group_metric_frame(
        preds.assign(hour=preds["timestamp"].dt.hour), "hour"
    )

    by_regime = None
    if "regime" in preds.columns:
        by_regime = _group_metric_frame(preds, "regime")

    return BacktestResult(
        predictions=preds,
        summary=summary,
        by_year=by_year,
        by_hour=by_hour,
        by_regime=by_regime,
    )


def _clean_history(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", LABEL_COL, "load_forecast_mw", "res_forecast_mw"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"History frame missing required columns: {missing}")

    data = df.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"]).dt.tz_localize(None)
    data = data.dropna(subset=required)
    return data.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def _predict_model(model: Any, holdout: pd.DataFrame) -> pd.DataFrame:
    if hasattr(model, "predict"):
        return model.predict(holdout)
    if hasattr(model, "predict_hourly"):
        return model.predict_hourly(holdout)
    raise TypeError("Model must expose predict(df) or predict_hourly(df).")


def _metric_frame(df: pd.DataFrame) -> pd.DataFrame:
    row = _metric_row(df)
    return pd.DataFrame([row])


def _group_metric_frame(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(group_col):
        metrics = _metric_row(group).to_dict()
        rows.append({group_col: key, **metrics})
    return pd.DataFrame(rows)


def _metric_row(df: pd.DataFrame) -> pd.Series:
    y = df[LABEL_COL].to_numpy()
    metrics = {
        "rows": len(df),
        "pinball_p10": pinball_loss(y, df[QUANTILE_COLS[0.1]].to_numpy(), 0.1),
        "pinball_p50": pinball_loss(y, df[QUANTILE_COLS[0.5]].to_numpy(), 0.5),
        "pinball_p90": pinball_loss(y, df[QUANTILE_COLS[0.9]].to_numpy(), 0.9),
        "coverage_p10_p90": coverage(
            y,
            df[QUANTILE_COLS[0.1]].to_numpy(),
            df[QUANTILE_COLS[0.9]].to_numpy(),
        ),
    }
    metrics["pinball_avg"] = (
        metrics["pinball_p10"] + metrics["pinball_p50"] + metrics["pinball_p90"]
    ) / 3.0
    return pd.Series(metrics)
