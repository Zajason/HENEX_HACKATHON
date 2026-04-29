from pathlib import Path
from datetime import datetime
import requests
import pandas as pd
import zipfile
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
ARCHIVE_DIR = RAW_DIR / "henex_archive"
ARCHIVE_EXTRACTED_DIR = ARCHIVE_DIR / "extracted"

ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def download_file(url: str, output_path: Path, overwrite: bool = False) -> Path:
    if output_path.exists() and not overwrite:
        print(f"[CACHE] {output_path.name}")
        return output_path

    print(f"[DOWNLOAD] {url}")
    r = requests.get(url, timeout=30)

    if r.status_code != 200:
        raise RuntimeError(f"Download failed: {r.status_code} | {url}")

    output_path.write_bytes(r.content)
    return output_path


def build_henex_dam_url(date: str, version: str = "01") -> str:
    d = datetime.strptime(date, "%Y-%m-%d")
    yyyymmdd = d.strftime("%Y%m%d")

    return (
        f"https://www.enexgroup.gr/documents/20126/200106/"
        f"{yyyymmdd}_EL-DAM_Results_EN_v{version}.xlsx"
    )


def build_ipto_load_url(date: str, version: str = "02") -> str:
    d = datetime.strptime(date, "%Y-%m-%d")
    yyyymmdd = d.strftime("%Y%m%d")
    yyyy = d.strftime("%Y")
    mm = d.strftime("%m")

    return (
        f"https://www.admie.gr/sites/default/files/attached-files/type-file/"
        f"{yyyy}/{mm}/{yyyymmdd}_ISP1DayAheadLoadForecast_{version}.xlsx"
    )


def build_ipto_res_url(date: str, version: str = "02") -> str:
    d = datetime.strptime(date, "%Y-%m-%d")
    yyyymmdd = d.strftime("%Y%m%d")
    yyyy = d.strftime("%Y")
    mm = d.strftime("%m")

    return (
        f"https://www.admie.gr/sites/default/files/attached-files/type-file/"
        f"{yyyy}/{mm}/{yyyymmdd}_ISP1DayAheadRESForecast_{version}.xlsx"
    )


def build_open_meteo_url(
    latitude: float = 37.98,
    longitude: float = 23.72,
    forecast_days: int = 1,
) -> str:
    return (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={latitude}"
        f"&longitude={longitude}"
        "&hourly=temperature_2m,wind_speed_10m,shortwave_radiation"
        f"&forecast_days={forecast_days}"
        "&timezone=Europe%2FAthens"
    )


def download_henex_dam(date: str) -> Path:
    url = build_henex_dam_url(date)
    path = RAW_DIR / f"{date}_henex_dam.xlsx"
    return download_file(url, path)


def download_ipto_load(date: str) -> Path:
    url = build_ipto_load_url(date)
    path = RAW_DIR / f"{date}_ipto_load_forecast.xlsx"
    return download_file(url, path)


def download_ipto_res(date: str) -> Path:
    url = build_ipto_res_url(date)
    path = RAW_DIR / f"{date}_ipto_res_forecast.xlsx"
    return download_file(url, path)


def download_open_meteo(date: str) -> Path:
    url = build_open_meteo_url()
    path = RAW_DIR / f"{date}_open_meteo.json"
    return download_file(url, path)


def inspect_excel(path: Path):
    xls = pd.ExcelFile(path)
    print(f"\nFile: {path.name}")
    print("Sheets:", xls.sheet_names)

    for sheet in xls.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, nrows=10)
        print(f"\nSheet: {sheet}")
        print(df.head(10))
        print("Columns:", list(df.columns))


def parse_henex_dam(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)

    df.columns = (
        df.columns.astype(str)
        .str.strip()
        .str.upper()
        .str.replace(" ", "_")
    )

    keep_candidates = [
        "DELIVERY_MTU",
        "DELIVERY_DURATION",
        "MCP",
        "TOTAL_TRADED_VOLUME",
        "TOTAL_VOLUME",
        "TRADED_VOLUME",
    ]

    existing = [c for c in keep_candidates if c in df.columns]
    df = df[existing].copy()

    if "DELIVERY_MTU" not in df.columns or "MCP" not in df.columns:
        raise ValueError(
            f"HEnEx parser could not find required columns. Found: {list(df.columns)}"
        )

    df["timestamp"] = pd.to_datetime(df["DELIVERY_MTU"], errors="coerce")
    df = df.dropna(subset=["timestamp"])

    df = df.rename(columns={
        "MCP": "dam_price_eur_mwh",
        "DELIVERY_DURATION": "delivery_duration",
        "TOTAL_TRADED_VOLUME": "total_traded_volume_mwh",
        "TOTAL_VOLUME": "total_volume_mwh",
        "TRADED_VOLUME": "traded_volume_mwh",
    })

    df["timestamp"] = df["timestamp"].dt.tz_localize(None)

    return df


def parse_ipto_forecast(
    path: Path,
    value_name: str,
    date: str | None = None
) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None)

    values = []

    for _, row in raw.iterrows():
        nums = pd.to_numeric(row, errors="coerce").dropna().tolist()

        if len(nums) >= 90:
            values = nums[-96:]
            break

    if not values:
        raise ValueError(f"Could not find 96 forecast values in {path.name}")

    if date is None:
        date = path.name[:10]

    start = pd.Timestamp(date)

    timestamps = pd.date_range(
        start=start,
        periods=len(values),
        freq="15min"
    )

    return pd.DataFrame({
        "timestamp": timestamps,
        value_name: values
    })


def parse_open_meteo(path: Path) -> pd.DataFrame:
    import json

    with open(path, "r") as f:
        data = json.load(f)

    if "hourly" not in data:
        raise ValueError(f"No 'hourly' field found in {path.name}. Response keys: {list(data.keys())}")

    hourly = data["hourly"]

    df = pd.DataFrame({
        "timestamp": pd.to_datetime(hourly["time"]),
        "temperature_2m_c": hourly.get("temperature_2m"),
        "wind_speed_10m": hourly.get("wind_speed_10m"),
        "shortwave_radiation": hourly.get("shortwave_radiation"),
    })

    return df

def build_daily_dataset(date: str) -> pd.DataFrame:
    dam_path = download_henex_dam(date)
    load_path = download_ipto_load(date)
    res_path = download_ipto_res(date)
    weather_path = download_open_meteo(date)

    dam = parse_henex_dam(dam_path)
    load = parse_ipto_forecast(load_path, "load_forecast_mw", date)
    res = parse_ipto_forecast(res_path, "res_forecast_mw", date)
    weather = parse_open_meteo(weather_path)

    df = dam.merge(load, on="timestamp", how="left")
    df = df.merge(res, on="timestamp", how="left")

    df = pd.merge_asof(
        df.sort_values("timestamp"),
        weather.sort_values("timestamp"),
        on="timestamp",
        direction="nearest",
        tolerance=pd.Timedelta("30min")
    )

    df = df.sort_values("timestamp")

    output_path = PROCESSED_DIR / f"{date}_aligned_dataset.csv"
    df.to_csv(output_path, index=False)

    print(f"\nSaved processed dataset to: {output_path}")

    return df

# =========================
# HEnEx historical archive
# =========================

HENEX_ARCHIVE_URL = "https://www.enexgroup.gr/dam-idm-archive"


def get_henex_archive_zip_links() -> dict[str, str]:
    """
    Scrapes the HEnEx DAM/IDM archive page and returns all ZIP links.

    Returns:
        {
            "2025_EL-DAM-IDAs_Results.zip": "https://...",
            "2025_EL-DAM-IDAs_AggrCurves.zip": "https://...",
            ...
        }
    """

    print(f"[SCRAPE] {HENEX_ARCHIVE_URL}")

    r = requests.get(HENEX_ARCHIVE_URL, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Could not open archive page: {r.status_code}")

    soup = BeautifulSoup(r.text, "html.parser")

    zip_links = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)

        if ".zip" not in href and ".zip" not in text:
            continue

        if href.startswith("/"):
            href = "https://www.enexgroup.gr" + href

        filename = text if text.endswith(".zip") else href.split("/")[-1]

        zip_links[filename] = href

    if not zip_links:
        raise RuntimeError("No ZIP links found on HEnEx archive page.")

    return zip_links


def filter_henex_archive_links(
    links: dict[str, str],
    years: list[int],
    include_results: bool = True,
    include_curves: bool = True,
) -> dict[str, str]:
    selected = {}

    for filename, url in links.items():
        year_match = any(filename.startswith(str(year)) for year in years)

        if not year_match:
            continue

        is_results = "Results.zip" in filename and "PrelimResults" not in filename
        is_curves = "AggrCurves.zip" in filename

        if include_results and is_results:
            selected[filename] = url

        if include_curves and is_curves:
            selected[filename] = url

    return selected


def download_henex_historical_archive(
    years: list[int],
    include_results: bool = True,
    include_curves: bool = True,
    extract: bool = True,
    overwrite: bool = False,
) -> list[Path]:
    """
    Downloads historical HEnEx archive ZIPs into:
        data/raw/henex_archive/

    Extracts them into:
        data/raw/henex_archive/extracted/
    """

    all_links = get_henex_archive_zip_links()

    selected_links = filter_henex_archive_links(
        all_links,
        years=years,
        include_results=include_results,
        include_curves=include_curves,
    )

    if not selected_links:
        raise RuntimeError(
            f"No matching archive ZIPs found for years={years}. "
            f"Available files include: {list(all_links.keys())[:10]}"
        )

    downloaded_paths = []

    for filename, url in selected_links.items():
        zip_path = ARCHIVE_DIR / filename

        download_file(url, zip_path, overwrite=overwrite)
        downloaded_paths.append(zip_path)

        if extract:
            extract_dir = ARCHIVE_EXTRACTED_DIR / filename.replace(".zip", "")
            extract_dir.mkdir(parents=True, exist_ok=True)

            print(f"[EXTRACT] {filename} -> {extract_dir}")

            with zipfile.ZipFile(zip_path, "r") as z:
                z.extractall(extract_dir)

    return downloaded_paths


def list_extracted_archive_files() -> list[Path]:
    files = list(ARCHIVE_EXTRACTED_DIR.rglob("*"))

    files = [
        f for f in files
        if f.is_file() and f.suffix.lower() in [".xlsx", ".xls", ".csv"]
    ]

    print(f"[ARCHIVE FILES] Found {len(files)} extracted data files")

    return files
if __name__ == "__main__":
    date = "2026-04-29"

    # 1. Daily operational dataset
    df = build_daily_dataset(date)

    print("\nFinal daily dataset preview:")
    print(df.head())

    print("\nDaily dataset info:")
    print(df.info())

    # 2. Historical HEnEx archive download
    archive_paths = download_henex_historical_archive(
        years=[2023, 2024, 2025],
        include_results=True,
        include_curves=True,
        extract=True,
        overwrite=False,
    )

    print("\nDownloaded archive ZIPs:")
    for p in archive_paths:
        print(p)

    extracted_files = list_extracted_archive_files()

    print("\nFirst extracted files:")
    for f in extracted_files[:20]:
        print(f)