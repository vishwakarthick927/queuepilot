# One engine, every perishable queue (docs for the pitch)

**Pitch line:** In many industries, the thing waiting in the queue is physically changing: it cools, it sets, it spoils. First-come-first-served ignores that. QueuePilot plugs in each industry's physics and serves whatever is losing money fastest. Same engine, new sector = new physics module, not a new product.

## How it works (engine/perishable.py)
- Each sector defines three things: how the job's physical state evolves while it waits, what the job is worth (₹) in that state, and how long it takes to serve.
- Every time a server frees up, QueuePilot computes for each waiting job: *₹ it will lose if it waits one more slot ÷ minutes it needs on the server*, and serves the largest. This is the classic **cμ rule** from queueing theory (optimal for linear waiting costs), extended with loss rates computed live from physics, including cliffs like a rejected load.
- Jobs already worthless go last, so they don't block jobs that can still be saved.
- Baseline: first come, first served. Both serve exactly the same jobs; only the order changes, and average wait is unchanged. **QueuePilot saves money with zero extra hardware, staff or wait.**

## Results (40 simulated days per row, ambient 30 °C unless stated)
| Sector | Physics | FCFS loss/day | QueuePilot loss/day | Loss cut | Rejected loads |
|---|---|---|---|---|---|
| Road paving (hot asphalt), 15 °C day | Newton cooling, reject < 125 °C | ₹14.5 lakh | ₹3.7 lakh | **−74%** | 12.1 → 3.1 |
| Ready-mix concrete pour | Cement setting time, halves per +10 °C | ₹7.1 lakh | ₹2.2 lakh | **−69%** | 18.5 → 5.8 |
| Milk chilling centre, 38 °C day | Bacteria doubling, price grades | ₹1.11 lakh | ₹0.55 lakh | **−51%** | 49.8 → 15.1 |
| Milk chilling centre, 30 °C | same | ₹34,000 | ₹20,700 | −39% | 4.5 → 2.6 |
| Sugarcane mill, 38 °C day | Sucrose inversion, exponential | ₹84,800 | ₹75,400 | −11% | none |

Plus the two earlier cases on the same idea of physics-aware queues:
| Office / admin counters | Pooled queue + skill matching | avg wait 7.1 → 5.0 min (−30%) |
| EV fast-charging hub | Battery CC-CV curve + shared grid cap | avg wait 47.7 → 11.9 min (−75%) |

## What the results honestly say
- **Biggest wins are where value falls off a cliff** (asphalt, concrete, milk grades): saving a load from rejection saves its full value. That's where the business case is strongest.
- **Sugarcane gains are small (−11%)** because sugar loss is smooth and roughly the same whatever the order. The real lever there is *reducing total waiting* (harvest and truck scheduling), which is the next module, not reordering. Say this if asked; it shows we understand the physics.
- Hot days hurt concrete and milk; for asphalt, cold and windy days are worst (it cools faster). The engine gets this right from the physics, no special cases.
- All parameters are realistic but illustrative assumptions (listed in each sector's docstring). Real deployment = calibrate them from site logs; that's the paper's learned-residual step.

## The startup angle
- **Customer:** ready-mix concrete companies, road contractors, dairy cooperatives, sugar mills. Each loses money every day on rejected or degraded loads.
- **Product:** a dispatch/queue brain on a phone or tablet at the site; trucks report temperature and batch time (many already have GPS and batch tickets).
- **Pricing:** per-site subscription, or a share of measured savings (e.g. 20% of ₹ saved). In our simulated concrete site, saving ~₹4.9 lakh/day means even a small share pays easily.
- **Moat:** a library of validated physics modules + learned corrections from each customer's data, which gets better with every site.
- **Expansion:** the same engine already covers EV charging and service counters. Next modules: PET tracers (radioactive decay), port berths (tide windows), cold-chain docks.

## Mentor Q&A
- **"Isn't this just priority scheduling?"** The rule is classic (cμ). What's new is computing each job's cost rate *from physics in real time*, including cliffs, across industries with one engine.
- **"Why doesn't wait time drop?"** Reordering doesn't change total work. It changes *who* waits, so the jobs about to be ruined go first. Money saved, nobody's average wait worse.
- **"Are your numbers real?"** Simulated with stated assumptions; the method is what we're proving. Calibration from real logs is step one with a pilot customer.

Run: `python -m engine.perishable` · API: `GET /sectors?runs=40&temp=30`
