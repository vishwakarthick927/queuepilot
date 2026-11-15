# QueuePilot Design — BUILD SPEC (v7, 15 Nov 10:20, MAIN). This is the plan of record.

Supersedes the scope of docs/CROWD.md (its story, facts list and Q&A still apply; the live control-room screen is now a stretch goal, not the MVP). Built to satisfy the judges' constraints in docs/CONSTRAINTS.md.

## What we are building (one sentence)
**An AI design service for architects: give it a floor plan, it recommends WHERE to put the fire exits so the building needs FEWER of them and still empties in time, even when people panic.** Decisions are made before the building exists, not during the emergency.

Pitch: "Every stampede starts as a queue that lost control. The cheapest place to fix it is on the drawing board. QueuePilot tells the architect where the exits must go."
Still QueuePilot: an evacuation is a network of queues at doors and stairs; we forecast those queues and design the building so they never lose control.

## The model: PG-GNN (physics-guided graph neural network) — judges' constraint 2
A building is a graph: **nodes** = rooms, corridor segments, stairs, exits; **edges** = doors and passages (width, length).

Every time step (e.g. 2 s), for every edge i→j:
1. **Physics (hard-coded, never learned):**
   - conservation: `people_i(next) = people_i + flow in − flow out`
   - door law: `flow ≤ width × max flow per metre × dt`
   - room law: a node cannot hold more than its area × max density; nobody goes below zero
2. **Learned by the GNN (only what physics does not know), all bounded:**
   - `efficiency_ij ∈ [0,1]` (sigmoid): how much of the door's textbook capacity is really used. Falls when people push, when flows merge, when the door is unfamiliar.
   - `share_ij` (softmax over a node's outgoing edges, sums to 1): which way people actually go: toward the exit they know, following others, not the nearest one.
3. `flow_ij = min(people_i × share_ij, capacity_ij × efficiency_ij, free space in j)`. Because shares sum to 1 and efficiency ≤ 1, **the network cannot create or lose a person: conservation holds by construction.**

GNN = message passing written by hand in PyTorch (no extra library, every line explainable): node features (people, area, kind, distance to each open exit, smoke/fire flag), edge features (width, length, familiarity of the exit it leads to); 3 rounds, hidden size 32; two small heads (efficiency, share logits). Trained by rolling the physics forward and backpropagating through it (differentiable physics), as in research/flood/water.py.

Why a GNN (answer for judges): a floor plan is a graph, not an image; a GNN works on ANY plan of any size, so one trained model scores a building it has never seen, in milliseconds. That is what makes it a design tool.

Three models, same data, same test (as in the flood twin):
- **Physics only**: efficiency = 1, everyone takes the shortest path (the textbook).
- **GNN only**: same message passing, predicts the change in people directly, no physics.
- **PG-GNN (ours)**.

Paper (Yu & Wang, PNAS 2024): §3A residual/hybrid model with constraints = our bounded learned terms; §3B mentions graph neural operators (we do NOT claim an operator, we claim a physics-constrained message-passing net); §4A generalisation = tested on floor plans never seen in training; §4E the learned terms have meaning (door efficiency, exit preference). Gap we fill: the paper stops at forecasting; we use the forecaster to make a design decision.

## Where the training data comes from (say this plainly to judges)
A detailed evacuation simulator we wrote (MAIN, `engine/evac.py`, numpy): the same graph, but with hidden behaviour the PG-GNN is never told: panic, exit familiarity ("leave the way you came in"), herding, doors that jam under pressure, fire closing edges over time. Thousands of random floor plans × exit layouts × fire starts. All results are **simulated** and labelled so. Real-data anchor for the method stays the bank result (learned 0.15 vs measured 0.156).

## How the recommendation is made
1. Architect's plan → graph with **candidate exit positions** (every place an exit could go).
2. **PG-GNN screens every layout** of k exits (hundreds to thousands) under every fire start, with panic on, including "the fire blocks any one exit". Score = worst-case clearance time.
3. **Top 5 are re-checked in the detailed simulator** (AI proposes, simulator verifies).
4. Output: the **fewest exits that pass the safe limit**, where they go, how wide; a value score per candidate position; the curve "number of exits → worst-case clearance"; comparison with a rule-of-thumb layout (evenly spaced); floor area freed.
5. Graph theory checks (Track 3): **max-flow** gives the best clearance any plan could reach (a bound); **min-cut** names the door or stair to widen.
Rule we never break: never below the building-code minimum (at least 2 exits, max travel distance, as parameters). We optimise placement and width and prove it by simulation; the fire authority approves.

## The MVP screen: "Design Studio" (new default page "/")
1. **Centre: the floor plan.** Rooms, corridors, candidate exit positions as markers sized by their value score. Chosen exits highlighted.
2. **Left: the brief.** Occupancy, safe limit, panic level slider, exits slider (2…N).
3. **Right: the verdict.** Fewest exits that pass; worst-case clearance; exits saved vs rule of thumb; m² freed; the bottleneck to widen (min-cut).
4. **Bottom: the curve** "exits → worst-case clearance" with the safe limit line, ours vs rule of thumb.
5. **Play:** evacuation animation on the plan, **rule-of-thumb layout vs ours, side by side, under panic with a fire**. This is the demo moment.
6. **Model drawer:** the plan as a graph; three-model accuracy on unseen plans; "people created or lost": GNN only vs ours (0).
Look: one dark studio theme, one accent, real units, tabular digits, no emoji, no stock gradients, one screen at 1440×900, readable from 4 m, loading/empty/error states. Every number read from a results JSON; every simulated number says "simulated".

Demo order (3 min): problem → load plan → rule-of-thumb layout fails under panic (animation) → press Recommend → fewer exits, passes → side by side → model drawer (unseen plans, conservation) → "never below code" line.

## Numbers we show (all from JSON, mean ± 95% CI where it applies)
| Number | Produced by |
|---|---|
| Exits needed: rule of thumb vs ours, same safe limit (hero) | MAIN design.json |
| Worst-case clearance time, both layouts, calm vs panic ("cost of panic") | MAIN design.json |
| Floor area freed (m², with the stated m² per exit core) | MAIN design.json |
| Clearance-time error on **unseen floor plans**: physics / GNN only / PG-GNN | WIN results.json |
| People created or lost per run: GNN only vs PG-GNN (0 by design) | WIN results.json |
| Does PG-GNN pick the truly best layout? top-1 / top-5 agreement with the detailed simulator | WIN recommend + MAIN truth ranking |
| Speed: layouts scored per second, PG-GNN vs detailed simulator | WIN results.json |
If a number is weak we show it and say why.

## Who builds what
| ID | Task | Owner |
|---|---|---|
| M1 | `engine/plans.py`: random floor-plan generator → graph; the demo plan; `data/design/demo_plan.json`. **Push first.** | MAIN |
| M2 | `engine/evac.py`: detailed evacuation simulator (panic, familiarity, herding, door jam, fire closes edges). Tests. | MAIN |
| M3 | `python -m engine.design_data` → training set (`data/design/train.npz`, gitignored; small `sample.npz` committed). WIN runs it locally (numpy only). | MAIN |
| M4 | `engine/design.py`: brute-force truth ranking of layouts for the demo plan, rule-of-thumb layout, max-flow bound, min-cut, code-minimum check → `data/design/design.json` | MAIN |
| M5 | `verify` entry point: re-check a list of layouts in the detailed simulator (WIN calls it after screening) | MAIN |
| W1 | `research/design/pggnn.py`: physics / GNN only / PG-GNN, train on M3, test on unseen plans → `results.json` | WIN |
| W2 | `research/design/recommend.py`: screen all layouts for the demo plan with PG-GNN, value score per candidate, call M5 on top 5 → `recommend.json` (+ weights JSON if the page runs the model live) | WIN |
| W3 | `frontend/src/design/`: Design Studio page per the spec above (build against demo_plan.json + stub JSON first) | WIN |
| W4 | Side-by-side evacuation animation + model drawer + polish | WIN |
| V1 | `docs/FACTS.md`: stampede facts, RSET < ASET, National Building Code exit rules, "people leave the way they came in", "pushing slows a door", each with a source link | Member 3 |
Superseded: C1–C6, W-C1–W-C5 (grid/CNN crowd twin). WIN: whatever you already wrote in research/crowd/ for the port, reuse the training loop.

## Contract (MAIN posts exact keys with M1; no renames after that without a MESSAGE)
**Plan graph** (`demo_plan.json`, and each plan in the dataset):
`{id, name, safe_limit_s, dt_s, max_density, flow_per_m_s,
  nodes: [{id, kind: "room"|"corridor"|"stair"|"exit", x, y, area_m2, people0}],
  edges: [{a, b, width_m, length_m}],
  candidates: [{id, node, attach_to, width_m, familiarity}],   # possible exits; attach_to = the node it would open from
  main_entrance: candidate id,
  fires: [{id, start_node, close: [{edge, step}]}]}`
**Training set** (`train.npz`, one row per run): `plan_index, exits (bitmask over candidates), fire, panic, people[step][node], flow[step][edge], clearance_step`; plans in `plans.json` beside it.
**MAIN → page** (`design.json`): `layouts [{exits, clearance_s, worst_case_s, worst_fire, passes}]`, `chosen`, `rule_of_thumb`, `curve [{n_exits, ours_s, rule_s}]`, `bound_maxflow_s`, `min_cut [edge]`, `area_freed_m2`, `cost_of_panic {calm_s, panic_s}`, `frames {chosen|rule_of_thumb: people[step][node]}` for the animation.
**WIN → page** (`results.json`, `recommend.json`): `models {physics|gnn|pggnn: {clearance_err_s, ci95, people_error}}`, `agreement {top1, top5}`, `speed {pggnn_per_s, simulator_per_s}`, `candidate_value [{id, score}]`, `screened`, `top5 [{exits, predicted_s, verified_s}]`.

## Checkpoints (T0 = 10:20; the user sets the hard cut-off)
- T0 + 0:40 — MAIN: M1 + demo plan pushed, simulator running. WIN: page skeleton renders the demo plan; model file scaffolded against the contract.
- T0 + 1:30 — MAIN: M3 dataset script + sample pushed. WIN: physics-only model matches MAIN's simulator on a calm run (sanity test).
- T0 + 3:00 — WIN: PG-GNN trained, results.json. MAIN: design.json with chosen vs rule of thumb + frames.
- T0 + 4:00 — Full demo order runs end to end. **Feature freeze.**
- **Fallback (decide at T0 + 3:00, not later):** if PG-GNN is not trained, the page ships with MAIN's simulator-ranked recommendation (still a working design tool) and PG-GNN is shown with whatever honest numbers exist. Flood twin stays at /?view=flood as the last resort.
- Before the pitch: record a screen video of the demo.

## Q&A additions (rest in docs/CROWD.md)
| Question | Answer |
|---|---|
| Why PG-GNN, not a CNN or LSTM? | A floor plan is a graph. A GNN runs on any plan of any size; physics inside it guarantees nobody appears or vanishes. |
| Where is the data from? | Our own detailed evacuation simulator with hidden panic behaviour. Simulated, and we say so. Next step: fit to fire-drill data. |
| Fewer exits sounds unsafe. | We never go below the code minimum. We show that well-placed exits beat more exits in the wrong place, and we test with panic and with any one exit lost. |
| Why trust the AI's pick? | We don't have to: the top 5 are re-checked in the detailed simulator, and max-flow gives the theoretical best to compare with. |
| What does the architect get? | Exit positions and widths, the worst-case clearance time, the bottleneck to widen, and the floor area saved. |
