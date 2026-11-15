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
