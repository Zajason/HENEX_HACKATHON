# Battery Optimization Constraints

## 0. Base-case assumptions

For the base case, we assume a standalone utility-scale Battery Energy Storage System (BESS):

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
| Degradation cost | $c^{deg}$ | 10 €/MWh throughput |
| Maximum cycles per day | $N^{max}_{cycles}$ | 2 |
| Grid import limit | $P^{grid,import}_{max}$ | 75 MW |
| Grid export limit | $P^{grid,export}_{max}$ | 75 MW |

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
E_t = E_{t-1} + \eta_{ch} P^{ch}_t \Delta t - \frac{P^{dis}_t}{\eta_{dis}} \Delta t
$$

where:

| Parameter | Meaning |
|---|---|
| $E_t$ | battery energy at the end of time step $t$ |
| $\eta_{ch}$ | charging efficiency |
| $\eta_{dis}$ | discharging efficiency |
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

If self-discharge is included, the SOC equation becomes:

$$
E_t = (1-\lambda \Delta t)E_{t-1} + \eta_{ch}P^{ch}_t\Delta t - \frac{P^{dis}_t}{\eta_{dis}}\Delta t
$$

where $\lambda$ is the standing loss rate per hour.

For a day-ahead arbitrage model over a short horizon, this can be set to:

$$
\lambda = 0
$$

or a very small value.

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

## References

- PyPSA storage optimization documentation: https://docs.pypsa.org/v1.0.5/user-guide/optimization/storage/
- PyPSA StorageUnit component documentation: https://docs.pypsa.org/latest/user-guide/components/storage-units/
- NREL ATB 2024 utility-scale battery storage: https://atb.nrel.gov/electricity/2024/utility-scale_battery_storage
- NREL ATB 2024 commercial battery storage, round-trip efficiency definition: https://atb.nrel.gov/electricity/2024/commercial_battery_storage
