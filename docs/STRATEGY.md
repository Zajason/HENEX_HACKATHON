# Battery Optimization Strategy

## Goal

Build a robust day-ahead battery scheduling framework for the Greek electricity market. The battery should charge, discharge, or stay idle based on expected economic value while respecting physical operating constraints and acknowledging that Greece has limited standalone battery operating history.

The core framing is:

> A battery monetizes temporal price spreads. It buys energy in low-value intervals, stores it, and sells it in higher-value intervals only when the spread is large enough to cover efficiency losses, degradation, fees, and forecast uncertainty.

Internally this can be thought of as a gamma/theta trade: the battery is long price dispersion across time, while losses, degradation, and idle opportunity cost are the carry. For the hackathon presentation, use the more transparent phrase: **robust day-ahead battery spread optimization**.

## Downloadable Data Check

The PDF names the right data sources. Practical download status:

| Source | Use | Download status | Notes |
| --- | --- | --- | --- |
| HEnEx Day-Ahead Market | DAM prices, traded volumes, MTU duration | Downloadable `.xlsx` | Official page exposes daily files and a URL template. Sample DAM results file returned HTTP 200. |
| IPTO / ADMIE ISP Forecast | Load forecasts and RES forecasts | Downloadable `.xlsx` | Official listing exposes daily load and RES forecast files. Sample load and RES files returned HTTP 200. |
| Open-Meteo | Weather forecasts and historical weather | API / CSV / JSON | Forecast API sample returned HTTP 200. Historical forecast API is useful for model training with forecast-like weather inputs. |
| ENTSO-E Transparency Platform | Cross-check DAM prices, load, generation, flows | API available with token | Useful fallback/cross-check, but requires registration and API token. |
| ICE TTF gas | Gas price driver | Optional / likely licensed for robust history | Use only if accessible quickly. Do not make the core solution depend on it. |
| EEX EUA carbon | Carbon price driver | Optional / market data access can be limited | Useful daily explanatory feature, but not required for a strong first version. |

Representative checked endpoints:

- HEnEx DAM results template: `https://www.enexgroup.gr/documents/20126/200106/YYYYMMDD_EL-DAM_Results_EN_v##.xlsx`
- Example checked HEnEx file: `https://www.enexgroup.gr/documents/20126/200106/20260429_EL-DAM_Results_EN_v01.xlsx`
- Example checked IPTO load forecast: `https://www.admie.gr/sites/default/files/attached-files/type-file/2026/04/20260429_ISP1DayAheadLoadForecast_02.xlsx`
- Example checked IPTO RES forecast: `https://www.admie.gr/sites/default/files/attached-files/type-file/2026/04/20260429_ISP1DayAheadRESForecast_02.xlsx`
- Example checked Open-Meteo forecast query: `https://api.open-meteo.com/v1/forecast?latitude=37.98&longitude=23.72&hourly=temperature_2m,wind_speed_10m,shortwave_radiation&forecast_days=1&timezone=Europe%2FAthens`

## Data Pipeline

1. Download HEnEx DAM results.
2. Parse `DELIVERY_MTU`, `DELIVERY_DURATION`, `MCP`, and total traded volume.
3. Download IPTO load and RES forecasts for the relevant delivery day.
4. Pull Open-Meteo weather forecasts for representative Greek zones or national weighted coordinates.
5. Align all features to the market time unit:
   - Hourly before the market transition.
   - 15-minute from 2025-10-01 onward.
6. Keep all inputs ex-ante:
   - Use forecasts available before the scheduling decision.
   - Use realized values only for backtesting labels and evaluation.

## Forecast Layer

Use a simple, explainable model first:

```text
price_hat_t =
    seasonal_profile(hour, weekday, month)
  + beta_load * load_forecast_t
  + beta_res * res_forecast_t
  + beta_weather * weather_t
  + beta_gas * gas_price_t
  + beta_carbon * carbon_price_t
```

Preferred first choices:

- Ridge regression or robust linear regression.
- Rolling retraining window.
- Calendar features for hour, weekday, month, holiday/weekend.
- Residual tracking by hour and season.

Data scarcity handling:

- If gas or carbon data is not available, omit it initially.
- If there is not enough forecast history, use analog days based on load, RES, weather, weekday, and month.
- Use historical forecast residuals to estimate uncertainty, not a complex volatility model.

## Statistical Arbitrage Research Layer

The first model should not try to predict the exact DAM price perfectly. The more useful objective is to predict whether a future charge-discharge spread is statistically large enough to monetize after losses and costs.

This changes the research question from:

```text
What is the exact price in each interval?
```

to:

```text
Which low-price and high-price intervals are likely to create a robust positive spread?
```

The base forecast remains the transparent linear model:

```text
price_hat_t =
    seasonal_profile_t
  + beta_load * load_forecast_t
  + beta_res * res_forecast_t
  + beta_weather * weather_t
  + optional_macro_terms_t
```

Then statistical arbitrage logic is applied on top of this model:

1. Estimate the fair value of each interval.
2. Compare forecast spreads across intervals inside the same delivery day.
3. Normalize spreads by historical forecast error.
4. Trade only the spreads that are statistically significant.
5. Use realized backtest results to improve the signal, not to overfit the optimizer.

The key signal can be expressed as a spread z-score:

```text
z_i_j = (
    price_hat_j * eta_dis
  - price_hat_i / eta_ch
  - degradation_cost
  - fees
) / spread_error_MAD_i_j
```

Where:

- `i` is a candidate charge interval.
- `j` is a candidate discharge interval.
- `j` should be later than `i` unless the battery starts the day with enough energy.
- `spread_error_MAD_i_j` is estimated from historical residuals for similar interval pairs.

Trade rule:

```text
allow spread i -> j only if z_i_j > z_threshold
```

This is the statistical arbitrage part of the strategy. The model is looking for mispriced time spreads relative to expected fundamentals, while the battery provides the physical mechanism to capture those spreads.

## Model Improvement Path

Start simple and improve only where backtests show measurable value.

Candidate model ladder:

1. Seasonal naive model:
   - Predict price from historical averages by hour or 15-minute slot, weekday, and month.
2. Linear fundamental model:
   - Add load forecast, RES forecast, weather, and optional gas/carbon variables.
3. Residual model:
   - Model the error of the linear forecast using recent residuals, analog days, and rolling price regime indicators.
4. Spread model:
   - Predict charge-discharge spread directly instead of predicting each interval independently.
5. Scenario model:
   - Generate multiple price paths from historical residuals and optimize for expected profit subject to downside limits.

The main comparison should be economic, not only statistical:

- Forecast MAE / RMSE.
- Spread hit rate.
- Profit per MWh throughput.
- Number of trades skipped by the uncertainty buffer.
- Realized profit versus naive daily rank strategy.
- Downside performance on bad forecast days.

The best model is the one that improves risk-adjusted battery profit after constraints, not necessarily the one with the lowest price forecast error.

## Hold Cost (Theta) Decomposition

The simplified `degradation_cost` term used elsewhere in this document is shorthand for cycling wear only. Real carry has time-based and SoC-dependent components that the optimizer needs to see, otherwise it will hold at 100% SoC for many hours waiting for a peak and not be charged for the privilege.

Full decomposition:

```text
theta_t = theta_cycle
        + theta_calendar
        + theta_self_discharge
        + theta_aux
        + theta_capital
        + theta_fixed
```

| Component | Driver | Scales with | LP form |
| --- | --- | --- | --- |
| `theta_cycle` | Wear from cycling | `charge_t + discharge_t` (throughput) | linear in throughput (already in objective) |
| `theta_calendar` | Capacity fade at rest, accelerated by high SoC and temperature | `SoC_t * dt` | linear in `SoC_t`; kinked form below |
| `theta_self_discharge` | Physical energy leakage from the cell | `SoC_t * dt` | enters SoC dynamics, not the objective |
| `theta_aux` | BMS plus thermal management consumption | `dt` or `price_t * dt` | constant per interval, or priced at clearing |
| `theta_capital` | Cost of capital tied up in stored MWh | `r * V(SoC_t) * dt` | linear in `SoC_t` with shadow price `r` |
| `theta_fixed` | O&M, lease, capacity fees, insurance | `dt` (constant) | does not affect schedule, only reported profit |

LP-compatible implementations:

- Linear calendar fade:
  ```text
  theta_calendar = c_cal * sum_t SoC_t * dt_t
  ```
- Kinked calendar fade above `SoC_threshold` (still LP, via slack `s_t`):
  ```text
  theta_calendar = c_low * sum_t SoC_t + c_high * sum_t s_t
  s_t >= SoC_t - SoC_threshold
  s_t >= 0
  ```
- Self-discharge in the SoC dynamics:
  ```text
  soc_t_plus_1 = (1 - delta_self) * soc_t + eta_ch * charge_t * dt_t - discharge_t * dt_t / eta_dis
  ```
- Aux load: `P_aux * sum_t price_hat_t * dt_t`, or a flat MWh/day deduction.
- Capital cost: `r * value_of_stored_energy(SoC_t) * dt_t`, using rolling charge price or the dual on the SoC bound from the previous solve as the proxy for value.
- Fixed O&M: constant per day, deducted from reported profit only.

Operational consequences once these terms are in the objective:

- Just-in-time charging: a 14-hour hold at full SoC now has a visible cost, so the optimizer trades earlier-and-cheaper charging against later-and-cleaner charging.
- Bias toward a 50-80% SoC band, matching real BESS operating practice and warranty terms.
- Hold-time aware spread filter (see below): a long-hold spread must beat a short-hold spread by enough to cover the additional carry.

Terminology note: in options vocabulary `theta_cycle` is transaction cost, `theta_capital` is rho, and the time-decay components (`theta_calendar`, `theta_self_discharge`, `theta_aux`, `theta_fixed`) are true theta. For the public pitch, treating all of them as "carry" is clearer.

## Spread Filter

For any candidate charge interval `i` and discharge interval `j`, compute the hold-time aware spread:

```text
spread_i_j = price_hat_j * eta_dis
           - price_hat_i / eta_ch
           - (theta_cycle_i + theta_cycle_j)
           - sum_{k=i..j} theta_calendar_k(SoC)
           - sum_{k=i..j} theta_aux_k
           - fees
```

Only allow a trade if:

```text
spread_i_j > lambda_buffer * forecast_error_MAD
```

This prevents the optimizer from chasing small spreads that are likely forecast noise, penalizes long holds at high SoC, and gives a clear explanation for why the battery sometimes remains idle.

## Optimization Layer

Decision variables per interval `t`:

- `charge_t`: MW charged.
- `discharge_t`: MW discharged.
- `soc_t`: MWh state of charge.

Objective:

```text
maximize sum_t dt_t * price_hat_t * (discharge_t - charge_t)
       - degradation_cost * sum_t dt_t * (charge_t + discharge_t)
       - fees * sum_t dt_t * (charge_t + discharge_t)
```

Core constraints:

```text
soc_t_plus_1 = (1 - delta_self) * soc_t + eta_ch * charge_t * dt_t - discharge_t * dt_t / eta_dis

0 <= soc_t <= energy_capacity_mwh
0 <= charge_t <= charge_power_max_mw
0 <= discharge_t <= discharge_power_max_mw
soc_final approximately equals soc_initial
daily_throughput <= allowed_daily_throughput
```

Implementation note:

- The constraint `charge_t * discharge_t = 0` is nonlinear.
- For a pure linear program, use a net-power formulation or rely on efficiency plus degradation costs to make simultaneous charge/discharge uneconomic.
- If strict mutual exclusivity is required, use a mixed-integer linear program with a binary mode variable.

## Baselines

Compare the optimizer against:

1. Idle battery: zero profit, zero degradation.
2. Naive daily rank strategy:
   - Charge during the lowest-priced feasible intervals.
   - Discharge during the highest-priced later-compatible intervals.
   - Skip the day if average spread does not clear losses, degradation, and safety margin.
3. Perfect foresight upper bound:
   - Optimize against realized DAM prices.
   - Use only as a benchmark, never as an operational strategy.

## Evaluation Metrics

Report:

- Expected daily profit.
- Realized backtest profit.
- Worst-case scenario profit.
- Total cycles or throughput.
- Degradation cost.
- State-of-charge path.
- Number of idle intervals and idle days.
- Profit versus naive baseline.
- Sensitivity to efficiency, degradation cost, and forecast-error buffer.

## Initial Deliverable Shape

The first working solution should be:

1. A downloader for HEnEx DAM prices, IPTO load forecasts, IPTO RES forecasts, and Open-Meteo weather.
2. A clean aligned time-series table at hourly or 15-minute resolution.
3. A simple price forecast or analog-day estimator.
4. A spread-filtered battery optimizer.
5. A backtest report with plots for price, schedule, state of charge, and profit.

## Pitch Sentence

**Weather-conditioned, degradation-aware day-ahead battery spread optimization for the Greek DAM under data scarcity.**
