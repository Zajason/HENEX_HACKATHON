# PLAN.md

Tiered execution roadmap. **Ship at every tier.** A working Tier 0 submission beats a half-built Tier 2. Tier numbers map to "what is the minimum set of features to demo a credible solution" — they are not difficulty levels.

Cursor: **end of Tier 0 data layer. Forecast layer not yet started.**

---

## Tier 0 — baseline that must work end-to-end (ship Day 1)

The "boring submission" that already beats the idle baseline. Everything downstream is an upgrade on this.

**Data layer**

- [x] HEnEx DAM downloader + parser (`MCP`, `DELIVERY_MTU`, `DELIVERY_DURATION`, traded volume).
- [x] IPTO load forecast downloader + parser (96 × 15-min values per day).
- [x] IPTO RES forecast downloader + parser.
- [x] Open-Meteo weather downloader + parser.
- [x] Per-day aligned dataset (`build_daily_dataset`).
- [ ] **Multi-day historical batch loader** — pull a date range, concat aligned dataframes, write `data/processed/history.parquet`. Needed for any model training. See [DATA.md](DATA.md).
- [ ] **Hourly-history loader** — for dates before 2025-10-01, parse hourly DAM and broadcast to a 15-min grid (4×) flagged `mtu_resolution = "hourly"`. Don't train regime model directly on the post-Oct-2025 sample alone.
- [ ] **Holiday + Greek-specific calendar dummies** — Easter window, Aug vacation, JJA cooling.

**Forecast layer (Tier 0 model)**

- [ ] Feature engineering: residual load `RL = load - res`, hour-of-day, weekday, month, RL ramps, calendar dummies. (Keep gas/carbon out of Tier 0 — too costly to source historically.)
- [ ] **Direct quantile regression** at P10 / P50 / P90, one model per quantile (sklearn `QuantileRegressor` or statsmodels). One global model trained on hourly history; intra-hour 15-min shape learned from the post-2025-10-01 sample as a multiplicative correction.
- [ ] Forecast-error MAD per (hour, weekday) cell, used by the spread filter.

**Optimizer layer (Tier 0)**

- [ ] **Deterministic LP** on P50 forecast with the spread filter `spread_ij > λ_buffer · MAD_ij`. Net-power formulation. Theta = `theta_cycle` only at this tier.
- [ ] CLI: `python -m optimizer.run --date YYYY-MM-DD` → schedule CSV + summary.

**Backtest + evaluation**

- [ ] Walk-forward backtest over a clean window (e.g. 2025-11-01 → 2026-04-28) using forecast vintages, not realized values.
- [ ] Three baselines: idle, naive daily rank, perfect foresight (upper bound only).
- [ ] Report: expected vs realized profit, profit per MWh throughput, cycles, idle intervals, daily SoC plot.

**Exit criterion for Tier 0:** the optimizer beats `idle` and `naive daily rank` on realized backtest profit on a held-out month.

---

## Tier 1 — regime-aware (the main quality jump)

Tier 0 with one upgrade: the price function is non-linear at regime boundaries. A single quantile model bleeds error across regimes; a soft mixture handles this without overfitting.

- [ ] **Soft regime classifier** on `(RL_percentile, hour, RES_share)` → weights `(w_surplus, w_normal, w_scarcity)`. Logistic regression or a small softmax MLP. Three regimes only — four splits the data too thin.
- [ ] **Per-regime quantile regression** at P10 / P50 / P90.
- [ ] **Final price quantile = weighted mixture** across regimes.
- [ ] **Scenarios via regime-conditioned residual bootstrap.** For interval *t*, sample N residuals from the historical empirical distribution conditioned on (regime, hour-of-day, month). Default `N = 200`. Avoids fitting a parametric volatility model on thin Greek data.
- [ ] Spread distribution: `μ_ij = mean_s(spread_ij^s)`, `σ_ij = std_s(spread_ij^s)`, `z_ij = μ_ij / σ_ij`. Trade only `z_ij > z_threshold`.

**Exit criterion for Tier 1:** profit per MWh throughput improves on a held-out month vs Tier 0, *and* the worst-case scenario profit (5th percentile) improves or holds flat — i.e. risk-adjusted profit is up, not just average.

---

## Tier 2 — curve-aware (only if HEnEx historical curves are accessible)

This is the real upgrade in theory and the easiest 2-day rabbit hole in practice. **Verify data access before committing.**

- [ ] Confirm HEnEx publishes downloadable historical aggregated buy/sell curves with the depth needed for backtest. If not, skip Tier 2 and present without it.
- [ ] Reconstruct supply / demand step functions per delivery period; locate clearing intersection.
- [ ] Compute `market_tightness_t = dP/dQ near clearing` (slope of supply curve at clearing quantity).
- [ ] Forecast tightness from `(RL, RES_share, hour, month, gas_proxy)`; use as additional regressor in the regime quantile models.
- [ ] Derived features: `low_price_curve_depth`, `high_price_curve_steepness`.

**Exit criterion for Tier 2:** Tier 2 regime+tightness model beats Tier 1 regime model on held-out forecast log-likelihood (pinball loss across quantiles), not just on backtest profit. If only backtest profit improves but pinball loss doesn't, suspect overfitting.

---

## Tier 3 — Greek-specific structural features + stochastic optimizer

Treat as polish on top of a working Tier 1 / Tier 2.

- [ ] `duck_curve_pressure_t = solar_t - load_t`.
- [ ] `evening_ramp_t = RL_t - RL_{t-4h}`.
- [ ] `curtailment_proxy_t = max(0, RES_share_t - export_capacity_share_t)` (requires ENTSO-E NTC).
- [ ] **Full theta decomposition** in the LP: cycle + calendar (kinked above `SoC_threshold`) + self-discharge in SoC dynamics + aux load + capital cost + fixed. See [OPTIMIZER.md](OPTIMIZER.md).
- [ ] **Stochastic LP with CVaR penalty.** Replace deterministic LP with `max E[profit] − λ_CVaR · CVaR_5%(profit)` over the N regime-bootstrapped scenarios.
- [ ] Optional: TTF gas + EUA carbon as exogenous regressors, only if accessible cheaply.

**Exit criterion for Tier 3:** the stochastic optimizer reduces realized worst-day loss without giving up more than 10% of expected profit vs the deterministic-with-buffer Tier 1 setup.

---

## Anti-goals — things explicitly **not** on this roadmap

- Pure autoregressive forecasting — ARIMA, vanilla Prophet "predict next price from previous price," LSTM on lagged price alone. Wrong frame: this is a market-clearing system, not a random walk. *(Note: Prophet **with exogenous regressors** — load_fcst, res_fcst, weather, holidays — is a different beast and is in fact used as the seasonal/trend/holiday backbone in the Tier 0 forecast layer; see [FORECAST.md](FORECAST.md). The anti-goal applies to Prophet-as-univariate-AR, not Prophet-as-decomposition.)*
- Mocked battery telemetry to fit deeper degradation models. Use datasheet priors; document in [OPTIMIZER.md](OPTIMIZER.md). The brief explicitly says solutions must work **without** rich telemetry history.
- Self-hosted neural-network weather models (FourCastNet, GraphCast checkpoints, Pangu-Weather, etc.). Setup cost (CUDA box + PyTorch + multi-GB weights + ERA5 IC pipeline) exceeds the EE auth wait for WeatherNext 2 with no hackathon-deliverable upside. Stack is `ERA5 + Open-Meteo` today, `ERA5 + WeatherNext 2` once EE lands.
- Real-time / intraday market integration. Out of scope; DAM only.
- Bid-curve participation strategy (price-taker only).
- Multi-asset portfolio optimization. One battery.

---

## Demo / submission shape

Final deliverable should be runnable end-to-end with one command and produce:

1. The optimal schedule for the next delivery day (charge / discharge / idle per 15-min interval).
2. Expected profit, worst-case scenario profit, SoC path, cycle count.
3. A backtest report: realized profit vs idle / naive-rank / perfect-foresight baselines over a held-out window.
4. A short narrative of *why* the schedule does what it does (which regimes, where the spreads come from). This is what makes the pitch land.
