# FORECAST.md

The forecast layer. Deep dive on what, why, and in what order. STRATEGY.md gives the why; this file gives the how.

## What the forecast emits

For every future 15-min interval `t` in the day-ahead window:

- A **distribution** over `dam_price_eur_mwh`, expressed as P10 / P50 / P90 (Tier 0) or as **N residual-bootstrap scenarios** (Tier 1+).
- Optional: regime weights `(w_surplus, w_normal, w_scarcity)` summing to 1.

The optimizer never asks for a point price; it asks for either a P50 (deterministic LP with buffer) or a scenario tensor (stochastic LP with CVaR). Keep these as the two interfaces.

## Why distributional, not point

A point forecast collapses uncertainty into the mean and forces the optimizer to either ignore risk or paste a heuristic margin on top. A distribution lets the **spread filter** operate on `μ_ij / σ_ij` (a real signal-to-noise ratio) rather than `μ_ij - margin` (a wild guess). It also lets a CVaR penalty be applied directly. See [OPTIMIZER.md](OPTIMIZER.md).

## The frame — model the market, not the price

Greek DAM is a market-clearing system. Price is an output of supply-meets-demand under a uniform-price auction. The right primary feature is **residual load**:

```
RL_t = load_t - solar_t - wind_t   ≈   load_t - res_t
```

Residual load determines which generator is on the margin → which determines clearing price. Anything that doesn't start here is starting in the wrong place.

The price function is **nonlinear at regime boundaries**:

| Regime | Trigger | Price behaviour |
| --- | --- | --- |
| Surplus | High RES share, low RL | Near-zero or negative prices, RES curtailment risk |
| Normal | Mid-RL, gas on margin | Moderate, slow-moving |
| Scarcity | High RL, evening ramp, low RES | Spike-prone, fat-tailed |

A single linear or quantile model spans these regimes and bleeds error across them. Soft mixtures *can* fix this — but Tier 0 also captures the kinks via piecewise / tree-based features without a regime layer. The honest comparison is **kinked single-stage vs soft regime mixture**, judged on held-out pinball loss. If the mixture doesn't beat the kinked single-stage, ship Tier 0.

## Inputs contract — Option B (no leakage)

At inference (gate-closure noon CET D-1) the model sees only:
- IPTO load forecast at the latest version published before noon D-1.
- IPTO RES forecast, same vintage rule.
- WeatherNext 2 forecast issued at the cycle that closed before noon CET D-1 (typically the 06 UTC run); ERA5 reanalysis as a backfill source for training history pre-2024.
- Calendar features (hour, weekday, month, holiday / JJA / Easter).
- (Tier 3 only) gas / carbon settlements from D-2.

**Cleared generation mix from ENTSO-E enters only as the label for the regime classifier, never as a feature.** `res_share = res_fcst / load_fcst` is identity arithmetic from inputs the model already sees; a two-stage "predict mix → predict price" pipeline stacks errors for zero information gain.

For backtest training: the same vintage rule applies. Use the latest IPTO forecast file with publish time < D-1 noon, ERA5 reanalysis for weather pre-2024, WeatherNext 2 historical-forecast archive for 2024+. ERA5 is reanalysis (post-hoc analysis), not forecast vintage — it is mildly better than the contemporaneous forecast would have been. Disclose this small upward bias on pre-2024 backtest skill in the report.

## Tier 0 — single-stage quantile model with kink features

Ships day 1. One global model, three quantiles, no regime layer.

**Features**
- `residual_load_mw_forecast = load_fcst - res_fcst`
- `RL_low_kink = min(RL_fcst, RL_q20)` — piecewise term that fires only when residual load is low (curtailment-prone).
- `RL_high_kink = max(RL_fcst - RL_q80, 0)` — piecewise term that fires only when residual load is high (scarcity-prone).
- `rl_ramp_4h_mw = RL_t - RL_{t-4h}`
- `hour_of_day` (cyclical), `weekday`, `is_weekend`
- `month`, `is_jja_cooling`, `is_aug_vacation`, `is_easter_window`
- Capacity-weighted weather (from [weather_sources.py](../weather_sources.py) `build_capacity_weighted_weather_dataset`):
  - `solar_weighted_shortwave_radiation`, `solar_weighted_temperature_2m`
  - `wind_weighted_wind_speed_10m` (and `_100m` if WeatherNext 2 publishes it natively)
  - `load_weighted_temperature_2m` — population-weighted, drives cooling/heating load
- *(optional, Tier 3 if cheaply available:)* `gas_price_eur_mwh`, `eua_carbon_eur_t`

**Models**: `lightgbm.LGBMRegressor(objective='quantile', alpha=q)` for `q ∈ {0.1, 0.5, 0.9}` — three independent fits. Tree splits handle the residual-load kinks natively; the explicit `RL_low_kink` / `RL_high_kink` features are still cheap to include and help the linear-quantile fallback. Fallback if LGBM is unavailable: three `sklearn.linear_model.QuantileRegressor(quantile=q, alpha=...)` with the explicit kink features doing the non-linear lifting.

**Training data**: hourly DAM history (longer span, more samples). Apply intra-hour 15-min shape (see below) to translate hourly forecasts to 15-min.

**Output**: `p10_eur_mwh, p50_eur_mwh, p90_eur_mwh` per 15-min interval.

**Forecast-error MAD** (used by the spread filter at the optimizer):

```
MAD_{hour, weekday} = median_t( |dam_price_eur_mwh_t - p50_eur_mwh_t| )
```

Computed on a held-out walk-forward window, indexed by `(hour, weekday)`. The optimizer reads this table.

## Tier 1 — soft regimes + bootstrapped scenarios

The main quality jump.

**Soft regime classifier**
- Inputs: `RL_percentile` (computed against rolling 90-day window of forecast RL), `hour`, `RES_share`, optional `gas_price_eur_mwh`.
- Output: `(w_surplus, w_normal, w_scarcity)` ≥ 0, sum to 1.
- Model: multinomial logistic regression or a 1-hidden-layer softmax MLP. Three regimes — four splits the data too thin.
- Labels for training: derived from realized DAM behavior — e.g. surplus = price < 5th percentile of historical, scarcity = price > 95th percentile, normal = otherwise. **Train once on history, then use forecast RL at inference.**

**Per-regime quantile regression**
- Same feature set as Tier 0, but three independent quantile models per regime → 9 fits total.
- Final quantile = `Σ_r w_r · q_r(t)`. (Mixture of quantile predictions is not the same as the quantile of the mixture, but it's a defensible LP-friendly approximation and is what the field typically uses.)

**Scenarios via regime-conditioned residual bootstrap**

```
1. For each historical interval t, compute residual_t = price_realized_t - p50_predicted_t.
2. Bucket residuals by (regime_label_t, hour_of_day_t, month_t).
3. At inference, for each future interval t* with regime weights w_r:
     a. Sample regime r* ~ Categorical(w_surplus, w_normal, w_scarcity).
     b. Sample residual ~ empirical distribution of residuals in bucket (r*, hour(t*), month(t*)).
     c. price_scenario_t* = p50_predicted_t* + residual.
4. Repeat for N draws -> ndarray of shape (N, T). Default N = 200.
```

**Why bootstrap, not GARCH / parametric:** thin Greek data; fat tails; regime-dependent variance. A parametric volatility model wouldn't calibrate well on 7 months of 15-min data. Empirical bootstrap respects whatever distribution is actually there.

## Tier 2 — curve-aware (only if HEnEx historical curves load)

**Forecast tightness**:

```
market_tightness_t = dP / dQ (slope of supply curve at clearing quantity, in eur_per_mwh per mwh)
```

Predict `tightness_hat_t` from `(RL, RES_share, hour, month, gas_proxy)`, use as additional regressor in the per-regime quantile models.

**Verify before committing**: that aggregated curves are downloadable with ≥ 6 months of usable depth, including across the hourly→15-min transition. If not, do not start Tier 2 — it becomes a 2-day rabbit hole that produces a feature you can't backtest.

## Tier 3 — Greek-specific structural features

Add to the regime models:
- `duck_curve_pressure_t = solar_t - load_t`
- `evening_ramp_t = RL_t - RL_{t-4h}` (already in Tier 0 features as `rl_ramp_4h_mw`)
- `curtailment_proxy_t = max(0, RES_share_t - export_capacity_share_t)` (needs ENTSO-E NTC)

## Hourly → 15-min: the intra-hour shape

Train the main quantile model on the longer hourly history. At inference, you need 96 × 15-min predictions per day. Approach:

1. Predict hourly P10/P50/P90 from the global model.
2. From the post-2025-10-01 15-min sample, learn an **intra-hour shape multiplier** per `(hour-of-day, weekday-bucket)` cell:

   ```
   shape[h, w, q ∈ {0,1,2,3}] = mean_observed_15min_price[h, w, q] / mean_observed_hourly_price[h, w]
   ```
3. At inference, decompose: `p_q_15min[h, w, q] = p_hourly[h, w] · shape[h, w, q]`.

This is a multiplicative correction, not a separate model. Cheap, robust, and avoids training a 15-min regime model on 7 months alone.

## Look-ahead leakage — the failure mode

Restating the rule from [DATA.md](DATA.md): the forecast is trained on history but **served forecast inputs at inference**. Specifically:

- Train: regress `price_realized_t` on **historical forecast** load, RES, weather (the vintage that would have been available before D-1 noon CET for that historical date). WeatherNext 2 historical-forecast archive (2024+) and ERA5 reanalysis (pre-2024) cover weather; IPTO's `_02` (or latest pre-noon) version files cover load / RES.
- Inference: feed forecast load, forecast RES, forecast weather. Never realized.
- **Do not** train on realized RL and serve forecast RL. The two have different error characteristics; the model will be miscalibrated by exactly the forecast-error variance.
- **Cleared mix is label-only.** ENTSO-E generation breakdown enters as the regime label in Tier 1, never as a feature in any tier.

If the held-out backtest pinball loss is dramatically lower than the in-sample pinball loss on a random shuffle, you are leaking.

## Calibration and evaluation

Forecast-quality metrics (forecast-layer only):

- **Pinball loss** at q ∈ {0.1, 0.5, 0.9} on a held-out walk-forward window. Primary metric for Tier 0 / Tier 1 comparison and for the gate that promotes Tier 1 over Tier 0.
- **Coverage**: fraction of realized prices inside the [P10, P90] interval should sit ~80%. Lower → over-confident bands; higher → over-wide.
- **Bootstrap scenario calibration** (Tier 1+): empirical CDF of realized residuals against the scenario distribution per regime. Should overlap.

Strategy-quality metrics (forecast feeds optimizer feeds these — see [PLAN.md](PLAN.md)):

- **Sharpe ladder** across baselines: idle, naive daily rank, Tier 0, Tier 1, perfect foresight upper bound. Annualized using √365 (battery operates daily).
- **Sortino** alongside Sharpe — battery P&L is skewed; Sharpe punishes upside variance the same as downside, which we do not care about.
- **Information ratio vs naive baseline** — the cleanest measure of model alpha.
- **Capture rate vs perfect foresight** — `Tier_X_profit / perfect_foresight_profit`. Industry context for DAM batteries: 50–75% is typical.
- **Hit rate** (fraction of trades profitable after costs), **max drawdown**, **profit per MWh throughput**.
- **Split by regime**: summer vs winter, hourly era vs 15-min era. Hides nothing.

Pinball loss measures the forecast; the Sharpe ladder measures whether the forecast translates into risk-adjusted profit. Report both — they are not redundant.

## Non-goals for the forecast layer

- Predicting the *next interval* from the previous interval (autoregressive). Wrong frame; this is not a random walk.
- Forecasting every fundamental separately and combining them downstream. Just predict price quantiles directly conditioned on fundamentals.
- A neural net before quantile regression beats the baseline. Premature.
