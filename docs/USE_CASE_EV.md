# Use case for judges: EV fast-charging hubs (QueuePilot-EV)

## The pitch (30 s)
At an EV charging hub, the "counter" is a charger and the "service time" is set by **battery physics**, not by a clerk. Two physical laws make it hard: a battery accepts less power as it fills up, and every charger shares one grid connection. Today hubs split power equally and let everyone charge to 100%. QueuePilot-EV treats the hub as a coupled dynamical system and cuts the **average wait from 48 to 12 minutes (−75%)** on the same hardware, while every driver still leaves with the charge their trip needs.

## Why this is hard (what makes ordinary queueing theory break)
1. **State-dependent service rate.** Erlang/M/M/c assumes a constant service rate. Here the rate depends on the car's state of charge (SOC), which changes every minute.
2. **Coupled servers.** Stalls are not independent: they share a 150 kW transformer, so one car's power is taken from another's.
3. **Service amount is a decision.** How full each car gets (80% or 100%) is something we can decide. It's a control variable, not a given.

## The physics (engine/ev.py)
State of each plugged car: SOC(t). The dynamics:

    dSOC/dt = P_i(t) / E_battery

Battery acceptance limit (CC-CV charging, the standard lithium-ion protocol):

    P_accept(SOC) = P_max                              SOC < 0.8   (constant current)
                  = P_max · (1 − 0.9·(SOC − 0.8)/0.2)  SOC ≥ 0.8   (constant voltage, taper to 10%)

Conservation of power at the site (the transformer constraint):

    Σ_i P_i(t) ≤ P_site,   0 ≤ P_i ≤ P_accept(SOC_i)

Hub: 4 stalls × 60 kW, 150 kW site cap (the grid, not the chargers, is the bottleneck, as at real hubs), 60 kWh batteries, cars arrive at 10–40% SOC, half want 100%.

## The three decisions QueuePilot-EV makes every minute
| Decision | Method | Why it is optimal / correct |
|---|---|---|
| Power split | **Water-filling**: raise a common power level; cars that can't absorb it (tapering) are capped at P_accept, the rest flows to cars in the fast phase | Maximises delivered kW under the site cap: the classic solution of max Σ P_i s.t. Σ P_i ≤ cap, P_i ≤ P_accept,i. Zero kW wasted on tapering cars. |
| Charge target | **Dynamic 80% cap** while cars are waiting (never below the SOC the driver's trip needs); released when the queue is empty | The last 20% runs at ~55% average power. Past 80%, minutes spent on one car buy far less range than the same minutes spent on the next car. |
| Who's next | Pooled virtual queue, freed stall takes the next car | Same pooling result as the office case. |

## Results (80 random busy days, mean ± 95% CI)
| Policy | Avg wait (min) | Max wait (min) | Time at hub (min) | Final SOC | Trip need met |
|---|---|---|---|---|---|
| Today: equal split, charge to request | 47.7 ± 7.6 | 129.5 | 112.6 | 90% | 100% |
| Water-filling only | 30.1 ± 5.3 | 95.1 | 89.5 | 90% | 100% |
| Dynamic 80% cap only | 12.5 ± 2.4 | 56.8 | 67.3 | 84% | 100% |
| **QueuePilot-EV (both)** | **11.9 ± 2.3** | **55.5** | **65.6** | 84% | **100%** |

Ablation (honest): water-filling alone gives −37% wait. The dynamic cap gives most of the rest. Together they cut wait by 75% and time at the hub from 1 h 53 min to 1 h 6 min.
Trade-off, stated plainly: average final charge falls from 90% to 84% during busy periods, but every car still gets at least the charge its trip needs, and drivers who arrive when the hub is empty still charge to 100%.

## How the paper fits (Yu & Wang, PNAS 2024)
- **Physics structure:** the SOC ODE and the power conservation constraint above.
- **What physics misses → learned residual (next step):** real acceptance curves vary with battery temperature, age and chemistry. The hybrid approach learns a correction to P_accept(SOC) from charger logs, constrained to [0, P_accept], so it can never request more power than the battery's safe limit. This is §3A residual modelling with a physical constraint, like our office forecaster.
- **Heat derating** is already a parameter (`temp`): on a hot day each stall drops to 60% power and the results recompute.

## Why judges should care (beyond a toy)
- Real and growing: EV adoption and highway charging corridors in India; chargers and grid connections are expensive, so **throughput per kW is the business metric**.
- No new hardware: it's a software policy on the existing charger controller (OCPP smart-charging profiles already allow per-stall power limits).
- Same QueuePilot engine family: arrivals, servers, physics-governed service → forecast, plan, route.

## Mentor Q&A
- **"Isn't the 80% cap unfair to people who want 100%?"** Only while cars are waiting, never below trip need, and fully released when the hub is free. The alternative is the next car waiting 36 more minutes.
- **"Why water-filling?"** It's the exact solution of maximising delivered power under a shared cap with per-car upper limits; it's the same algorithm used for power allocation in wireless channels.
- **"Is the charging curve realistic?"** CC-CV with a taper above ~80% is the standard Li-ion protocol; the exact shape varies by car. That variation is precisely what the learned residual is for.
- **"What if every car needs 100%?"** Then the cap never binds (need ≥ cap → target = need) and QueuePilot falls back to water-filling only, still −37%.

Run it: `python -m engine.ev`  ·  API: `GET /ev?runs=80&temp=1.0&avg_gap=18`
