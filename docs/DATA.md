# DATA.md

Data sources, schemas, alignment rules, and **the leakage discipline that the rest of the pipeline depends on**. Every other layer trusts that the data layer obeys these rules.

## Sources

| # | Source | Tier | Use | Endpoint pattern | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | HEnEx DAM Results | 0 | DAM clearing prices, MTU, traded volume | `https://www.enexgroup.gr/documents/20126/200106/{YYYYMMDD}_EL-DAM_Results_EN_v{NN}.xlsx` | downloadable, sample 200 OK |
| 2 | IPTO ISP Day-Ahead Load Forecast | 0 | Load forecast 96 × 15-min | `https://www.admie.gr/sites/default/files/attached-files/type-file/{YYYY}/{MM}/{YYYYMMDD}_ISP1DayAheadLoadForecast_{NN}.xlsx` | downloadable, sample 200 OK |
| 3 | IPTO ISP Day-Ahead RES Forecast | 0 | RES forecast 96 × 15-min | `https://www.admie.gr/sites/default/files/attached-files/type-file/{YYYY}/{MM}/{YYYYMMDD}_ISP1DayAheadRESForecast_{NN}.xlsx` | downloadable, sample 200 OK |
| 4 | WeatherNext 2 (Earth Engine / BigQuery) | 0 | Live + post-2024 forecast vintage; ensemble members give weather P10/P50/P90 | `projects/gcp-public-data-weathernext/...` (EE asset) | needs GCP project + auth; collection schema **not yet inspected** |
| 5 | ERA5 reanalysis (Copernicus CDS) | 0 | Pre-2024 weather backfill for training labels | `cdsapi` → `reanalysis-era5-single-levels` | needs `~/.cdsapirc` token; reanalysis ≠ forecast vintage (small upward bias on backtest skill — disclose) |
| 5b | Open-Meteo (forecast + historical-forecast) | fallback | Free fallback if WeatherNext 2 / ERA5 are unavailable | `https://api.open-meteo.com/v1/forecast?...` | free, no auth |
| 6 | ENTSO-E Transparency: Day-Ahead Prices | 0 | Price safety net + cross-check vs HEnEx | REST API | API token (provisioned) |
| 7 | ENTSO-E Transparency: Actual Generation per Production Type | 1 | Cleared fuel mix — **canonical source** for the hourly era pre-2025-10-01 (back to ~2015) and for consistency post-Oct-2025 | REST API | API token (provisioned) |
| 8 | ENTSO-E Transparency: NTC / cross-border flows | 3 | Curtailment proxy, import constraints | REST API | API token (provisioned) |
| 9 | HEnEx aggregated buy/sell curves | 2 | Curve tightness, market depth | HEnEx market results section | **needs verification** that historical archive is downloadable |
| 10 | TTF gas (ICE Endex) | 3 | Gas marginal cost driver | ICE / news settlements | likely licensed for clean history; do not depend on it |
| 11 | EEX EUA carbon | 3 | Carbon cost driver | EEX market data hub | similar concern; daily settlements usable |
| 12 | RAAEY GeoPortal (`geo.rae.gr`) | aux | Plant-level RES installed-capacity registry — used to set capacity weights in [weather_sources.py](../weather_sources.py) | website (JS-rendered) | Selenium-only; placeholders in `GREEK_ZONES` for now |

The version suffix `{NN}` (e.g. `_v01`, `_v02`) on HEnEx and IPTO files is a publisher revision counter. The latest version published on a given date is the one that was actually used by the market. For backtest fidelity, **prefer the latest version** that was available *before gate closure* (D-1 ≈ 12:00 EET) — see leakage section below.

## Time alignment — the canonical rule

- **Single timestamp grid.** All layers join on `timestamp` (`pd.Timestamp`, Europe/Athens, naive after `tz_localize(None)`).
- **15-min from 2025-10-01 onward**, hourly before. The aligned dataset carries `mtu_resolution ∈ {"hourly", "15min"}` so downstream models can subset.
- DST transitions: Greek time follows Europe/Athens. The 23-hour and 25-hour days happen on the last Sundays of March and October. Trust pandas' `date_range(... freq="15min", tz="Europe/Athens")`; do not roll your own.

## Schema — `data/processed/<date>_aligned_dataset.csv`

Built by `data_pipeline.build_daily_dataset(date)`. One row per delivery period of `date`.

> **Known bug, fix when the multi-day loader lands:** the snapshot at `2026-04-29_aligned_dataset.csv` has 1617 rows from a cross-product join (per-classification HEnEx rows × 96 MTUs). Target shape is one row per `(timestamp, MTU)` — the rebuilder must aggregate HEnEx classifications before joining.

| Column | Type | Source | Notes |
| --- | --- | --- | --- |
| `timestamp` | datetime64[ns] | derived | naive, Europe/Athens |
| `mtu_resolution` | str | derived | `"hourly"` or `"15min"` — set per-row at materialization |
| `dam_price_eur_mwh` | float | HEnEx `MCP` | the realized clearing price (label-side) |
| `delivery_duration` | int | HEnEx | minutes; 60 before 2025-10-01, 15 after |
| `total_traded_volume_mwh` | float | HEnEx | optional |
| `load_forecast_mw` | float | IPTO load | 96 × 15-min |
| `res_forecast_mw` | float | IPTO RES | 96 × 15-min |
| `solar_weighted_shortwave_radiation` | float | WeatherNext 2 / ERA5 → [weather_sources.py](../weather_sources.py) | capacity-weighted across the six Greek zones |
| `solar_weighted_temperature_2m` | float | weather aggregator | panel-efficiency proxy |
| `wind_weighted_wind_speed_10m` | float | weather aggregator | hub-height extrapolation downstream |
| `wind_weighted_wind_speed_100m` | float | weather aggregator | only present if WeatherNext 2 publishes natively |
| `load_weighted_temperature_2m` | float | weather aggregator | population-weighted; drives cooling/heating load |
| `cleared_thermal_share` | float | ENTSO-E generation-by-production-type (label-side, regime classifier only — never input feature) | Lignite + Natural Gas share of total generation |
| `cleared_res_share` | float | ENTSO-E (label-side only) | RES share of total generation |
| `cleared_imports_share` | float | ENTSO-E (label-side only) | imports share of total generation |

## History dataset — `data/processed/history.parquet` (planned, Tier 0)

Concatenated aligned datasets across a date range. One file, one schema, sorted by `timestamp`. Used for all model training and walk-forward backtest. Add `mtu_resolution` column on materialization.

## Leakage discipline — the rules nothing else negotiates around

The DAM gate closes at **D-1 ≈ 12:00 EET**. Every feature used to score a day-D schedule must have existed before that moment.

**Allowed at training time and at inference time:**
- `load_forecast_mw`, `res_forecast_mw` — these are forecasts published *before* gate closure. Use them as-is.
- Capacity-weighted weather aggregates from [weather_sources.py](../weather_sources.py). For inference, the WeatherNext 2 cycle that closed before noon CET D-1 (typically 06 UTC). For training pre-2024 use ERA5 reanalysis as backfill (note: ERA5 is reanalysis not forecast vintage — mildly better than the contemporaneous forecast would have been; disclose in report).
- Calendar features (hour, weekday, month, holiday / JJA / Easter dummies). Always safe.

**Allowed at training time only — never at inference time, never as a regressor in a forecast model:**
- `dam_price_eur_mwh` — this is the label. Backtest reads it for evaluation. The forecast never sees it for the day being predicted.
- **Cleared fuel mix from ENTSO-E** (`cleared_thermal_share`, `cleared_res_share`, `cleared_imports_share`). These are realized post-clearing. They are used as labels for the regime classifier (Tier 1) but never as features in any tier. `res_share = res_fcst / load_fcst` is identity arithmetic from inputs the price model already sees, so a two-stage "predict mix → predict price" pipeline stacks errors for zero gain. ("Option B" — see [FORECAST.md](FORECAST.md).)
- Any other realized RES, load, generation, outage, or imports series. Realized residual load `RL_realized` is a label proxy useful for fitting `RL → price` historical relationships, but at inference you must feed `RL_forecast` (built from forecast load and forecast RES).
- HEnEx aggregated buy/sell curves for date D are realized post-clearing. For Tier 2, the regressor is **forecast tightness** built from forecast inputs, not realized tightness.

**The trap (don't fall in):** training a forecast on realized RL and then serving it forecast RL at inference produces a backtest that looks great and a strategy that loses money. If the backtest is suspiciously good, this is the first place to look.

**Honest backtest discipline:** for date D in the backtest window,
1. Use only files / API responses dated < D-1 12:00 EET.
2. Use forecast vintages (load forecast, RES forecast, weather forecast) — never realized series — as features.
3. Compare schedule profit against realized DAM prices.

## Multi-day batch loader (Tier 0 todo)

`scripts/fetch_history.py --start YYYY-MM-DD --end YYYY-MM-DD`:

- Iterates dates, calls `build_daily_dataset(date)` (which already caches), concats, writes `data/processed/history.parquet`.
- Tags `mtu_resolution`.
- Skips dates where any of the four core sources 404 (log them; many are missing pre-launch dates and weekends/holidays for some endpoints).
- Idempotent on re-run thanks to download caching.

## Hourly → 15-min broadcast (Tier 0)

For dates < 2025-10-01:
- HEnEx DAM is hourly. Broadcast each hourly price to its four 15-min slots, flag `mtu_resolution = "hourly"`.
- IPTO load and RES forecasts may already be 15-min (96 values per day) even pre-Oct-2025; verify per file.
- Train the regime model on hourly history; learn an **intra-hour shape multiplier** from the post-2025-10-01 sample, then apply at inference to disaggregate the hourly P50 forecast into 15-min slots.

This avoids training a 15-min regime model on 7 months of data, which is too thin.

## File caching

`data_pipeline.download_file` caches by output path. Filenames in `data/raw/`:

```
{YYYY-MM-DD}_henex_dam.xlsx
{YYYY-MM-DD}_ipto_load_forecast.xlsx
{YYYY-MM-DD}_ipto_res_forecast.xlsx
{YYYY-MM-DD}_open_meteo.json          # fallback only
weather/era5_greece_{YYYY}_{MM}.nc    # ERA5 monthly NetCDF
weather/weathernext2_greece_zones_{YYYY-MM-DD}.csv
weather/greece_capacity_weighted_{YYYY-MM-DD}.csv
```

Pass `overwrite=True` to refetch (e.g. when a publisher posts a higher version number). Don't reinvent caching.

## Probe-driven historical backfill

Don't promise a start date in code; let 404s define the floor. Pragmatic floors based on market history:

- **HEnEx EL-DAM**: Greek DAM launched Nov 2020. The version suffix (`_v01` / `_v02`) and column layout almost certainly shift at the 2025-10-01 hourly→15-min transition. Walk back from today, log the first sustained 404 streak, lock that as the floor. Cache the floor so subsequent runs do not re-probe.
- **IPTO ISP files**: ISP naming aligns with the Target Model — earliest realistic floor is late 2020. Same probe approach.
- **ENTSO-E Transparency**: Greek bidding zone has clean coverage from ~2015. Use as the safety net for any series HEnEx / IPTO did not archive cleanly. Day-ahead price, load, and generation per production type all reach back further than the HEnEx file format does.

Downloader interface: `fetch_history --start auto --end today` where `auto` does a binary-search probe to find the earliest 200-OK date, caches it, and starts there.

## Things to verify before leaning on them

- Whether HEnEx historical buy/sell curves are downloadable with depth ≥ 6 months. Determines Tier 2 viability.
- Whether IPTO publishes load/RES forecast files with versions higher than `_02` and how to discover the latest version programmatically (current parser hard-codes `_02`).
- WeatherNext 2 Earth Engine collection schema: band names, ensemble-member dimension, and the property carrying forecast init time. Run `inspect_earth_engine_collection` in [weather_sources.py:256-273](../weather_sources.py#L256-L273) once GCP auth is set up.
