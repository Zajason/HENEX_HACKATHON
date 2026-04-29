# Battery Optimization Constraints

## 0. Base-case assumptions

For the base case, we assume a standalone utility-scale Battery Energy Storage System (BESS) with LFP chemistry:

| Parameter | Symbol | Value |
|---|---:|---:|
| Nominal power | $P_{nom}$ | 75 MW |
| Energy capacity | $E_{nom}$ | 300 MWh |
| Duration | $D$ | 4 h |
| Time step | $\Delta t$ | 0.25 h |
| Minimum SOC | $SOC_{min}$ | 10% |
| Maximum SOC | $SOC_{max}$ | 90% |
| Initial SOC | $SOC_0$ | 50% |
| Charging efficiency | $\eta_{ch}$ | 0.95 |
| Discharging efficiency | $\eta_{dis}$ | 0.95 |
| Round-trip efficiency | $RTE$ | $0.95 \cdot 0.95 \approx 90\%$ |
| Self-discharge rate | $\lambda_{self}$ | $5 \times 10^{-5}$ /h (≈ 0.12% / day) |
| Auxiliary parasitic load | $P_{aux}$ | 0.5 MW continuous |
| Degradation cost | $c^{deg}$ | 10 €/MWh throughput |
| Maximum cycles per day | $N^{max}_{cycles}$ | 2 |
| Grid import limit | $P^{grid,import}_{max}$ | 75 MW |
| Grid export limit | $P^{grid,export}_{max}$ | 75 MW |
| DAM safety margin | $m^{DAM}$ | 5% of $P_{nom}$ (3.75 MW) |
| Imbalance short price uplift | $\beta^{IMB,short}$ | +35 €/MWh over reference |
| Imbalance long price discount | $\beta^{IMB,long}$ | −20 €/MWh below reference |
| Non-compliance threshold | $\tau_{tol}$ | 5% of $P_{nom}$ (3.75 MW) |
| Non-compliance penalty | $c^{NC}$ | 100 €/MWh over threshold |
| Execution uncertainty | $\sigma^{exec}$ | 2% of $|P^{DAM}_t|$ |

The energy capacity follows from:

$$
E_{nom} = P_{nom} \cdot D = 75 \cdot 4 = 300 \text{ MWh}
$$

---

## 1. Decision variables

For each time step $t$:

| Variable | Unit | Meaning |
|---|---:|---|
| $P^{ch}_t$ | MW | Charging power |
| $P^{dis}_t$ | MW | Discharging power |
| $E_t$ | MWh | Energy stored in the battery at the end of time step $t$ |
| $u^{ch}_t$ | binary | 1 if the battery is charging |
| $u^{dis}_t$ | binary | 1 if the battery is discharging |

---

## 2. Charging power limit

The battery cannot charge above its maximum charging power:

$$
0 \leq P^{ch}_t \leq P^{ch}_{max} u^{ch}_t
$$

For the base case:

$$
P^{ch}_{max} = 75 \text{ MW}
$$

If $u^{ch}_t=0$, then $P^{ch}_t=0$. If $u^{ch}_t=1$, the battery may charge up to $P^{ch}_{max}$.

---

## 3. Discharging power limit

The battery cannot discharge above its maximum discharging power:

$$
0 \leq P^{dis}_t \leq P^{dis}_{max} u^{dis}_t
$$

For the base case:

$$
P^{dis}_{max} = 75 \text{ MW}
$$

---

## 4. No simultaneous charging and discharging

The battery cannot charge and discharge at the same time:

$$
u^{ch}_t + u^{dis}_t \leq 1
$$

Allowed operating modes:

| Mode | $u^{ch}_t$ | $u^{dis}_t$ |
|---|---:|---:|
| Charging | 1 | 0 |
| Discharging | 0 | 1 |
| Idle | 0 | 0 |
| Simultaneous charge/discharge | 1 | 1, not allowed |

---

## 5. State-of-charge energy balance

The energy stored in the battery evolves according to:

$$
E_t = (1 - \lambda_{self}\Delta t) E_{t-1} + \eta_{ch} P^{ch}_t \Delta t - \frac{P^{dis}_t}{\eta_{dis}} \Delta t - P_{aux} \Delta t
$$

where:

| Parameter | Meaning |
|---|---|
| $E_t$ | battery energy at the end of time step $t$ |
| $\eta_{ch}$ | charging efficiency |
| $\eta_{dis}$ | discharging efficiency |
| $\lambda_{self}$ | self-discharge rate per hour |
| $P_{aux}$ | auxiliary parasitic load (HVAC, BMS, monitoring) |
| $\Delta t$ | time step duration in hours |

For 15-minute DAM data:

$$
\Delta t = 0.25 \text{ h}
$$

---

## 6. SOC bounds

The battery should not operate at 0% or 100% SOC. We therefore impose:

$$
E_{min} \leq E_t \leq E_{max}
$$

with:

$$
E_{min} = SOC_{min} E_{nom}
$$

$$
E_{max} = SOC_{max} E_{nom}
$$

For the base case:

$$
E_{min}=0.10 \cdot 300 = 30 \text{ MWh}
$$

$$
E_{max}=0.90 \cdot 300 = 270 \text{ MWh}
$$

---

## 7. Initial SOC

The initial energy level must be fixed:

$$
E_0 = E_{initial}
$$

For the base case:

$$
E_{initial} = 0.50 \cdot E_{nom} = 0.50 \cdot 300 = 150 \text{ MWh}
$$

This prevents the optimizer from assuming an unrealistic initial energy level.

---

## 8. Terminal SOC

For daily scheduling, the battery should finish the day with the same energy level it started with:

$$
E_T = E_0
$$

This prevents artificial profit caused by emptying the battery at the end of the optimization horizon.

---

## 9. Duration relation

Battery duration is the number of hours the battery can discharge at nominal power:

$$
D = \frac{E_{nom}}{P_{nom}}
$$

Equivalently:

$$
E_{nom} = P_{nom} \cdot D
$$

For the base case:

$$
D = \frac{300}{75}=4 \text{ h}
$$

A useful sensitivity analysis is:

| Scenario | $P_{nom}$ | $E_{nom}$ | Duration |
|---|---:|---:|---:|
| Short-duration | 75 MW | 150 MWh | 2 h |
| Base case | 75 MW | 300 MWh | 4 h |
| Longer-duration | 75 MW | 450 MWh | 6 h |

---

## 10. Round-trip efficiency

Round-trip efficiency is the share of input energy recovered after a full charge-discharge cycle:

$$
RTE = \eta_{ch} \cdot \eta_{dis}
$$

For the base case:

$$
RTE = 0.95 \cdot 0.95 = 0.9025 \approx 90\%
$$

This means that if 100 MWh are taken from the grid for charging, approximately 90 MWh can be delivered back to the grid after discharge.

---

## 11. Self-discharge / standing loss

For a realistic utility-scale Li-ion (LFP) BESS of this size, **two distinct loss sources** must be modelled — they are **not** negligible at the daily P&L level:

### 11.A Cell self-discharge (electrochemical)

LFP cells lose ~2-3% / month at 25°C at the cell level (EPRI Battery Energy Storage Performance Guide). At pack level, with BMS overhead, this becomes ~3-5% / month. Converted to an hourly rate:

$$
\lambda_{self} = 5 \times 10^{-5} \text{ /h} \quad (\approx 0.12\% \text{ / day})
$$

### 11.B Auxiliary parasitic load (HVAC, BMS, monitoring, lighting)

The BESS draws continuous parasitic power even when idle, primarily for thermal management and control electronics. NREL ATB 2024 estimates this at 0.5-1.5% of $P_{nom}$. For our 75 MW base case:

$$
P_{aux} = 0.5 \text{ MW continuous} \quad (\approx 0.67\% \text{ of } P_{nom})
$$

This translates to ~12 MWh/day standing loss, which **is not negligible** — it typically reduces net profit by €500-1,000 / day depending on price levels.

### Combined SOC dynamics with both loss terms

$$
E_t = (1 - \lambda_{self}\Delta t) E_{t-1} + \eta_{ch}P^{ch}_t\Delta t - \frac{P^{dis}_t}{\eta_{dis}}\Delta t - P_{aux}\Delta t
$$

This is the equation used throughout the optimization (see §5). The aux load is modelled as a constant continuous draw — it does not change with SOC or operating mode (slight simplification; in reality HVAC scales with cell temperature and ambient conditions).

### Sensitivity cases

| Scenario | $\lambda_{self}$ | $P_{aux}$ | Daily standing loss |
|---|---:|---:|---:|
| Modern LFP, well-cooled | $5 \times 10^{-5}$ /h | 0.4 MW | ~10 MWh |
| **Base case** | $5 \times 10^{-5}$ /h | 0.5 MW | ~12 MWh |
| Older or hot-climate | $1 \times 10^{-4}$ /h | 1.0 MW | ~25 MWh |

---

## 12. Cycle / throughput constraint

To avoid excessive battery cycling, we can impose a maximum number of equivalent full cycles per day:

$$
\sum_t P^{dis}_t \Delta t \leq N^{max}_{cycles} E_{nom}
$$

For the base case:

$$
N^{max}_{cycles}=2
$$

$$
E_{nom}=300 \text{ MWh}
$$

Therefore:

$$
\sum_t P^{dis}_t \Delta t \leq 600 \text{ MWh/day}
$$

---

## 13. Degradation cost

Battery cycling causes degradation. To account for this, we add a degradation cost proportional to energy throughput:

$$
C^{deg}=c^{deg}\sum_t(P^{ch}_t+P^{dis}_t)\Delta t
$$

For the base case:

$$
c^{deg}=10 \text{ €/MWh throughput}
$$

Sensitivity cases:

| Scenario | $c^{deg}$ |
|---|---:|
| Low degradation | 5 €/MWh |
| Base case | 10 €/MWh |
| High degradation | 15 €/MWh |

---

## 14. Grid connection limit

The grid connection limit restricts how much power can be imported from or exported to the grid:

$$
P^{ch}_t \leq P^{grid,import}_{max}
$$

$$
P^{dis}_t \leq P^{grid,export}_{max}
$$

For a standalone battery, we assume a symmetric grid connection equal to the nominal battery power:

$$
P^{grid,import}_{max}=P^{grid,export}_{max}=P_{nom}=75 \text{ MW}
$$

---

## 15. Objective function

The optimization maximizes arbitrage profit minus degradation cost:

$$
\max \sum_t \pi_t(P^{dis}_t-P^{ch}_t)\Delta t - c^{deg}\sum_t(P^{ch}_t+P^{dis}_t)\Delta t
$$

where $\pi_t$ is the electricity price in €/MWh.

---

## 16. Final compact formulation

$$
\max \sum_t \pi_t(P^{dis}_t-P^{ch}_t)\Delta t - c^{deg}\sum_t(P^{ch}_t+P^{dis}_t)\Delta t
$$

subject to:

$$
0 \leq P^{ch}_t \leq P^{ch}_{max}u^{ch}_t
$$

$$
0 \leq P^{dis}_t \leq P^{dis}_{max}u^{dis}_t
$$

$$
u^{ch}_t+u^{dis}_t\leq 1
$$

$$
E_t = E_{t-1} + \eta_{ch}P^{ch}_t\Delta t - \frac{P^{dis}_t}{\eta_{dis}}\Delta t
$$

$$
E_{min}\leq E_t\leq E_{max}
$$

$$
E_0=E_{initial}
$$

$$
E_T=E_0
$$

$$
\sum_t P^{dis}_t\Delta t \leq N^{max}_{cycles}E_{nom}
$$

$$
P^{ch}_t\leq P^{grid,import}_{max}
$$

$$
P^{dis}_t\leq P^{grid,export}_{max}
$$

---

## 17. Post-clearing settlement chain (DAM → Imbalance, no Intraday)

The DAM optimization produces a binding commitment, but real-world execution must account for the settlement chain that follows clearing. **This BESS does not participate in the Intraday Market (IDM)** — the only routes for the position after DAM clearing are direct execution and imbalance settlement. The five operational stages are:

1. **DAM order accepted** → binding commercial position from D-1 12:00.
2. **No cancellation after clearing** → DAM financial settlement runs irrevocably.
3. **No intraday recourse** → there is no opportunity to hedge or correct the position via IDM trades. The asset must execute the cleared DAM schedule as-is, or face imbalance.
4. **Real-time deviation** → if actual delivery does not match the cleared DAM schedule, the difference (`actual − scheduled`) is measured.
5. **Imbalance settlement** → the deviation is settled at the **imbalance price** (charge if short, credit if long).
6. **Non-compliance charges** → systematic deviations or violations of dispatch instructions trigger additional penalties.

These stages do **not** appear as classical equality/inequality LP constraints. Instead they enter the D-1 optimization as **expected-cost terms in the objective** plus **safety margins on the binding decision variables**.

The absence of intraday recourse makes the safety margin (§17.6) and the expected-imbalance term (§17.5) more important than they would be in a full DAM+IDM portfolio: there is no second chance to fix a bad position before delivery.

### 17.1 Decision variables

| Variable | Stage | Meaning |
|---|---|---|
| $P^{DAM}_t$ | D-1 | Binding DAM commitment (= $P^{dis}_t - P^{ch}_t$) |
| $\Delta_t = \Delta^+_t - \Delta^-_t$ | Real time | Imbalance: $\Delta^+_t \geq 0$ if over-delivery, $\Delta^-_t \geq 0$ if under-delivery |

### 17.2 DAM revenue (binding, stages 1-2)

$$
R^{DAM} = \sum_t \pi^{DAM}_t \cdot P^{DAM}_t \cdot \Delta t
$$

This is what the deterministic / stochastic LP already optimizes.

### 17.3 Imbalance settlement (stages 3-5)

The imbalance price is **asymmetric** — being short usually costs more than being long is rewarded:

$$
C^{IMB} = \sum_t \left[ \pi^{IMB,short}_t \cdot \Delta^-_t - \pi^{IMB,long}_t \cdot \Delta^+_t \right] \Delta t
$$

with:

$$
\pi^{IMB,short}_t \approx \pi^{DAM}_t + \beta^{IMB,short} = \pi^{DAM}_t + 35 \text{ €/MWh}
$$

$$
\pi^{IMB,long}_t \approx \pi^{DAM}_t - |\beta^{IMB,long}| = \pi^{DAM}_t - 20 \text{ €/MWh}
$$

The asymmetry ($+35$ vs $-20$) reflects that the TSO penalizes shortfalls more harshly than over-delivery. This is the dominant economic incentive to **stay within schedule**.

### 17.4 Non-compliance penalty (stage 6)

For deviations exceeding a tolerance band, additional non-compliance charges apply:

$$
C^{NC} = c^{NC} \sum_t \max\left(|\Delta_t| - \tau_{tol},\ 0\right) \cdot \Delta t
$$

with:

$$
\tau_{tol} = 0.05 \cdot P_{nom} = 3.75 \text{ MW}
$$

$$
c^{NC} = 100 \text{ €/MWh of excess deviation}
$$

This term only activates when the deviation is large enough to trigger TSO-level intervention (typically >5% of nameplate).

### 17.5 D-1 objective with settlement chain

At D-1 we do not yet know $\pi^{IMB}_t$ or the actual deviation $\Delta_t$. They are modelled in **expectation**:

$$
\max\ \mathbb{E}[R^{DAM}] - \mathbb{E}[C^{IMB}] - \mathbb{E}[C^{NC}] - C^{deg}
$$

The expected imbalance cost can be approximated as:

$$
\mathbb{E}[C^{IMB}] \approx \beta^{IMB} \cdot \sigma^{exec}_t \cdot |P^{DAM}_t| \cdot \Delta t
$$

where $\sigma^{exec}_t$ is the **execution uncertainty** of the BESS (fraction of MWh that will likely deviate from schedule due to equipment availability or SOC tracking error), and $\beta^{IMB}$ is the calibrated imbalance premium (~30-50 €/MWh from historical data).

Default execution uncertainty for a well-instrumented BESS:

$$
\sigma^{exec}_t = 2\%
$$

Because there is no intraday corrective channel, this expected-imbalance term is the **only** ex-ante mechanism for the optimizer to internalise execution risk. It should not be omitted.

### 17.6 DAM safety margin (operational hedge against imbalance risk)

To reduce expected imbalance exposure, the binding DAM bid is capped below the physical limit:

$$
0 \leq P^{ch}_t \leq (P^{ch}_{max} - m^{DAM}) u^{ch}_t
$$

$$
0 \leq P^{dis}_t \leq (P^{dis}_{max} - m^{DAM}) u^{dis}_t
$$

with:

$$
m^{DAM} = 0.05 \cdot P_{nom} = 3.75 \text{ MW}
$$

This leaves a 5% headroom on each side (charge and discharge) so that if the BESS slightly under-performs in real time, the deviation stays within the non-compliance tolerance band $\tau_{tol}$ and avoids the high penalty zone of $c^{NC}$. Without intraday recourse, this margin is the operator's primary lever for managing real-time deviation risk.

Effective bid limits become:

$$
P^{DAM,max}_t = 75 - 3.75 = 71.25 \text{ MW}
$$

### 17.7 Updated full objective (D-1 with settlement chain)

Combining all terms:

$$
\max \sum_t \pi^{DAM}_t (P^{dis}_t - P^{ch}_t)\Delta t
- c^{deg}\sum_t (P^{ch}_t + P^{dis}_t)\Delta t
- \mathbb{E}[C^{IMB}]
- \mathbb{E}[C^{NC}]
$$

subject to all constraints in sections 1-16, plus the safety-margin power limits from §17.6.

### 17.8 Modelling notes

- Stages 1, 2 are **descriptive** (market rules) — they justify the *binding* nature of $P^{DAM}_t$ but produce no equation.
- Stage 3 (intraday recourse) is **explicitly excluded** from this BESS — there is no $P^{IDM}$ variable and no IDM cost term. The asset is a pure DAM participant.
- Stages 4, 5, 6 enter as **expected costs** in the D-1 objective via §17.3-17.4, plus the **safety margin** in §17.6. The actual realized values are computed only post-execution in the backtest.
- Calibration of $\beta^{IMB,short}$, $\beta^{IMB,long}$, $\sigma^{exec}_t$, $c^{NC}$ should come from historical Greek imbalance settlement data when available. Defaults above are typical European TSO values.
- Because the optimizer cannot rely on IDM as a release valve, **uncertainty-aware tiers (Tier 1 CVaR, Tier 5 robust) are preferred over Tier 0 deterministic** for this asset profile.

---

## References

- PyPSA storage optimization documentation: https://docs.pypsa.org/v1.0.5/user-guide/optimization/storage/
- PyPSA StorageUnit component documentation: https://docs.pypsa.org/latest/user-guide/components/storage-units/
- NREL ATB 2024 utility-scale battery storage: https://atb.nrel.gov/electricity/2024/utility-scale_battery_storage
- NREL ATB 2024 commercial battery storage, round-trip efficiency definition: https://atb.nrel.gov/electricity/2024/commercial_battery_storage
- EPRI Battery Energy Storage Performance Guide (self-discharge and parasitic load benchmarks)
- ENTSO-E Balancing Report (imbalance pricing methodology and asymmetric settlement)
