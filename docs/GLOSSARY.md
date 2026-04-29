# GLOSSARY.md

Vocabulary bridge between options/derivatives language (which is how the strategy was *thought through*) and power-market language (which is how it should be *presented*). This file exists so an agent reading STRATEGY.md doesn't have to guess what "long price dispersion" means in LP terms.

## The one-line mapping

> A battery is **long price dispersion across time, short carry.** Price dispersion is the optionality (gamma); losses, degradation, calendar fade, and capital-tied-up are the carry (theta). The LP picks the schedule that maximizes expected dispersion harvest minus carry, subject to physical constraints.

## Greeks → power-market quantities

These are first-order finite-difference sensitivities of the optimizer's value function `V(P)` (expected profit given price scenarios `P`) to the inputs.

```
delta_t  = ( V(P + ε·e_t) − V(P − ε·e_t) ) / (2ε)
gamma_t  = ( V(P + ε·e_t) − 2·V(P) + V(P − ε·e_t) ) / ε²
theta    = dV / d(degradation_cost)        # negative; carry
vega_f   = dV / d(σ_forecast)              # negative; wider forecast → wider buffer → fewer trades
vega_r   = dV / d(σ_realized)              # positive;  wider realized spreads → more profit
```

| Symbol | What it measures (power-market reading) | Used in code as |
| --- | --- | --- |
| `delta_t` | Marginal value of one extra EUR/MWh at interval `t` | Sanity check on optimizer dual / shadow price on `price_hat_t` |
| `gamma_t` | Convexity in price at interval `t` — value of dispersion around `t`, captured because the battery can choose to charge OR discharge | Indirectly captured by stochastic LP over scenarios; deterministic LP misses it |
| `theta` | Hold cost per unit of stored energy per interval (cycle wear, calendar fade, self-discharge, aux load, capital, fixed). See [OPTIMIZER.md](OPTIMIZER.md) | `theta_cycle + theta_calendar + theta_self_discharge + theta_aux + theta_capital + theta_fixed` |
| `vega_f` | Sensitivity to **forecast** uncertainty. **Short**: wider forecast → larger `lambda_buffer · MAD` → spread filter rejects more candidate trades → fewer trades, lower expected profit | Set in spread filter via `lambda_buffer` |
| `vega_r` | Sensitivity to **realized** intra-day volatility. **Long**: wider realized spreads → bigger `(p_high − p_low)` → more profit | Realized P&L property; not a tunable, but it explains why the strategy fits well in volatile months |

The strategy is **long vega_r, short vega_f** — i.e. we want the realized world to have wide intra-day spreads (RES surplus → scarcity), but we want our forecast to be tight enough that we actually trade. This is the classic stat-arb tension and is why the forecast quality matters more than the optimizer sophistication.

## Power-market terms (for someone arriving from quant finance)

| Term | Plain reading |
| --- | --- |
| **DAM** | Day-Ahead Market. Closes D-1 ~ 12:00 EET. One auction per delivery day, 96 × 15-min delivery periods (since 2025-10-01). Greek operator: HEnEx. |
| **MTU** | Market Time Unit. The atomic delivery period. 60 min before 2025-10-01, **15 min after**. |
| **MCP** | Market Clearing Price. The uniform price all accepted buyers pay and all accepted sellers receive for that delivery period. |
| **Uniform-price auction** | All accepted bids clear at the marginal (last-accepted) offer's price. Greek DAM uses this. |
| **SDAC** | Single Day-Ahead Coupling. Pan-European common algorithm that clears coupled zones simultaneously, respecting cross-border NTC. |
| **IPTO / ADMIE** | Greek transmission system operator. Publishes load forecasts, RES forecasts, ATC values. |
| **Residual load (RL)** | `load - solar - wind`. The portion of demand that thermal generators (and imports) must serve. The single most important price driver in a high-RES market. |
| **Merit order** | Generators stack from cheapest to most expensive (RES → nuclear → lignite → CCGT → OCGT → diesel/scarcity). The marginal generator sets MCP. |
| **Curtailment** | Forced reduction of RES output when supply > demand or grid can't absorb it. Greek curtailment rose sharply in 2025. |
| **Duck curve** | Mid-day solar-driven dip in residual load followed by sharp evening ramp as solar fades and demand rises. Battery's natural prey. |
| **NTC / ATC** | Net / Available Transmission Capacity on cross-border links. Caps imports/exports; tightens scarcity prices when binding. |
| **Round-trip efficiency** | `eta_ch · eta_dis`. Energy out / energy in. Typical Li-ion BESS: 0.85–0.92. |
| **Cycle / throughput** | One cycle = one full charge + discharge of `E_max`. Throughput = `Σ_t (charge_t + discharge_t) · dt_t`. Warranty terms cap cycles per day or lifetime throughput. |
| **State of charge (SoC)** | Energy stored, in MWh or as fraction of `E_max`. |
| **Calendar fade** | Capacity loss from time alone, accelerated at high SoC and high temperature. Distinct from cycling wear. |
| **Self-discharge** | Energy leakage from the cell at rest. ~ 0.5%/day for Li-ion. |
| **TTF** | Title Transfer Facility. Dutch gas hub; the European gas benchmark. Drives marginal cost of CCGT/OCGT, which is usually price-setting in normal regimes. |
| **EUA** | EU Emissions Allowance. Price of emitting one tonne of CO₂. Adds to thermal marginal cost. |
| **Aggregated buy/sell curves** | HEnEx publishes the stepwise demand and supply curves used to clear each delivery period. Their slope at clearing = "market tightness" = how much an extra MWh of demand would move price. |

## Strategy phrase translation

For the public pitch, do not say "long gamma." Say one of:

- *robust day-ahead battery spread optimization*
- *degradation-aware stochastic battery scheduling*
- *curve-aware statistical arbitrage in the day-ahead market*

For internal reasoning, the options frame is faster:

- "We want gamma" = we want the price path to have curvature, i.e. wide intra-day spreads.
- "Theta is bleeding us" = SoC is held too high too long; calendar fade is eating profit.
- "The trade has bad vega_f / vega_r ratio" = forecast uncertainty is large relative to the dispersion we expect to monetize. Skip the day.
- "The optimizer is short gamma in this regime" = deterministic LP on a flat P50 has no dispersion to harvest; switch to scenarios.

## What we are *not* claiming

- The battery has true optionality in the financial sense. It has a single first-stage decision per day (DAM is once-only, no recourse). The "options analogy" is a useful intuition, not a structural claim.
- Greeks here are sensitivities of the LP value function, not derivative sensitivities of a traded product.
- "Stat arb" here means *exploiting recurring statistical structure in the price formation* (RES surplus, evening ramps), not pairs trading.
