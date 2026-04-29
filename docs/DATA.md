# DATA.md

Data sources, schemas, alignment rules, and **the leakage discipline that the rest of the pipeline depends on**. Every other layer trusts that the data layer obeys these rules.

## Sources

| # | Source | Tier | Use | Endpoint pattern | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | HEnEx DAM Results | 0 | DAM clearing prices, MTU, traded volume | `https://www.enexgroup.gr/documents/20126/200106/{YYYYMMDD}_EL-DAM_Results_EN_v{NN}.xlsx` | downloadable, sample 200 OK |
| 2 | IPTO ISP Day-Ahead Load Forecast | 0 | Load forecast 96 × 15-min | `https://www.admie.gr/sites/default/files/attached-files/type-file/{YYYY}/{MM}/{YYYYMMDD}_ISP1DayAheadLoadForecast_{NN}.xlsx` | downloadable, sample 200 OK |
| 3 | IPTO ISP Day-Ahead RES Forecast | 0 | RES forecast 96 × 15-min | `https://www.admie.gr/sites/default/files/attached-files/type-file/{YYYY}/{MM}/{YYYYMMDD}_ISP1DayAheadRESForecast_{NN}.xlsx` | downloadable, sample 200 OK |
| 4 | Open-Meteo forecast API | 0 | Temperature, wind, shortwave radiation | `https://api.open-meteo.com/v1/forecast?...` | free, no auth |
| 5 | Open-Meteo historical-forecast API | 0 | Forecast-vintage weather for backtest training | `https://historical-forecast-api.open-meteo.com/v1/forecast?...` | free, no auth |
| 6 | HEnEx aggregated buy/sell curves | 2 | Curve tightness, market depth | HEnEx market results section | **needs verification** that historical archive is downloadable |
| 7 | ENTSO-E Transparency Platform | 1–3 | Cross-check, NTC, cross-border flows | `https://transparency.entsoe.eu/...` (REST API) | needs API token |
| 8 | TTF gas (ICE Endex) | 3 | Gas marginal cost driver | ICE / news settlements | likely licensed for clean history; do not depend on it |
| 9 | EEX EUA carbon | 3 | Carbon cost driver | EEX market data hub | similar concern; daily settlements usable |

The version suffix `{NN}` (e.g. `_v01`, `_v02`) on HEnEx and IPTO files is a publisher revision counter. The latest version published on a given date is the one that was actually used by the market. For backtest fidelity, **prefer the latest version** that was available *before gate closure* (D-1 ≈ 12:00 EET) — see leakage section below.

## Time alignment — the canonical rule

- **Single timestamp grid.** All layers join on `timestamp` (`pd.Timestamp`, Europe/Athens, naive after `tz_localize(None)`).
- **15-min from 2025-10-01 onward**, hourly before. The aligned dataset carries `mtu_resolution ∈ {"hourly", "15min"}` so downstream models can subset.
- DST transitions: Greek time follows Europe/Athens. The 23-hour and 25-hour days happen on the last Sundays of March and October. Trust pandas' `date_range(... freq="15min", tz="Europe/Athens")`; do not roll your own.

## Schema — `data/processed/<date>_aligned_dataset.csv`

Built by `data_pipeline.build_daily_dataset(date)`. One row per delivery period of `date`.

| Column | Type | Source | Notes |
| --- | --- | --- | --- |
| `timestamp` | datetime64[ns] | derived | naive, Europe/Athens |
| `dam_price_eur_mwh` | float | HEnEx `MCP` | the realized clearing price (label-side) |
| `delivery_duration` | int | HEnEx | minutes; 60 before 2025-10-01, 15 after |
| `total_traded_volume_mwh` | float | HEnEx | optional |
| `load_forecast_mw` | float | IPTO load | 96 × 15-min |
| `res_forecast_mw` | float | IPTO RES | 96 × 15-min |
| `temperature_2m_c` | float | Open-Meteo | nearest-30min merge |
| `wind_speed_10m` | float | Open-Meteo |  |
| `shortwave_radiation` | float | Open-Meteo |  |

## History dataset — `data/processed/history.parquet` (planned, Tier 0)

Concatenated aligned datasets across a date range. One file, one schema, sorted by `timestamp`. Used for all model training and walk-forward backtest. Add `mtu_resolution` column on materialization.

## Leakage discipline — the rules nothing else negotiates around

The DAM gate closes at **D-1 ≈ 12:00 EET**. Every feature used to score a day-D schedule must have existed before that moment.

**Allowed at training time and at inference time:**
- `load_forecast_mw`, `res_forecast_mw` — these are forecasts published *before* gate closure. Use them as-is.
- `temperature_2m_c`, `wind_speed_10m`, `shortwave_radiation` — for inference, use the **forecast** API. For backtest training, use the **historical-forecast** API endpoint (Open-Meteo provides the forecast that was actually emitted at that historical timestamp), not the realized weather. Realized weather is post-hoc.
- Calendar features (hour, weekday, month, holiday dummies). Always safe.

**Allowed at training time only — never at inference time, never as a regressor in a forecast model:**
- `dam_price_eur_mwh` — this is the label. Backtest reads it for evaluation. The forecast never sees it for the day being predicted.
- Any "realized" RES, load, generation, outage, or imports series. Realized residual load `RL_realized` is a *label proxy* — useful for fitting `RL → price` historical relationships, but at inference you must feed `RL_forecast` (built from forecast load and forecast RES).
- HEnEx aggregated curves for date D are realized post-clearing. For Tier 2, the regressor is **forecast tightness** built from forecast inputs, not realized tightness.

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
{YYYY-MM-DD}_open_meteo.json
```

Pass `overwrite=True` to refetch (e.g. when a publisher posts a higher version number). Don't reinvent caching.

## Things to verify before leaning on them

- Whether HEnEx historical buy/sell curves are downloadable with depth ≥ 6 months. Determines Tier 2 viability.
- Whether IPTO publishes load/RES forecast files with versions higher than `_02` and how to discover the latest version programmatically (current parser hard-codes `_02`).
- ENTSO-E rate limits if you provision an API token.
