# MEMORY.md

Durable project state. Read this before acting; update it when state changes. This file is the answer to "what does an agent need to know about this repo *right now* that is not in STRATEGY.md and not derivable from the code?"

Keep entries short. If a section grows past a few lines, promote it to its own spec file and link.

---

## Project context

- **Event:** HEnEx hackathon — *Battery Optimization in the Greek Electricity Market*. Source brief: [Hackathon_final.docx.pdf](../Hackathon_final.docx.pdf).
- **Today:** 2026-04-29. Greece's first standalone batteries entered DAM test mode in April 2026, so there is **no mature battery operating history**. The brief calls this out as intentional data scarcity.
- **Market resolution:** hourly until 2025-09-30, **15-minute MTU from 2025-10-01 onward**. Any model that ignores this will silently average over four 15-min slots and lose the intra-hour spread that is the entire point of the trade.
- **Pitch sentence (canonical):** *Weather-conditioned, degradation-aware day-ahead battery spread optimization for the Greek DAM under data scarcity.*

## Core thesis (the one paragraph that matters)

The battery monetizes recurring statistical structure in the Greek DAM: midday RES surplus → low/negative prices, evening residual-load ramp → high prices, regime-dependent nonlinear spike probability. We **forecast a distribution of clearing prices** (P10/P50/P90 or N scenarios), compute the **distribution of charge-discharge spreads**, and feed that into a **degradation-aware stochastic LP**. Trade only when expected spread clears losses + carry + a forecast-uncertainty buffer. See [STRATEGY.md](STRATEGY.md) for the long form.

## Decisions log

Append-only. Each entry: date, decision, why, where it lives. If a decision changes, add a new entry — do not edit history.

- **2026-04-29 — Strategy framing.** Battery as "long price dispersion / short carry." Public pitch language is "robust day-ahead battery spread optimization." Why: keeps the options-theory edge in our heads without exposing it. Where: [STRATEGY.md](STRATEGY.md), [GLOSSARY.md](GLOSSARY.md).
- **2026-04-29 — Forecast architecture is tiered, not monolithic.** Tier 0 ships a quantile baseline; Tier 1 adds soft regimes; Tier 2 adds HEnEx curve features *only if* historical curves are accessible; Tier 3 adds Greek-specific structural features. Why: ship something every step; do not let a Tier-2 rabbit hole block a working submission. Where: [PLAN.md](PLAN.md), [FORECAST.md](FORECAST.md).
- **2026-04-29 — Soft regimes over hard regimes; three regimes (surplus / normal / scarcity).** Why: regime label is itself a forecast; mixture weights interpolate at boundaries instead of jumping; four regimes splits 7 months of 15-min data too thin. Where: [FORECAST.md](FORECAST.md).
- **2026-04-29 — Train on hourly history, predict at 15-min via intra-hour shape.** Why: only ~7 months of 15-min data exists as of 2026-04-29; insufficient for a regime model standalone. Where: [FORECAST.md](FORECAST.md), [DATA.md](DATA.md).
- **2026-04-29 — CVaR stochastic LP is optimizer-layer, not forecast-layer.** Forecast just emits scenarios. Optimizer starts deterministic-with-buffer (λ_buffer · forecast_error_MAD) and graduates to CVaR once scenarios are wired up. Why: separates concerns; lets the backtest run before the stochastic solver is in place. Where: [OPTIMIZER.md](OPTIMIZER.md).
- **2026-04-29 — Theta is decomposed (cycle + calendar + self-discharge + aux + capital + fixed), not a single `degradation_cost` scalar.** Why: a single scalar lets the optimizer hold at 100% SoC for 14 hours waiting for a peak with no penalty; that is unphysical and presents badly. Where: [STRATEGY.md](STRATEGY.md) §"Hold Cost (Theta) Decomposition", [OPTIMIZER.md](OPTIMIZER.md).
- **2026-04-29 — LP not MILP, until proven necessary.** Use net-power formulation + efficiency penalty so simultaneous charge/discharge is uneconomic; promote to MILP with a binary mode variable only if simulation shows the LP relaxes incorrectly. Why: solver simplicity, faster scenario sweeps. Where: [OPTIMIZER.md](OPTIMIZER.md).

## Open questions (need user decision before committing code)

- **HEnEx historical curve archives.** Are aggregated buy/sell curves downloadable with usable historical depth? If yes, Tier 2 (curve-aware) is real; if no, it stays aspirational and we present without it.
- **Gas + carbon access.** TTF spot is hard to get historically without a license. Daily settlements via public sources are doable but noisy. Ship Tier 0 without; revisit only if cheap.
- **ENTSO-E API token.** Useful for cross-border NTC and cross-checks. Worth provisioning only if a feature in the model actually needs it.
- **λ_buffer (forecast-uncertainty multiplier on the spread filter)** and **λ_CVaR (downside aversion in the stochastic objective)**. Calibrate from backtest; current placeholder values: `λ_buffer = 1.0`, `λ_CVaR = 0.5`. Confirm before locking.

## Constraints to remember

- **Look-ahead leakage is the failure mode.** Every feature must be available before DAM gate closure (D-1 ≈ 12:00 EET). Realized values → labels and evaluation only. If the backtest looks too good, this is the first place to check.
- **No mocking the database / market.** Backtest uses realized DAM prices and *forecast vintages* of inputs (load forecast, RES forecast, weather forecast). Do not feed realized RL into a model that will be served forecast RL at inference.
- **Don't average over the hourly→15-min transition.** Two regimes of resolution. The model needs to know which one each row is in (`mtu_resolution` column), or you need to subset.
- **Battery telemetry does not exist for Greek standalone assets pre-April-2026.** All battery-side parameters (`eta_ch`, `eta_dis`, `E_max`, `P_ch_max`, `P_dis_max`, `delta_self`, `kappa_cycle`, calendar fade rates, `SoC_threshold`) come from datasheet defaults or industry priors, not from data. Document chosen values in [OPTIMIZER.md](OPTIMIZER.md).

## What is done

- HEnEx DAM, IPTO load, IPTO RES, Open-Meteo weather downloaders + parsers ([data_pipeline.py](../data_pipeline.py)).
- Per-day aligned dataset builder writing to `data/processed/<date>_aligned_dataset.csv`.
- Strategy thesis written down ([STRATEGY.md](STRATEGY.md)) including theta decomposition.

## What is next

See [PLAN.md](PLAN.md) for the tiered roadmap and current cursor position.
