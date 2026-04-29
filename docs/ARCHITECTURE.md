# ARCHITECTURE.md

Module layout and dataflow. The repo today is one script; this document is the **target** layout we grow into.

## Dataflow (one slide version)

```
HEnEx DAM       IPTO load     IPTO RES      Open-Meteo          [Tier 2/3 only]
(prices,        forecast      forecast      weather forecast    HEnEx curves
 curves)                                                        TTF gas, EUA carbon
    \             |             |               |                /
     \            v             v               v               /
      `------>  data_pipeline  <----------------------------'
                     |
                     v
             aligned 15-min table        (data/processed/<date>_aligned_dataset.csv)
                     |
                     v
              feature engineering        (residual load, ramps, regime features,
                     |                    calendar dummies, intra-hour shape)
                     v
            forecast layer (FORECAST.md)
                     |
                     v
          P10 / P50 / P90 + N scenarios per 15-min interval
                     |
                     v
            optimizer (OPTIMIZER.md)
              spread filter -> LP / stochastic LP
                     |
                     v
          schedule: charge_t, discharge_t, soc_t, expected profit, CVaR
                     |
                     v
              backtest + evaluation
                     |
                     v
                 report (plots, baselines, sensitivity)
```

## Target module layout

```
HENEX_hackathon/
  data_pipeline.py          # downloaders + parsers + per-day aligned dataset (existing)
  data/
    raw/                    # cache of downloaded files (gitignored)
    processed/              # aligned per-day CSVs + history.parquet

  features/
    __init__.py
    calendar.py             # hour, weekday, month, holiday dummies, JJA, Easter, Aug
    residual_load.py        # RL = load - res, ramps, RES_share, duck_curve_pressure
    intra_hour.py           # broadcast hourly history to 15-min using post-Oct-2025 shape
    regime.py               # soft regime classifier (Tier 1+)

  forecast/
    __init__.py
    quantile_baseline.py    # Tier 0: direct quantile regression on hourly history
    quantile_regime.py      # Tier 1: per-regime quantile + soft-mixture
    scenarios.py            # regime-conditioned residual bootstrap -> N price paths
    error_mad.py            # forecast_error_MAD per (hour, weekday) and per pair (i,j)

  optimizer/
    __init__.py
    lp_deterministic.py     # Tier 0: LP on P50, theta_cycle only, spread filter
    lp_stochastic.py        # Tier 3: max E[profit] - lambda_CVaR * CVaR_5%
    theta.py                # full theta decomposition (cycle, calendar, self_discharge,
                            #   aux, capital, fixed); see OPTIMIZER.md
    spread_filter.py        # spread_ij computation + lambda_buffer * MAD gate
    constraints.py          # SoC dynamics, power bounds, daily throughput, cyclic SoC

  backtest/
    __init__.py
    walk_forward.py         # walk-forward backtest with forecast vintages (no leakage)
    baselines.py            # idle, naive_daily_rank, perfect_foresight
    metrics.py              # profit per MWh, cycles, idle ratio, hit rate, CVaR realised
    report.py               # plots: price + schedule + SoC + profit, sensitivity tables

  scripts/
    fetch_history.py        # batch download + align over a date range -> history.parquet
    run_day.py              # CLI: forecast + optimize + write schedule for one date
    run_backtest.py         # CLI: walk-forward backtest report

  AGENTS.md  MEMORY.md  STRATEGY.md  PLAN.md  ARCHITECTURE.md
  DATA.md    FORECAST.md  OPTIMIZER.md  GLOSSARY.md
  Hackathon_final.docx.pdf
  requirements.txt
```

Layers are added **only when their tier in [PLAN.md](PLAN.md) starts**. Do not stub empty modules.

## Module contracts

Each layer reads from the previous layer and writes a well-typed dataframe. Treat these signatures as informal interfaces — if you change one, update this file.

**features.\* → DataFrame**
- Index/key: `timestamp` (Europe/Athens, naive).
- Required columns from upstream: `dam_price_eur_mwh`, `load_forecast_mw`, `res_forecast_mw`, `temperature_2m_c`, `wind_speed_10m`, `shortwave_radiation`.
- Adds: `residual_load_mw`, `res_share`, `rl_ramp_4h_mw`, `duck_curve_pressure_mw`, calendar dummies, `mtu_resolution ∈ {"hourly","15min"}`.

**forecast.quantile_\* → DataFrame**
- One row per future 15-min interval.
- Columns: `p10_eur_mwh`, `p50_eur_mwh`, `p90_eur_mwh`. Tier 1+ also `regime_w_surplus`, `regime_w_normal`, `regime_w_scarcity`.

**forecast.scenarios → ndarray of shape (N, T)**
- N scenario draws × T future intervals. Default `N = 200`.

**optimizer.lp_\* → dict**
- `schedule`: DataFrame with `timestamp`, `charge_mw`, `discharge_mw`, `soc_mwh`.
- `expected_profit_eur`, `cvar5_profit_eur`, `cycles`, `idle_intervals`, `infeasible: bool`.

**backtest.walk_forward → DataFrame**
- One row per date in the backtest window with optimizer-side decisions, realized DAM, realized profit, and counterfactual baseline profits (idle, naive_rank, perfect_foresight).

## Time alignment — the one rule

There is exactly one timestamp grid. All layers join on it. The grid is:

- 1 row per hour for dates < 2025-10-01 (broadcasted to 15-min downstream when needed).
- 1 row per 15 min for dates ≥ 2025-10-01.
- All timestamps are Europe/Athens, *naive* (`tz_localize(None)` after construction).
- `mtu_resolution` column carries the regime so any consumer can subset cleanly.

If a function takes a dataframe and silently drops or merges across this boundary, that is a bug.
