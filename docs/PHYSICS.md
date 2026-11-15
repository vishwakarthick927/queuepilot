# Lagrangian and Hamiltonian mechanics: do they belong in QueuePilot? (MAIN, 15 Nov)

Short answer: **Hamiltonian dynamics, no. Two related ideas, yes**: the Hamilton–Jacobi (eikonal) equation for routing, and Lagrangian relaxation (Lagrange multipliers) for the exit optimisation.

## 1. Hamiltonian / Lagrangian equations of motion: NOT a fit
- They describe **conservative** systems: total energy stays constant (a pendulum, a planet).
- A crowd is the opposite: people are self-driven and lose energy all the time (they stop, push, slow down in a dense space). Smoke spreads and never "un-spreads". Both are **dissipative**.
- Hamiltonian neural networks build energy conservation into the model. Used here, they would force a crowd to keep its "energy", which is physically wrong.
- Line for judges: "Physics-guided means using the RIGHT physics. A crowd conserves people, not energy. So we hard-code conservation of people (the continuity equation) and of smoke, not a Hamiltonian."

## 2. Hamilton–Jacobi (eikonal) equation: YES, already inside the model
- How fast can a person reach the nearest exit from any point? The time field T(x) obeys the eikonal equation `|∇T(x)| = 1 / v(x)`, T = 0 at the exits. It is a Hamilton–Jacobi equation.
- Hughes' continuum crowd model (2002) uses exactly this: people walk down the gradient of T.
- Our shortest-path routing (Dijkstra on the floor-plan graph, engine/evac.py) is the discrete solution of this equation on the graph.
- Possible upgrade (small, ~30 lines): make the edge cost travel TIME with crowd-dependent speed (`length / v(ρ)`) instead of length, re-solved every few steps. Then routing reacts to crowding, which is Hughes' model on a graph.

## 3. Lagrange multipliers / Lagrangian relaxation: YES, for the design question
- The architect's question is a constrained optimisation: minimise the number of exits, subject to "everyone out within the safe limit" in every fire scenario.
- Lagrangian relaxation turns the hard constraint into a penalty with a multiplier: `L = exits + λ · (clearance time − limit)`. Raising λ means "safety matters more"; λ is the price of one second of evacuation time in exits.
- Today we search every layout exactly (fine for 8–10 exit positions). For a large building with 30+ positions that is too many layouts; Lagrangian relaxation with the PG-GNN as the fast scorer is the standard way to scale.
- Max-flow / min-cut (already in engine/design.py) is itself a Lagrangian-duality result (LP duality): the min-cut is the dual of the max-flow.

## Recommendation
1. Say it on stage in one sentence (section 1 line). It shows judgement, which is worth more than forcing an equation in.
2. Optional build, if time allows: (a) eikonal routing with crowd-dependent travel time; (b) a Lagrangian-relaxation exit search shown as "how this scales to a 40-storey tower". Neither changes today's results.
3. Do not add Hamiltonian neural networks.

Citations to verify before quoting: Hughes, "A continuum theory for the flow of pedestrians", Transportation Research B, 2002; Greydanus et al., "Hamiltonian Neural Networks", NeurIPS 2019.

---

# TESTED (15 Nov, `python -m engine.mechanics` → data/design/mechanics.json, mechanics.png). All simulated.
Same test for every model: 320 evacuations on 16 floor plans never used for fitting; truth = engine/evac.py. Each model's constants were fitted on ~100 training runs first (grid search), so each gets its best shot.

| Model | Error in time to get everyone out | What goes wrong / right, and why |
|---|---|---|
| Hamiltonian + friction | 112.5 ± 14.6 s | Friction stops the sloshing but makes the crowd creep: only 82% of buildings ever empty. Rooms still dip to −2.3 people; 10% of movement is away from the exits. There is no door limit in the equations, so no setting fits both the fast start and the slow tail. |
| Hamiltonian / Lagrangian (energy conserved) | 81.5 ± 16.1 s | Energy cannot leave, so the crowd "sloshes": **42.5% of all movement is AWAY from the exits**, and momentum carries rooms to **−90.8 people** (impossible). Euler–Lagrange gives the same equations, so this covers both. |
| GNN only (no physics) | 51.7 ± 6.9 s | Learns from data but nothing stops it inventing people: 328 created or lost per run (WIN's result). |
| Least action: fastest path for everyone (physics only) | 22.1 ± 2.4 s | The Lagrangian idea that DOES fit (path of least travel time = eikonal / Hamilton–Jacobi). Never breaks a law, but assumes people are rational: misses the rush to the known exit and door jams. |
| **PG-GNN (ours)** | **4.7 ± 0.7 s** | Keeps the least-action routing and conservation of people as hard physics; learns only exit choice and door efficiency. 0 people created or lost. (WIN's result, same 320 runs.) |

Fitted constants: Hamiltonian g = 0.0002, k = 1.0; damped g = 0.002, k = 3.0, γ = 0.05 (best in the grids in engine/mechanics.py; the frictionless g sits at the grid's lower edge, i.e. it wants to be as slow as possible).

**Lagrange multipliers on the exit search (the part that helps):** minimise `exits + λ × (seconds over the limit)/10` by local search with rising λ, against trying every layout.

| Building | Every layout tried | Lagrange search | Same answer? |
|---|---|---|---|
| Community hall | 511 layouts | 31 | yes, 3 exits, 146 s |
| School wing | 127 | 38 | yes, 3 exits, 148 s |
| Office floor | 127 | 23 | yes, 3 exits, 90 s |
| Apartment floor | 127 | 18 | yes, 2 exits, 64 s |
| Cinema level | 127 | 13 | yes, 2 exits, 102 s |

Same answer on all five with 3–16× fewer layouts simulated. Honest limit: five small buildings; a local search can miss the best layout on a harder one, which is why the result is re-checked in the simulator.

**What to say:** "We tested it. Hamiltonian and Lagrangian equations of motion conserve energy; a crowd does not, so that model sends 42% of the movement away from the exits and predicts negative people. The parts of Lagrange's and Hamilton's work that fit are least-action routing, which is already inside our physics, and Lagrange multipliers, which find the same exits with up to 16 times fewer simulations. The PG-GNN on top of the right physics has the lowest error, 4.7 seconds."

