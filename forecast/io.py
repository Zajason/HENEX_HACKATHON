"""Load DAM history from the HEnEx archive and stitch it to forecast features.

The archive layout is uneven across years (nested folders, an unexpanded inner
zip in 2025). This module walks the extracted tree recursively, extracts any
inner zips it finds, and returns a single training DataFrame.
"""

from __future__ import annotations

from pathlib import Path
import zipfile

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

ARCHIVE_EXTRACTED_DIR = RAW_DIR / "henex_archive" / "extracted"
MACRO_DIR = RAW_DIR / "macro"

DAM_FILE_PATTERN = "*_EL-DAM_Results_EN_v*.xlsx"


def _expand_nested_zips(root: Path) -> None:
    """Extract any *.zip files found beneath `root` into siblings, in place."""
    for zip_path in root.rglob("*.zip"):
        if not zip_path.is_file():
            continue
        out_dir = zip_path.with_suffix("")
        marker = out_dir / ".extracted"
        if marker.exists():
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(out_dir)
            marker.touch()
        except (zipfile.BadZipFile, PermissionError, OSError):
            continue


def find_archive_dam_files(root: Path = ARCHIVE_EXTRACTED_DIR) -> list[Path]:
    _expand_nested_zips(root)
    files = sorted(root.rglob(DAM_FILE_PATTERN))
    if not files:
        raise FileNotFoundError(
            f"No DAM result files found beneath {root}. "
            "Did data_pipeline.download_henex_historical_archive run?"
        )
    return files


def parse_dam_file(path: Path) -> pd.DataFrame:
    """Parse one EL-DAM_Results_EN_v##.xlsx into a tidy frame.

    Returns columns: timestamp, dam_price_eur_mwh, delivery_duration.
    Handles both hourly (pre-2025-10-01) and 15-min files transparently.
    """
    df = pd.read_excel(path)
    df.columns = (
        df.columns.astype(str).str.strip().str.upper().str.replace(" ", "_")
    )

    if "DELIVERY_MTU" not in df.columns or "MCP" not in df.columns:
        return pd.DataFrame(
            columns=["timestamp", "dam_price_eur_mwh", "delivery_duration"]
        )

    out = df[["DELIVERY_MTU", "MCP"]].copy()
    if "DELIVERY_DURATION" in df.columns:
        out["DELIVERY_DURATION"] = df["DELIVERY_DURATION"]
    else:
        out["DELIVERY_DURATION"] = 60

    out["timestamp"] = pd.to_datetime(out["DELIVERY_MTU"], errors="coerce")
    out = out.dropna(subset=["timestamp"]).copy()
    out["timestamp"] = out["timestamp"].dt.tz_localize(None)

    out = out.rename(
        columns={
            "MCP": "dam_price_eur_mwh",
            "DELIVERY_DURATION": "delivery_duration",
        }
    )

    # HEnEx files often carry one row per (timestamp, market segment); collapse
    # to one clearing row per timestamp by averaging.
    out = (
        out.groupby("timestamp", as_index=False)
        .agg(
            dam_price_eur_mwh=("dam_price_eur_mwh", "mean"),
            delivery_duration=("delivery_duration", "max"),
        )
    )
    return out


def load_dam_history(root: Path = ARCHIVE_EXTRACTED_DIR) -> pd.DataFrame:
    files = find_archive_dam_files(root)
    frames = []
    for f in files:
        try:
            frames.append(parse_dam_file(f))
        except Exception:
            continue
    if not frames:
        raise RuntimeError("All DAM file parses failed.")
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df["mtu_resolution"] = (df["delivery_duration"] <= 30).map(
        {True: "15min", False: "hourly"}
    )
    return df.reset_index(drop=True)


def load_macro_history() -> pd.DataFrame:
    """Load the latest macro_drivers_*.csv produced by data_pipeline."""
    candidates = sorted(MACRO_DIR.glob("macro_drivers_*.csv"))
    if not candidates:
        return pd.DataFrame(columns=["date"])
    df = pd.read_csv(candidates[-1])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df


def attach_macro(df: pd.DataFrame, macro: pd.DataFrame) -> pd.DataFrame:
    if macro.empty:
        return df
    out = df.copy()
    out["date"] = out["timestamp"].dt.date
    out = out.merge(macro, on="date", how="left").drop(columns=["date"])
    return out


def load_training_history() -> pd.DataFrame:
    """One-call entry point: DAM history + macro drivers, label-ready.

    Returns a frame with columns:
      timestamp, dam_price_eur_mwh, delivery_duration, mtu_resolution,
      ttf_gas_proxy, eua_carbon_proxy
    The forecast features module joins forecast-vintage load / RES / weather
    on top of this label-side frame.
    """
    dam = load_dam_history()
    macro = load_macro_history()
    return attach_macro(dam, macro)


def write_training_history(out_path: Path | None = None) -> Path:
    """Materialize the training history to parquet for fast reload."""
    if out_path is None:
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        out_path = PROCESSED_DIR / "training_history.parquet"
    df = load_training_history()
    try:
        df.to_parquet(out_path, index=False)
    except Exception:
        out_path = out_path.with_suffix(".csv")
        df.to_csv(out_path, index=False)
    return out_path
