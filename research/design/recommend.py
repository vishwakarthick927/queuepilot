"""
W2: screen every exit layout of the demo plan with the trained PG-GNN, then let MAIN's detailed
simulator re-check the best five ("AI proposes, simulator verifies", docs/BUILD.md).

For each layout (the main entrance is always built, at least 2 exits = building-code minimum) the
worst case is the slowest of MAIN's scenarios: no fire, each corridor fire, and a fire blocking each
built exit. Everything is judged with panic 0.8, like engine/design.py. A layout passes if its worst
case is within the plan's safe limit and the code check (engine.design.travel_ok) holds.

Value of a candidate position = seconds it takes off the worst case, on average, when it is added to
a layout that does not have it yet.

Agreement = does the screen pick the simulator's best layout (top 1), or have it in its top 5?
Checked against the truth ranking MAIN wrote in data/design/design.json, for PG-GNN and physics only.

    python -m research.design.recommend          # writes research/design/recommend.json
"""
import json
import time
from itertools import combinations

import numpy as np
import torch

from engine.design import DESIGN_PANIC, scenarios, travel_ok, verify
from research.design.pggnn import DATA, OUT, PGGNN, Graph, PhysicsOnly, clearance_steps, rollout

STEPS = 300
BATCH = 512


def all_layouts(plan):
    """Every set of candidate exits that keeps the main entrance and has at least 2 exits."""
    main = plan["main_entrance"]
    others = [c["id"] for c in plan["candidates"] if c["id"] != main]
    return [sorted((main,) + pick) for n in range(1, len(others) + 1) for pick in combinations(others, n)]


@torch.no_grad()
def screen(model, plan, layouts, panic=DESIGN_PANIC):
    """Worst-case clearance (seconds, inf = somebody never got out) of every layout, in batches."""
    jobs = [(li, L, fire, lost) for li, L in enumerate(layouts) for _, fire, lost in scenarios(plan, L)]
    worst = np.zeros(len(layouts))
    for s in range(0, len(jobs), BATCH):
        chunk = jobs[s:s + BATCH]
        b = Graph.batch([Graph(plan, L, fire, panic, lost) for _, L, fire, lost in chunk])
        traj = rollout(model, b, torch.tensor(b.people0, dtype=torch.float32), 0, STEPS)
        for (li, *_), c in zip(chunk, clearance_steps(traj, b)):
            worst[li] = max(worst[li], np.inf if c is None else c * plan["dt_s"])
    return worst


def ranked(layouts, worst, n):
    """Layouts with n exits, best first."""
    idx = [i for i, L in enumerate(layouts) if len(L) == n]
    return [layouts[i] for i in sorted(idx, key=lambda i: worst[i])]


def agreement(layouts, worst, truth):
    """Top-1 / top-5 agreement with the simulator's best layout, at every exit count the truth covers."""
    hits1, hits5, counts = 0, 0, sorted({len(t["exits"]) for t in truth})
    for n in counts:
        best = min((t for t in truth if len(t["exits"]) == n), key=lambda t: t["worst_case_s"] or np.inf)["exits"]
        mine = ranked(layouts, worst, n)
        hits1 += mine[0] == best
        hits5 += best in mine[:5]
    return {"top1": round(hits1 / len(counts), 2), "top5": round(hits5 / len(counts), 2), "exit_counts": counts}


def candidate_value(plan, layouts, worst):
    """Average seconds saved when a candidate is added to a layout that lacks it (capped at the run length)."""
    w = np.minimum(worst, STEPS * plan["dt_s"])
    index = {tuple(L): i for i, L in enumerate(layouts)}
    out = []
    for c in plan["candidates"]:
        gains = [w[i] - w[index[tuple(sorted(L + [c["id"]]))]] for i, L in enumerate(layouts)
                 if c["id"] not in L and tuple(sorted(L + [c["id"]])) in index]
        out.append({"id": c["id"], "score": round(float(np.mean(gains)), 1) if gains else 0.0})
    return out


def main():
    plan = json.loads((DATA / "demo_plan.json").read_text())
    truth = json.loads((DATA / "design.json").read_text())["by_panic"][str(DESIGN_PANIC)]["layouts"]
    model = PGGNN()
    model.load_state_dict(torch.load(OUT / "pggnn.pt"))
    layouts = all_layouts(plan)
    t = time.perf_counter()
    worst = screen(model, plan, layouts)
    secs = time.perf_counter() - t
    worst_phys = screen(PhysicsOnly(), plan, layouts)
    ok = np.array([w <= plan["safe_limit_s"] and travel_ok(plan, L)[0] for L, w in zip(layouts, worst)])
    fewest = int(min(len(L) for L, k in zip(layouts, ok) if k)) if ok.any() else None
    top = ranked(layouts, worst, fewest)[:5] if fewest else []
    checked = verify(plan, top)                                  # MAIN's detailed simulator, M5
    res = {"screened": len(layouts), "scenarios_per_layout": "no fire + each fire + a fire blocking each exit",
           "screen_seconds": round(secs, 1), "fewest_exits": fewest,
           "candidate_value": candidate_value(plan, layouts, worst),
           "top5": [{"exits": L, "predicted_s": float(worst[layouts.index(L)]) if np.isfinite(worst[layouts.index(L)]) else None,
                     "verified_s": v["worst_case_s"], "verified_passes": v["passes"]} for L, v in zip(top, checked)],
           "agreement": agreement(layouts, worst, truth),
           "agreement_physics_only": agreement(layouts, worst_phys, truth),
           "setup": {"panic": DESIGN_PANIC, "steps": STEPS, "plan": plan["id"], "simulated": True}}
    print(json.dumps({k: v for k, v in res.items() if k != "candidate_value"}, indent=1))
    (OUT / "recommend.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
