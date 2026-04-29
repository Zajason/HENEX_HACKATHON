# OPTIMIZER.md

The optimization layer. STRATEGY.md gives the concept and the theta decomposition; this file is the implementation contract.

## Decision variables (per 15-min interval `t`)

| Variable | Units | Bounds |
| --- | --- | --- |
| `charge_t` | MW | `0 ≤ charge_t ≤ P_ch_max` |
| `discharge_t` | MW | `0 ≤ discharge_t ≤ P_dis_max` |
| `soc_t` | MWh | `SoC_min ≤ soc_t ≤ E_max` |
| `s_t` *(Tier 3)* | MWh | `s_t ≥ 0`, `s_t ≥ soc_t - SoC_threshold` (slack for kinked calendar fade) |

All variables continuous → LP. We do **not** introduce a binary mode variable (which would force MILP) until simulation shows the LP's relaxation actually picks simultaneous charge/discharge with positive objective contribution. With efficiency penalties and theta_cycle in the objective, simultaneous operation is uneconomic and the LP keeps `charge_t · discharge_t = 0` at the optimum without explicit constraint.

## Battery parameters (datasheet priors — no telemetry yet)

The brief explicitly says we work without rich battery telemetry. These are starting values; document any change here when you tune them.

| Parameter | Symbol | Default | Notes |
| --- | --- | --- | --- |
| Energy capacity | `E_max` | 10 MWh | typical small grid-scale BESS |
| Charge power max | `P_ch_max` | 5 MW | 0.5C |
| Discharge power max | `P_dis_max` | 5 MW | 0.5C |
| Round-trip efficiency | `eta_ch · eta_dis` | 0.88 | split as `eta_ch = 0.94`, `eta_dis = 0.94` |
| Self-discharge per interval | `delta_self` | `~5e-5` | ~ 0.5% per day at 96 intervals |
| Min SoC | `SoC_min` | 0.10 · `E_max` | warranty-friendly floor |
| Calendar-fade kink threshold | `SoC_threshold` | 0.80 · `E_max` | fade rate jumps above this |
| Daily throughput cap | `cycles_per_day · E_max` | `1.5 · E_max` | warranty / wear control |

## Theta decomposition (LP-compatible)

From STRATEGY.md §"Hold Cost (Theta) Decomposition". Implemented in `optimizer/theta.py` and added to the objective by tier.

| Component | Tier | LP form |
| --- | --- | --- |
| `theta_cycle` | 0 | `kappa_cycle · Σ_t dt_t · (charge_t + discharge_t)` |
| `theta_calendar` linear | 3 | `c_cal · Σ_t soc_t · dt_t` |
| `theta_calendar` kinked above `SoC_threshold` | 3 | `c_low · Σ_t soc_t + c_high · Σ_t s_t`, with slack `s_t ≥ soc_t - SoC_threshold`, `s_t ≥ 0` |
| `theta_self_discharge` | 1+ | enters SoC dynamics, not the objective |
| `theta_aux` | 3 | `P_aux · Σ_t price_hat_t · dt_t` (priced) **or** `P_aux · Σ_t dt_t · price_const` (flat) |
| `theta_capital` | 3 | `r · Σ_t value(soc_t) · dt_t`; use rolling charge price or the SoC-bound dual from prior solve as `value(soc_t)` |
| `theta_fixed` | 3 | constant per day; deducted from reported profit only, not in the optimization |

`kappa_cycle` calibration:

```
kappa_cycle = battery_capex_per_mwh / lifetime_throughput_mwh
            = capex_eur_per_mwh / (cycles_lifetime · 2 · E_max)
```

Default: `capex_eur_per_mwh = 250 000`, `cycles_lifetime = 6 000` → `kappa_cycle ≈ 20 EUR/MWh` of throughput. Tune in [MEMORY.md](MEMORY.md) decisions log when you change.

## Tier 0 — deterministic LP on P50 with spread filter

Objective:

```
maximize  Σ_t  dt_t · p50_t · (discharge_t - charge_t)
        − kappa_cycle · Σ_t dt_t · (charge_t + discharge_t)
        − fees      · Σ_t dt_t · (charge_t + discharge_t)
```

Constraints:

```
soc_{t+1} = (1 - delta_self) · soc_t + eta_ch · charge_t · dt_t - discharge_t · dt_t / eta_dis
SoC_min ≤ soc_t ≤ E_max
0 ≤ charge_t ≤ P_ch_max
0 ≤ discharge_t ≤ P_dis_max
soc_T ≈ soc_0                                # cyclic, soft equality with small slack
Σ_t dt_t · (charge_t + discharge_t) ≤ allowed_daily_throughput
```

**Spread filter as pre-pass** (cuts the search before the LP runs):

```
spread_ij = p50_j · eta_dis - p50_i / eta_ch
          - (theta_cycle_i + theta_cycle_j)
          - sum_{k=i..j} theta_calendar_k_estimate
          - sum_{k=i..j} theta_aux_k
          - fees_i_j
allow (i, j) only if  spread_ij > lambda_buffer · MAD_{hour(i), hour(j)}
```

If no `(i, j)` pair survives the filter for the day, output `idle` schedule (all zeros) and exit. This is the optimizer's way to say "no robust spread today" — a feature, not a bug. Backtest reports the fraction of idle days.

`lambda_buffer` default: `1.0`. Calibrate from backtest.

## Tier 1 — same LP, but on regime-mixture P50

No structural change to the LP. The forecast just emits a different P50 (the regime-weighted mixture). Spread filter uses `μ_ij` and `σ_ij` from the bootstrap scenarios:

```
μ_ij = mean_s ( spread_ij^s )
σ_ij = std_s  ( spread_ij^s )
z_ij = μ_ij / σ_ij
allow (i, j) only if z_ij > z_threshold     # default 1.0
```

This is a tighter filter than the MAD version because it accounts for regime-dependent uncertainty.

## Tier 3 — stochastic LP with CVaR penalty

Decision variables: same `charge_t, discharge_t, soc_t`, plus per-scenario profit auxiliary `pi_s` and CVaR auxiliaries `(eta, u_s)`.

Per-scenario profit:

```
pi_s = Σ_t dt_t · price_t^s · (discharge_t - charge_t)
     − Σ_t dt_t · kappa_cycle · (charge_t + discharge_t)
     − fees · Σ_t dt_t · (charge_t + discharge_t)
     − [theta_calendar terms]   # same SoC-based, scenario-independent
     − [theta_aux terms]
```

CVaR_α as an LP epigraph (Rockafellar–Uryasev, α = 5%):

```
CVaR_α(loss) = min_{eta, u}   eta + (1 / (α N)) · Σ_s u_s
             s.t.             u_s ≥ -pi_s - eta
                              u_s ≥ 0
```

Objective:

```
maximize  (1/N) · Σ_s pi_s   −   lambda_CVaR · CVaR_α(-pi)
                              =  (1/N) · Σ_s pi_s
                                 − lambda_CVaR · ( eta + (1/(α N)) · Σ_s u_s )
```

Decision `(charge_t, discharge_t, soc_t)` is **first-stage** — one schedule, evaluated against all N scenarios. There is no recourse — DAM submission is once-per-day and irrevocable.

`lambda_CVaR` default: `0.5`. Tune so realized worst-day loss falls without giving up > 10% of expected profit (PLAN.md exit criterion).

## Solver

- Default: `scipy.optimize.linprog(method="highs")`. Fast on these problem sizes (96 intervals × N scenarios × few constraints).
- If the formulation grows or you want better diagnostics, drop in `cvxpy` with HiGHS or CLARABEL. `cvxpy` is more pleasant for the CVaR epigraph.
- Avoid commercial solvers (Gurobi, CPLEX) — license adds friction in a hackathon judging environment.

## Net-power formulation (avoid the simultaneous-charge/discharge MILP trap)

If at any tier the LP optimum has both `charge_t > 0` and `discharge_t > 0` with positive objective contribution (i.e. the model is gaming the round-trip), you have one of two issues:

1. `kappa_cycle` is too low and round-trip efficiency penalty alone isn't enough — raise it or add a small L1 penalty on `charge_t + discharge_t`.
2. The price scenario has a weird arbitrage that the LP exploits via the relaxation. Check forecast sanity before reaching for MILP.

Only if both are ruled out, introduce a binary `mode_t ∈ {0, 1}` with `charge_t ≤ M · mode_t`, `discharge_t ≤ M · (1 - mode_t)` and switch to MILP. Document the switch in [MEMORY.md](MEMORY.md).

## Outputs

`optimizer.lp_*.solve(...)` returns a dict:

```
{
  "schedule": DataFrame[timestamp, charge_mw, discharge_mw, soc_mwh, mode],
  "expected_profit_eur": float,
  "cvar5_profit_eur": float,            # only meaningful for Tier 3
  "worst_scenario_profit_eur": float,    # only meaningful for Tier 1+
  "cycles": float,
  "throughput_mwh": float,
  "idle_intervals": int,
  "infeasible": bool,
  "solver_status": str,
  "binding_constraints": list[str],
}
```

The `binding_constraints` field is gold for the demo narrative — it tells you *why* the schedule did what it did (was it the throughput cap, the SoC bound, the calendar fade penalty?).

## What to report in the pitch

For a chosen demo day, show:

1. Forecast P10/P50/P90 over 96 intervals overlaid on realized price.
2. Optimal schedule (charge / discharge / idle) and SoC path.
3. Profit decomposition: gross revenue − cycle wear − calendar fade − aux − fees.
4. Counterfactuals: idle = 0; naive daily rank profit; perfect-foresight upper bound.
5. The `binding_constraints` story in one sentence. ("Today the throughput cap binds — the spread is wide enough that we'd want to do 2 cycles, but warranty caps us at 1.5.")
