from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


# ============================================================
# Config
# ============================================================

DATA_DIR = Path("data")
RAW_WEATHER_DIR = DATA_DIR / "raw" / "weather"
PROCESSED_WEATHER_DIR = DATA_DIR / "processed" / "weather"

RAW_WEATHER_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_WEATHER_DIR.mkdir(parents=True, exist_ok=True)


# load_weight: population-based proxy for electricity demand drivers
# (mainly cooling/heating load). Rough estimates from Hellenic Statistical
# Authority regional populations, normalized to sum to 1 across the
# represented zones.
#
# Caveat: the current 6-zone geometry is RES-oriented and does not include
# a dedicated point near Thessaloniki (~2nd largest demand center). The
# west_macedonia zone is used as the closest proxy for the wider
# Macedonia/Thessaloniki demand pool until a Thessaloniki zone is added or
# IPTO's actual zonal load distribution is plugged in.
GREEK_ZONES = [
    {
        "zone": "attica",
        "lat": 37.98,
        "lon": 23.72,
        "solar_weight": 0.20,
        "wind_weight": 0.10,
        "load_weight": 0.50,
    },
    {
        "zone": "central_greece",
        "lat": 38.90,
        "lon": 22.40,
        "solar_weight": 0.20,
        "wind_weight": 0.25,
        "load_weight": 0.08,
    },
    {
        "zone": "thessaly",
        "lat": 39.64,
        "lon": 22.42,
        "solar_weight": 0.25,
        "wind_weight": 0.10,
        "load_weight": 0.10,
    },
    {
        "zone": "west_macedonia",
        "lat": 40.30,
        "lon": 21.78,
        "solar_weight": 0.15,
        "wind_weight": 0.10,
        "load_weight": 0.20,
    },
    {
        "zone": "crete",
        "lat": 35.24,
        "lon": 24.81,
        "solar_weight": 0.10,
        "wind_weight": 0.20,
        "load_weight": 0.07,
    },
    {
        "zone": "aegean_islands",
        "lat": 37.45,
        "lon": 25.33,
        "solar_weight": 0.10,
        "wind_weight": 0.25,
        "load_weight": 0.05,
    },
]


WEATHER_VARS = [
    "temperature_2m",
    "wind_speed_10m",
    "shortwave_radiation",
    "cloud_cover",
    "precipitation",
]


# ============================================================
# Helpers
# ============================================================

def normalize_weights(rows: list[dict], weight_col: str) -> list[dict]:
    total = sum(float(r.get(weight_col, 0.0)) for r in rows)

    if total <= 0:
        equal = 1.0 / len(rows)
        return [{**r, weight_col: equal} for r in rows]

    return [{**r, weight_col: float(r[weight_col]) / total} for r in rows]


def capacity_weighted_aggregate(
    zone_weather: pd.DataFrame,
    weight_col: str,
) -> pd.DataFrame:
    """
    zone_weather columns expected:
    timestamp, zone, weight_col, temperature_2m, wind_speed_10m, shortwave_radiation
    """

    drop = {"timestamp", "zone", "lat", "lon", "solar_weight", "wind_weight", "load_weight"}

    value_cols = [
        c for c in zone_weather.columns
        if c not in drop
        and pd.api.types.is_numeric_dtype(zone_weather[c])
    ]

    df = zone_weather.copy()

    for c in value_cols:
        df[c] = df[c] * df[weight_col]

    out = (
        df.groupby("timestamp", as_index=False)[value_cols]
        .sum()
        .sort_values("timestamp")
    )

    return out


def collapse_ensemble_quantiles(
    df: pd.DataFrame,
    group_cols: list[str],
    value_cols: list[str],
    quantiles: Iterable[float] = (0.1, 0.5, 0.9),
) -> pd.DataFrame:
    """
    Input example:
    timestamp | zone | member | temperature_2m | wind_speed_10m

    Output:
    timestamp | zone | temperature_2m_q10 | temperature_2m_q50 | ...
    """

    frames = []

    grouped = df.groupby(group_cols)

    for q in quantiles:
        q_df = grouped[value_cols].quantile(q).reset_index()
        q_label = int(q * 100)
        q_df = q_df.rename(columns={c: f"{c}_q{q_label}" for c in value_cols})
        frames.append(q_df)

    out = frames[0]

    for frame in frames[1:]:
        out = out.merge(frame, on=group_cols, how="outer")

    return out


# ============================================================
# 1. WeatherNext 2 via Google Earth Engine
# ============================================================

def init_earth_engine(
    project_id: str,
    service_account: str | None = None,
    key_file: str | None = None,
):
    """
    Interactive local auth:
        init_earth_engine(project_id="your-gcp-project")

    Service account auth:
        init_earth_engine(
            project_id="your-gcp-project",
            service_account="service-account@project.iam.gserviceaccount.com",
            key_file="path/to/key.json"
        )
    """

    import ee

    if service_account and key_file:
        credentials = ee.ServiceAccountCredentials(service_account, key_file)
        ee.Initialize(credentials, project=project_id)
    else:
        ee.Authenticate()
        ee.Initialize(project=project_id)

    return ee


def fetch_weathernext2_earth_engine_points(
    project_id: str,
    start_time: str,
    end_time: str,
    zones: list[dict] = GREEK_ZONES,
    variables: list[str] = WEATHER_VARS,
    dataset_id: str = "projects/gcp-public-data-weathernext/assets/weathernext_2_0_0",
    output_csv: str | None = None,
) -> pd.DataFrame:
    """
    Pulls WeatherNext 2 values at Greek representative points from Earth Engine.

    IMPORTANT:
    Dataset band/property names may need adjustment after inspecting the collection.
    Use inspect_earth_engine_collection() below first.
    """

    ee = init_earth_engine(project_id)

    collection = (
        ee.ImageCollection(dataset_id)
        .filterDate(start_time, end_time)
    )

    rows = []

    for z in zones:
        point = ee.Geometry.Point([z["lon"], z["lat"]])

        for image_info in collection.toList(collection.size()).getInfo():
            image_id = image_info["id"]
            image = ee.Image(image_id)

            sampled = image.reduceRegion(
                reducer=ee.Reducer.first(),
                geometry=point,
                scale=25000,
                bestEffort=True,
            ).getInfo()

            timestamp = image_info.get("properties", {}).get("system:time_start")

            row = {
                "timestamp_ms": timestamp,
                "zone": z["zone"],
                "lat": z["lat"],
                "lon": z["lon"],
                "solar_weight": z["solar_weight"],
                "wind_weight": z["wind_weight"],
                "load_weight": z["load_weight"],
            }

            for var in variables:
                row[var] = sampled.get(var)

            rows.append(row)

    df = pd.DataFrame(rows)

    if "timestamp_ms" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", errors="coerce")
        df = df.drop(columns=["timestamp_ms"])

    df = df.sort_values(["timestamp", "zone"])

    if output_csv:
        path = PROCESSED_WEATHER_DIR / output_csv
        df.to_csv(path, index=False)
        print(f"[SAVED] {path}")

    return df


def inspect_earth_engine_collection(
    project_id: str,
    dataset_id: str = "projects/gcp-public-data-weathernext/assets/weathernext_2_0_0",
):
    """
    Run this first if band names are unknown.
    """

    ee = init_earth_engine(project_id)

    collection = ee.ImageCollection(dataset_id)
    first = ee.Image(collection.first())

    print("First image bands:")
    print(first.bandNames().getInfo())

    print("\nFirst image properties:")
    print(first.propertyNames().getInfo())


# ============================================================
# 2. WeatherNext 2 via BigQuery
# ============================================================

def fetch_weathernext2_bigquery_points(
    project_id: str,
    table_id: str,
    start_time: str,
    end_time: str,
    zones: list[dict] = GREEK_ZONES,
    output_csv: str | None = None,
) -> pd.DataFrame:
    """
    BigQuery version.

    You must provide the exact WeatherNext 2 BigQuery table_id after checking
    your Google Cloud / public dataset catalog.

    Example table_id placeholder:
        "bigquery-public-data.some_dataset.some_table"

    This function assumes the table has:
        timestamp, latitude, longitude, variable/value style columns
    You may need to adjust SQL once exact schema is known.
    """

    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)

    zones_df = pd.DataFrame(zones)

    temp_zones_path = PROCESSED_WEATHER_DIR / "greek_zones_for_bigquery.csv"
    zones_df.to_csv(temp_zones_path, index=False)

    query = f"""
    -- Adjust field names after inspecting table schema
    SELECT
      timestamp,
      latitude,
      longitude,
      temperature_2m,
      wind_speed_10m,
      shortwave_radiation
    FROM `{table_id}`
    WHERE timestamp >= TIMESTAMP("{start_time}")
      AND timestamp < TIMESTAMP("{end_time}")
      AND latitude BETWEEN 34.0 AND 42.0
      AND longitude BETWEEN 19.0 AND 30.0
    """

    df = client.query(query).to_dataframe()

    if output_csv:
        path = PROCESSED_WEATHER_DIR / output_csv
        df.to_csv(path, index=False)
        print(f"[SAVED] {path}")

    return df


def inspect_bigquery_table(project_id: str, table_id: str):
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    table = client.get_table(table_id)

    print(f"Table: {table_id}")
    print("Schema:")
    for field in table.schema:
        print(field.name, field.field_type)


# ============================================================
# 3. ERA5 via Copernicus CDS
# ============================================================

def download_era5_greece_single_levels(
    year: int,
    month: int,
    output_name: str | None = None,
    overwrite: bool = False,
):
    """
    Downloads ERA5 hourly single-level data for Greece.

    Requires:
        pip install cdsapi

    And CDS credentials configured at:
        ~/.cdsapirc

    Variables:
        2m_temperature
        10m_u_component_of_wind
        10m_v_component_of_wind
        surface_solar_radiation_downwards
    """

    import cdsapi

    if output_name is None:
        output_name = f"era5_greece_{year}_{month:02d}.nc"

    output_path = RAW_WEATHER_DIR / output_name

    if output_path.exists() and not overwrite:
        print(f"[CACHE] {output_path}")
        return output_path

    c = cdsapi.Client()

    days = [f"{d:02d}" for d in range(1, 32)]
    times = [f"{h:02d}:00" for h in range(24)]

    print(f"[ERA5 DOWNLOAD] {year}-{month:02d} -> {output_path}")

    c.retrieve(
        "reanalysis-era5-single-levels",
        {
            "product_type": "reanalysis",
            "format": "netcdf",
            "variable": [
                "2m_temperature",
                "10m_u_component_of_wind",
                "10m_v_component_of_wind",
                "surface_solar_radiation_downwards",
                "total_cloud_cover",
                "total_precipitation",
            ],
            "year": str(year),
            "month": f"{month:02d}",
            "day": days,
            "time": times,
            # North, West, South, East
            "area": [42.5, 19.0, 34.0, 30.0],
        },
        str(output_path),
    )

    return output_path


def _open_era5_dataset(nc_path: str | Path):
    """
    Opens ERA5 download as xarray.Dataset.

    Handles two CDS response shapes:
      - single .nc file (single variable or all-instantaneous request)
      - zip bundle (mixed instantaneous + accumulated variables); CDS now
        bundles these into archives like
            data_stream-oper_stepType-instant.nc
            data_stream-oper_stepType-accum.nc
        We open each member and xr.merge them on the shared time axis.
    """

    import zipfile
    import xarray as xr

    nc_path = Path(nc_path)

    if not zipfile.is_zipfile(nc_path):
        return xr.open_dataset(nc_path)

    extract_dir = nc_path.with_suffix(".unpacked")
    extract_dir.mkdir(exist_ok=True)

    with zipfile.ZipFile(nc_path, "r") as zf:
        zf.extractall(extract_dir)

    members = sorted(extract_dir.glob("*.nc"))
    if not members:
        raise RuntimeError(f"No .nc members in zip {nc_path}")

    datasets = [xr.open_dataset(m) for m in members]
    return xr.merge(datasets, compat="override")


def era5_points_to_dataframe(
    nc_path: str | Path,
    zones: list[dict] = GREEK_ZONES,
    output_csv: str | None = None,
) -> pd.DataFrame:
    """
    Extracts nearest-grid ERA5 data for each Greek representative zone.
    """

    import xarray as xr

    ds = _open_era5_dataset(nc_path)

    rows = []

    for z in zones:
        point = ds.sel(
            latitude=z["lat"],
            longitude=z["lon"],
            method="nearest",
        )

        df = point.to_dataframe().reset_index()

        # ERA5 names are often short variable names in NetCDF.
        # t2m = Kelvin, u10/v10 = m/s, ssrd = J/m².
        rename_map = {
            "valid_time": "timestamp",
            "time": "timestamp",
            "t2m": "temperature_2m_k",
            "u10": "u10",
            "v10": "v10",
            "ssrd": "surface_solar_radiation_downwards",
            "tcc": "total_cloud_cover",
            "tp": "total_precipitation_m",
        }

        df = df.rename(columns=rename_map)

        if "temperature_2m_k" in df.columns:
            df["temperature_2m_c"] = df["temperature_2m_k"] - 273.15

        if "u10" in df.columns and "v10" in df.columns:
            df["wind_speed_10m"] = np.sqrt(df["u10"] ** 2 + df["v10"] ** 2)

        df["zone"] = z["zone"]
        df["lat"] = z["lat"]
        df["lon"] = z["lon"]
        df["solar_weight"] = z["solar_weight"]
        df["wind_weight"] = z["wind_weight"]
        df["load_weight"] = z["load_weight"]

        keep = [
            "timestamp",
            "zone",
            "lat",
            "lon",
            "solar_weight",
            "wind_weight",
            "load_weight",
            "temperature_2m_c",
            "wind_speed_10m",
            "surface_solar_radiation_downwards",
            "total_cloud_cover",
            "total_precipitation_m",
        ]

        keep = [c for c in keep if c in df.columns]
        rows.append(df[keep])

    out = pd.concat(rows, ignore_index=True)
    out = out.sort_values(["timestamp", "zone"])

    if output_csv:
        path = PROCESSED_WEATHER_DIR / output_csv
        out.to_csv(path, index=False)
        print(f"[SAVED] {path}")

    return out


# ============================================================
# 4. Full weather build helper
# ============================================================

def build_capacity_weighted_weather_dataset(
    zone_weather: pd.DataFrame,
    output_name: str,
) -> pd.DataFrame:
    """
    Builds:
    - solar-weighted aggregate (RES generation, solar-side)
    - wind-weighted aggregate  (RES generation, wind-side)
    - load-weighted aggregate  (population proxy; mainly for temperature
      driving cooling/heating demand)

    Then merges all three into one dataset.

    Note: every numeric variable is weighted under all three schemes for
    symmetry. Only `load_weighted_temperature_2m` is physically meaningful
    on the load side; downstream feature engineering can drop the
    not-meaningful load-weighted columns or simply ignore them in the
    price model.
    """

    solar_zones = normalize_weights(
        zone_weather[
            ["zone", "solar_weight"]
        ].drop_duplicates().to_dict("records"),
        "solar_weight",
    )

    wind_zones = normalize_weights(
        zone_weather[
            ["zone", "wind_weight"]
        ].drop_duplicates().to_dict("records"),
        "wind_weight",
    )

    load_zones = normalize_weights(
        zone_weather[
            ["zone", "load_weight"]
        ].drop_duplicates().to_dict("records"),
        "load_weight",
    )

    solar_weights = pd.DataFrame(solar_zones)
    wind_weights = pd.DataFrame(wind_zones)
    load_weights = pd.DataFrame(load_zones)

    base = zone_weather.drop(
        columns=["solar_weight", "wind_weight", "load_weight"], errors="ignore"
    )

    solar_df = base.merge(solar_weights, on="zone", how="left")
    wind_df = base.merge(wind_weights, on="zone", how="left")
    load_df = base.merge(load_weights, on="zone", how="left")

    solar_agg = capacity_weighted_aggregate(solar_df, "solar_weight")
    wind_agg = capacity_weighted_aggregate(wind_df, "wind_weight")
    load_agg = capacity_weighted_aggregate(load_df, "load_weight")

    solar_agg = solar_agg.rename(
        columns={
            c: f"solar_weighted_{c}"
            for c in solar_agg.columns
            if c != "timestamp"
        }
    )

    wind_agg = wind_agg.rename(
        columns={
            c: f"wind_weighted_{c}"
            for c in wind_agg.columns
            if c != "timestamp"
        }
    )

    load_agg = load_agg.rename(
        columns={
            c: f"load_weighted_{c}"
            for c in load_agg.columns
            if c != "timestamp"
        }
    )

    out = solar_agg.merge(wind_agg, on="timestamp", how="outer")
    out = out.merge(load_agg, on="timestamp", how="outer")
    out = out.sort_values("timestamp")

    path = PROCESSED_WEATHER_DIR / output_name
    out.to_csv(path, index=False)
    print(f"[SAVED] {path}")

    return out


# ============================================================
# Example usage
# ============================================================

if __name__ == "__main__":
    # A) ERA5 historical backfill example
    # Requires ~/.cdsapirc
    # nc = download_era5_greece_single_levels(year=2024, month=1)
    # era5_zone_df = era5_points_to_dataframe(nc, output_csv="era5_greece_zones_2024_01.csv")
    # build_capacity_weighted_weather_dataset(
    #     era5_zone_df,
    #     output_name="era5_greece_capacity_weighted_2024_01.csv",
    # )

    # B) WeatherNext 2 Earth Engine example
    # Requires Earth Engine auth and GCP project
    # inspect_earth_engine_collection(project_id="your-gcp-project")
    # wn2_zone_df = fetch_weathernext2_earth_engine_points(
    #     project_id="your-gcp-project",
    #     start_time="2026-04-29T00:00:00",
    #     end_time="2026-04-30T00:00:00",
    #     output_csv="weathernext2_greece_zones_2026_04_29.csv",
    # )
    # build_capacity_weighted_weather_dataset(
    #     wn2_zone_df,
    #     output_name="weathernext2_greece_capacity_weighted_2026_04_29.csv",
    # )

    print("Weather source module ready.")