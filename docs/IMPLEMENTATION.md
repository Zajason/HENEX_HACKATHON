# IMPLEMENTATION.md

Concrete step-by-step schedule from "data foundation" to a trained, validated Tier-0 forecast. Pick up at the first unchecked box.

For strategic context see [PLAN.md](PLAN.md). For the forecast contract see [FORECAST.md](FORECAST.md). For data leakage rules see [DATA.md](DATA.md).

---

## Cursor

Last updated 2026-04-29.

- HEnEx DAM history built: `data/processed/henex_dam_history.parquet` (51,907 intervals, 2020-11-01 → 2025-12-31).
- ERA5 weather pipeline validated end-to-end on Jan 2024.
- IPTO bulk download was kicked off at 2026-04-29 ~15:00 EET (background task `bv420u423`); ~3,990 tasks total.
- Earth Engine / WeatherNext 2: still waiting on auth (non-blocking; Tier-0 ships on ERA5 + Open-Meteo).

---

## Phase A — Data foundation

Phase target: a single unified `data/processed/history.parquet` covering the full HEnEx span with price + IPTO features. ERA5 weather streamed in afterwards.

### A1. IPTO bulk download (in progress)

- **Status:** running in background.
- **Output:** `data/raw/ipto_history/{YYYY-MM-DD}_ipto_{load,res}_forecast.xlsx` per date.
- **Verify:**
  - `ls data/raw/ipto_history/ | wc -l` should approach ~3,990.
  - Final log written to `data/processed/ipto_history_log.json` with `status_counts` and `miss_dates`.
- **Known holes:** 2025-10-01 (no IPTO files published the day of the hourly→15-min transition; verified via probe). Other misses go in the log.
- **Time:** ~15-20 min remaining.

### A2. Parse IPTO history → parquet

- **What:** read every per-day Excel in `data/raw/ipto_history/`, extract the 96 × 15-min values, concatenate into long-format DataFrames indexed by timestamp.
- **Two outputs:** `data/processed/ipto_load_history.parquet`, `data/processed/ipto_res_history.parquet`.
- **Schema (each):** `timestamp` (Europe/Athens naive), `value_mw` (load or RES), `source_date` (delivery date), `source_version` (the `_vNN` suffix actually used).
- **Implementation:** wrap `data_pipeline.parse_ipto_forecast` in a glob loop. Skip files smaller than 1 KB (corrupt downloads).
- **Verify:** ~190,000 rows per file (1990 days × 96), `value_mw` non-negative, no duplicate timestamps.
- **Time:** ~5 min.

### A3. Build unified `history.parquet` (price + IPTO)

- **What:** left-join HEnEx history + IPTO load + IPTO RES on `timestamp`. Handle the 2025-10-01 transition: pre-Oct hourly DAM prices broadcast to the four 15-min slots; post-Oct prices already 15-min.
- **Output:** `data/processed/history.parquet`.
- **Schema:** `timestamp`, `mtu_resolution`, `dam_price_eur_mwh`, `delivery_duration`, `total_volume_mwh`, `load_forecast_mw`, `res_forecast_mw`. Weather columns appended in A5.
- **Verify:**
  - One row per `(timestamp)`. No duplicates.
  - 5+ years of coverage; `mtu_resolution` distribution matches the ratio in `henex_dam_history`.
  - `load_forecast_mw` and `res_forecast_mw` non-null for ≥95% of rows (some misses expected from A1 gaps).
- **Time:** ~2 min.

### A4. Kick off ERA5 backfill (background)

- **What:** loop `weather_sources.download_era5_greece_single_levels(year=Y, month=M)` over `(Y, M)` covering 2020-11 → 2026-04 (66 months). `cdsapi` queues each request server-side; light client-side parallelism (~3 in flight).
- **Outputs:** `data/raw/weather/era5_greece_{YYYY}_{MM}.nc` per month.
- **Caching:** the function early-returns on `output_path.exists()`, so re-running is idempotent.
- **Verify:** 66 NetCDF files cached.
- **Time:** ~45-60 min wall-clock; runs in background while Phase B progresses.

### A5. Merge ERA5 weather into `history.parquet`

- **Runs after A4 completes.**
- **What:** for each ERA5 monthly NetCDF, run `era5_points_to_dataframe` then `build_capacity_weighted_weather_dataset`. Concatenate across months. Convert UTC → Europe/Athens (naive). Broadcast hourly weather to 15-min by forward-fill within the hour. Left-join the `solar_weighted_*`, `wind_weighted_*`, `load_weighted_*` columns into `history.parquet`.
- **Critical conversions:**
  - `surface_solar_radiation_downwards` is **accumulated J/m²** since the day-start in ERA5 — convert to instantaneous W/m² as `Δ(ssrd) / 3600`. Filed already.
  - Timestamps need `tz_localize('UTC').tz_convert('Europe/Athens').tz_localize(None)` before the join.
- **Verify:** weather columns non-null where both source and HEnEx exist; no large gaps; sensible diurnal shape on a sample day.
- **Time:** ~5 min.

---

## Phase B — Forecast implementation

Runs in parallel with A4/A5. B1-B4 depend only on price + IPTO data; B5/B6 add weather features once A5 lands.

### B1. Feature engineering module

- **File:** `forecast/features.py` (new).
- **Inputs:** `data/processed/history.parquet`.
- **Functions:**
  - `add_residual_load(df)` → adds `RL_mw = load_forecast_mw − res_forecast_mw`.
  - `add_kink_features(df, q_low=0.20, q_high=0.80)` → adds `RL_low_kink = min(RL, RL_q20)` and `RL_high_kink = max(RL − RL_q80, 0)`. The quantile thresholds are computed on the **training fold** at each walk-forward step, never on the test fold.
  - `add_calendar_features(df)` → adds `hour, dow, month, is_weekend, is_jja, is_aug_vacation, is_easter_window, is_greek_holiday`.
  - `add_ramps(df)` → adds `rl_ramp_4h_mw`.
- **Verify:** unit tests on a 1-week subset; no NaNs introduced beyond what the join introduces.
- **Time:** ~15 min.

### B2. Tier-0 model module

- **File:** `forecast/tier0.py` (new).
- **Class:** `Tier0QuantileForecaster` with:
  - `fit(df_train, target='dam_price_eur_mwh', quantiles=(0.1, 0.5, 0.9))` — three independent `lightgbm.LGBMRegressor(objective='quantile', alpha=q)`.
  - `predict(df_test)` → DataFrame with `[timestamp, p10_eur_mwh, p50_eur_mwh, p90_eur_mwh]`.
  - `feature_columns` property — locked at fit time, used by `predict` to enforce identical feature set.
- **Hyperparameters:** start with defaults; tune `num_leaves`, `min_data_in_leaf`, `learning_rate` only if pinball loss plateaus.
- **Verify:** fit on Jan-Nov 2024, predict Dec 2024, eyeball P50 vs realized.
- **Time:** ~20 min.

### B3. Walk-forward backtest harness

- **File:** `forecast/backtest.py` (new).
- **Function:** `walk_forward(df, train_window_months=12, test_window_months=1, step_months=1)`.
- **Behavior:** rolling origin. For each fold: train on `[t-12, t)`, predict `[t, t+1)`, advance by 1 month. Concatenates per-fold predictions into a single DataFrame.
- **Output columns:** `timestamp, p10, p50, p90, realized, fold_id`.
- **Verify:** no overlap between train and test sets; folds are temporally ordered; first usable fold starts when ≥12 months of training data exist.
- **Time:** ~20 min.

### B4. First fit on price + IPTO only (no weather)

- **What:** run B3 on `history.parquet` before A5 lands. Produces a baseline pinball-loss number that A5/B6 must beat.
- **Output:** `data/processed/forecast_walkforward_v0_no_weather.parquet`.
- **Sanity check:** pinball loss reasonable; P10/P90 coverage near 80%; no obvious leakage signs.
- **Time:** ~10 min runtime.

### B5. Merge weather features (depends on A5)

- **What:** A5 added weather columns to `history.parquet`. B5 just re-runs B4 with the expanded feature set.
- **Time:** ~5 min.

### B6. Re-fit Tier-0 with weather features

- **Output:** `data/processed/forecast_walkforward_v1_with_weather.parquet`.
- **Compare:** B6 pinball loss vs B4 pinball loss. Quantify the weather-feature lift.
- **Time:** ~10 min runtime.

---

## Phase C — Validation

### C1. Calibration report

- **File:** `forecast/report.py` (new).
- **Functions:**
  - `pinball_loss(predictions_df, by=['year', 'month', 'mtu_resolution', 'hour'])` — sliced to expose where the model fails.
  - `coverage(predictions_df)` — fraction of `realized` inside `[p10, p90]`. Target ≈ 0.80.
- **Verify:** coverage 0.75-0.85; pinball loss declines monotonically from B4 → B6 (otherwise weather features don't help and we revisit the join).
- **Output:** `data/processed/forecast_calibration_report.csv`.
- **Time:** ~10 min.

### C2. Forecast-error MAD table

- **What:** compute `MAD_{hour, weekday} = median(|realized − p50|)` from the walk-forward predictions. This table feeds the spread filter in the optimizer (`spread_ij > λ_buffer · MAD_ij`).
- **Output:** `data/processed/forecast_error_mad.parquet`.
- **Schema:** `hour, weekday, mad_eur_mwh, n`.
- **Time:** ~5 min.

### C3. Visual sanity plots

- **What:** matplotlib panels — for three sample dates (a winter peak day, a summer cooling-load day, and a 2025 negative-price day), plot realized DAM vs P10/P50/P90.
- **Output:** `docs/figures/forecast_sample_<date>.png`.
- **Time:** ~10 min.

---

## End state — what "forecast implemented" means

When the boxes above are all ticked:

- `data/processed/history.parquet` exists, covers 2020-11 → present, has price + IPTO + ERA5 weather columns, one row per `(timestamp)`.
- `forecast/{features,tier0,backtest,report}.py` exist.
- `Tier0QuantileForecaster.fit(...)` / `predict(...)` works on any held-out window.
- `data/processed/forecast_walkforward_v1_with_weather.parquet` is the canonical artefact the optimizer reads.
- `data/processed/forecast_error_mad.parquet` is the canonical buffer table the spread filter reads.
- The Tier-1 regime mixture is now the candidate upgrade — see [PLAN.md](PLAN.md) for the gate (must beat Tier-0 on held-out pinball loss).

---

## Recovery checklist (read this if you came back days later)

If you don't know where you stopped:

1. `ls data/raw/ipto_history/ | wc -l` — A1 done if ≥ 3,800.
2. `ls data/processed/ipto_*_history.parquet 2>/dev/null` — A2 done if both files exist.
3. `python -c "import pandas as pd; print(pd.read_parquet('data/processed/history.parquet').columns)"` — A3 done if it runs and shows price + IPTO columns; A5 done if it shows weather columns too.
4. `ls data/raw/weather/era5_greece_*.nc | wc -l` — A4 done if ≥ 60.
5. `ls forecast/` — B1-B3 done if `features.py / tier0.py / backtest.py` exist.
6. `ls data/processed/forecast_walkforward_*.parquet` — B4 / B6 done.
7. `ls data/processed/forecast_calibration_report.csv data/processed/forecast_error_mad.parquet` — C1 / C2 done.

---

## Anti-traps to remember

- **Look-ahead leakage** is the failure mode. Train features must be the forecast vintage that would have been available before noon CET D-1. Realized values are labels only. See [DATA.md](DATA.md) leakage section.
- **Hourly → 15-min broadcast** is multiplicative correction territory, not a separate model. Train on hourly history; learn intra-hour shape from the post-2025-10-01 sample.
- **No `.fit()` on the full dataset before splitting.** Walk-forward only. Quantile thresholds for the kink features are recomputed per fold.
- **2025-10-01 is a hole** in IPTO. Drop those intervals from training; do not impute.
- **Cleared mix is a label, not a feature.** ENTSO-E generation breakdown enters Tier 1 as the regime label only — never as a regressor in any tier.
