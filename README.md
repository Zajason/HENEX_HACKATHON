# HEnEx hackathon — Greek DAM battery

Day-ahead price forecasting and battery dispatch for the Greek
day-ahead market (DAM), built for the HEnEx hackathon. Two layers,
loosely coupled: a forecast model that produces P10/P50/P90 prices
per 15-minute slot, and a risk-aware LP that dispatches a 75 MW /
300 MWh battery against those prices.

## Why this market, why now

Greece has been the most interesting DAM in the EU for a while.
Renewable share is high and rising, the grid is tight enough that
dispatch decisions actually move the clearing price, and the country
flipped from hourly to 15-minute resolution on **1 October 2025**.
That last bit matters: the trading regime we ship code for is barely
six months old, so any model that claims to learn intra-hour dynamics
is learning from ~8.5K observations. Most of the engineering effort
in this repo is about not pretending we have more data than we do.

Standalone batteries enter DAM trade in April 2026. The deadline is
real.

## The forecast layer

`forecast/` has it. The shipping model is three independent LightGBM
quantile regressors at q ∈ {0.10, 0.50, 0.90}. Single stage, not a
two-step "predict the cleared mix then price" pipeline. Features are
forecast-vintage only — anything realised after D-1 12:00 EET is
forbidden. Thirty features, all of which a power trader would name
in thirty seconds: load forecast, residual load, RES share, two
curtailment kinks, six capacity-weighted weather aggregates over six
Greek zones (solar / wind / load weights), TTF gas and EUA carbon
proxies from yfinance, calendar bits including Orthodox Easter.

The output of LightGBM is then recalibrated with empirical residual
quantiles by (hour, weekday). Without this step P10-P90 coverage is
~42%; with it, **79.2%** against an 80% target. Calibration is not
optional when the optimiser sizes its risk buffer from the band
width.

The model trains with sample weights: exponential decay with a
one-year half-life and a floor of 0.3, multiplied by 2× on rows from
the 15-minute era. This is the closest thing to "data augmentation"
in here. We did not inject synthetic noise.

A walk-forward backtest with 365-day initial windows, 30-day steps,
and 30-day horizons over 2024-2025 lands at **9.23 €/MWh average
pinball** and **29.34 €/MWh P50 MAE**. The Feb 2025 slice — the
worst part of the regime transition, where the original baseline
model produced a coverage of 0.20 — recovers to 0.73 after the macro
fix and sample weighting.

A note on skill scores. Our P50 has higher MAE than yesterday's
price as a forecast (−24% skill vs persistence). That is what
calibrated quantile regression does — it regresses the median toward
the conditional mean and trades volatility-tracking for distributional
honesty. The bands are the product. Persistence has none.

## The dispatch layer

`optimisation/forecast_dispatch.py` solves a daily LP in HiGHS via
SciPy. The objective is asymmetric: discharge revenue uses
P50 − λ · uncertainty, charge cost uses P50 + λ · uncertainty,
where uncertainty is the half-width of P10-P90. λ controls how
much of the band the optimiser treats as a guard. We swept it from
0.0 to 0.35 on the 2025 walk-forward and shipped λ = 0.10. That
sits at the knee of the Pareto frontier: aggressive enough to take
thin spreads, conservative enough that the worst day is bounded.

Constraints in the LP are the obvious ones — power, energy, SOC
band, charge/discharge efficiency, daily cycle cap, terminal SOC.
Degradation is priced linearly at 10 €/MWh of throughput. None of
this is novel; the leverage is in the forecast that feeds it.

## The numbers

Backtested over 2025, 339 trading days, 75 MW / 300 MWh battery,
2 cycles/day cap, 95% round-trip efficiency, 10% / 90% SOC band:

| | |
|---|---|
| Annualised realised profit | **€6.73 M / yr** |
| €/MW-yr | €89,671 |
| Win rate | 95.0% |
| Worst day | −€10,134 |
| CVaR(5%) daily | −€2,514 |
| Mean equivalent cycles/day | 0.89 |
| **% of perfect-foresight upper bound** | **70.9%** |

The perfect-foresight number is the one I'd defend hardest to a
panel. We re-ran the same optimiser substituting realised prices for
the forecast — that gives the theoretical maximum any dispatch policy
could achieve on this asset. We capture 71% of it. Published BESS
arbitrage studies typically land at 60-90%.

For reference, the original conservative configuration (λ = 0.35,
which was the upstream default) earned €4.95 M / yr at 52% capture.
The +€1.78 M / yr lift came purely from the lambda sweep — no model
change.

## Layout

```
forecast/                  Tier-0 LightGBM quantile model + calibration + backtest harness
optimisation/              LP dispatch (forecast_dispatch.py is the headline) + tier escalations
scripts/                   Phase A (data), B (model), C (reports), and predict_tomorrow.py
data/raw/                  HEnEx archive, IPTO load+RES, ERA5 NetCDFs, macro CSVs (gitignored)
data/processed/            history.parquet and the walk-forward outputs (gitignored)
models/                    Frozen artefacts: tier0.pkl, calibration_table, mad_table, manifest.json
api/, frontend/            Web UI to run a fresh prediction + see realised P&L
docs/                      MEMORY, STRATEGY, FORECAST, OPTIMIZER, etc. Read STRATEGY first.
```

## Running it

You'll need Python 3.12, the requirements in `requirements.txt`, and
optionally a Copernicus CDS account to refetch ERA5 weather.

From a clean checkout, the smallest reproduction path that doesn't
need internet:

```
python -m scripts.b6_walkforward_with_weather
python -m scripts.calibrate_walkforward
python -m scripts.freeze_model
python -m scripts.c2_mad_table
python -m scripts.backtest_forecast_optimisation \
    --forecast-csv data/processed/forecast_walkforward_v1_with_weather_calibrated.csv \
    --year 2025
```

That's about six minutes of compute. Outputs land in
`data/processed/`, `models/`, and `optimisation/results/`.

To start from raw HEnEx archives and IPTO downloads:

```
python -m scripts.fetch_history --start 2023-01-01 --end 2025-12-31
python -m scripts.a5_merge_era5_weather    # needs ERA5 NetCDFs
```

To predict tomorrow on a clean laptop with the frozen artefacts:

```
python -m scripts.predict_tomorrow --date 2026-04-30
```

That last one fetches IPTO load/RES, Open-Meteo weather for six
zones, and a macro snapshot live, then runs through the pickled
model. About four seconds end-to-end. No training data needed on
disk.

## Caveats

The €6.73 M / yr is gross. Knock off ~€500k/yr for O&M, augmentation
reserve, insurance, and taxes before quoting net. We do not model
ancillary services (FCR, aFRR) — in Greek practice those typically
add another €10-30k/MW-yr stacked on top of DAM revenue, so the
all-in figure for a real operator is meaningfully higher than what
this repo measures.

The backtest is one calendar year. 2025 was a relatively
spread-rich year. 2026 onwards, who knows.

The 2023 IPTO backfill is on disk but currently filtered out of
walk-forward by the dropna on weather columns (we don't have ERA5
2023). Either downloading 12 more ERA5 months or relaxing the dropna
would unlock it.

## Pointers

- `docs/STRATEGY.md` for the high-level pitch
- `docs/FORECAST.md` for forecast-layer detail
- `docs/OPTIMIZER.md` for dispatch-layer detail
- `docs/PLAN.md` for the phase-by-phase build log
- The `forecast-tier1-augment` branch has the macro / cloud / sample
  weighting work that's now on main, plus the lambda sweep.
