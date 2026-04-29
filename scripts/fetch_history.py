"""Phase A batch builder: HEnEx DAM + IPTO load/RES -> history.parquet.

This fills the file expected by Phase B:

    data/processed/history.parquet

It intentionally does not merge ERA5 weather. Run scripts.a5_merge_era5_weather
after this if the ERA5 NetCDF files are available.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from data_pipeline import (
    RAW_DIR,
    build_ipto_load_url,
    build_ipto_res_url,
    download_file,
    download_henex_historical_archive,
    parse_ipto_forecast,
)
from forecast.io import attach_macro, load_dam_history, load_macro_history

IPTO_DIR = RAW_DIR / "ipto_history"
LOAD_DIR = IPTO_DIR / "load"
RES_DIR = IPTO_DIR / "res"
DEFAULT_OUT = Path("data") / "processed" / "history.parquet"


def _download_ipto_with_version_fallback(
    date: str,
    kind: str,
    versions: tuple[str, ...],
    overwrite: bool = False,
) -> Path | None:
    if kind == "load":
        out_dir = LOAD_DIR
        url_builder = build_ipto_load_url
        suffix = "load"
    elif kind == "res":
        out_dir = RES_DIR
        url_builder = build_ipto_res_url
        suffix = "res"
    else:
        raise ValueError(f"unknown IPTO kind: {kind}")

    out_dir.mkdir(parents=True, exist_ok=True)
    for version in versions:
        out_path = out_dir / f"{date}_{suffix}_v{version}.xlsx"
        if out_path.exists() and not overwrite:
            return out_path
        try:
            return download_file(url_builder(date, version=version), out_path, overwrite=overwrite)
        except Exception as exc:
            print(f"[MISS] IPTO {kind} {date} v{version}: {exc}")
    return None


def download_ipto_history(
    start: str,
    end: str,
    versions: tuple[str, ...],
    overwrite: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range(start=start, end=end, freq="D")
    load_frames = []
    res_frames = []
    misses = []

    for i, ts in enumerate(dates, start=1):
        date = ts.strftime("%Y-%m-%d")
        print(f"[IPTO] {i}/{len(dates)} {date}")
        load_path = _download_ipto_with_version_fallback(date, "load", versions, overwrite)
        res_path = _download_ipto_with_version_fallback(date, "res", versions, overwrite)
        if load_path is None or res_path is None:
            misses.append(date)
            continue

        try:
            load_frames.append(parse_ipto_forecast(load_path, "load_forecast_mw", date))
            res_frames.append(parse_ipto_forecast(res_path, "res_forecast_mw", date))
        except Exception as exc:
            print(f"[MISS] IPTO parse {date}: {exc}")
            misses.append(date)

    if not load_frames or not res_frames:
        raise SystemExit("No IPTO history could be parsed.")

    load = (
        pd.concat(load_frames, ignore_index=True)
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    res = (
        pd.concat(res_frames, ignore_index=True)
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    out_dir = Path("data") / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    load.to_parquet(out_dir / "ipto_load_history.parquet", index=False)
    res.to_parquet(out_dir / "ipto_res_history.parquet", index=False)

    if misses:
        miss_path = out_dir / "ipto_history_misses.csv"
        pd.DataFrame({"date": misses}).to_csv(miss_path, index=False)
        print(f"[IPTO] wrote misses -> {miss_path} ({len(misses)} dates)")

    print(f"[IPTO] load rows: {len(load):,} | res rows: {len(res):,}")
    return load, res


def build_history(
    start: str,
    end: str,
    versions: tuple[str, ...],
    out_path: Path,
    skip_henex_download: bool,
    overwrite_ipto: bool,
) -> Path:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end) + pd.Timedelta(days=1)
    years = list(range(start_ts.year, pd.Timestamp(end).year + 1))

    if not skip_henex_download:
        download_henex_historical_archive(
            years=years,
            include_results=True,
            include_curves=False,
            extract=True,
            overwrite=False,
        )

    print("[HEnEx] loading DAM archive")
    dam = load_dam_history()
    dam = dam[(dam["timestamp"] >= start_ts) & (dam["timestamp"] < end_ts)].copy()
    if dam.empty:
        raise SystemExit(f"No HEnEx DAM rows found for {start} -> {end}.")
    print(f"[HEnEx] rows: {len(dam):,} | {dam['timestamp'].min()} -> {dam['timestamp'].max()}")

    load, res = download_ipto_history(start, end, versions, overwrite=overwrite_ipto)

    history = dam.merge(load, on="timestamp", how="left")
    history = history.merge(res, on="timestamp", how="left")

    macro = load_macro_history()
    if not macro.empty:
        history = attach_macro(history, macro)
        print(f"[history] macro merged: {list(macro.columns)}")
    else:
        print("[history] WARNING: no macro_drivers_*.csv found; skipping TTF/EUA")

    history = history.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    needed = ["load_forecast_mw", "res_forecast_mw"]
    macro_value_cols = [c for c in macro.columns if c != "date"] if not macro.empty else []
    needed = needed + macro_value_cols
    coverage = history[needed].notna().mean().mul(100).round(1)
    print("[history] coverage:")
    for col, pct in coverage.items():
        print(f"  {col}: {pct:.1f}%")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    history.to_parquet(out_path, index=False)
    print(f"[history] wrote {out_path} ({len(history):,} rows)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2023-01-01")
    parser.add_argument("--end", default="2025-12-31")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--versions",
        default="02,01,03,04",
        help="comma-separated IPTO version fallback order",
    )
    parser.add_argument("--skip-henex-download", action="store_true")
    parser.add_argument("--overwrite-ipto", action="store_true")
    args = parser.parse_args()

    versions = tuple(v.strip().removeprefix("v") for v in args.versions.split(",") if v.strip())
    build_history(
        start=args.start,
        end=args.end,
        versions=versions,
        out_path=args.out,
        skip_henex_download=args.skip_henex_download,
        overwrite_ipto=args.overwrite_ipto,
    )


if __name__ == "__main__":
    main()

