"""
W2: screen every exit layout of the demo plan with the trained PG-GNN, then let the detailed
simulator re-check the best five ("AI proposes, simulator verifies", docs/BUILD.md).

For each layout (the main entrance is always kept, at least 2 exits = building-code minimum):
    worst case = the slowest of: no fire, every fire, and "the fire blocks any one exit"
Everything runs with panic on. A layout passes if its worst case is within the plan's safe limit.

Value of a candidate position = how many seconds it takes off the worst case, on average,
when it is added to a layout that does not have it yet.

    python -m research.design.recommend [--selftest]     # writes recommend.json
"""
import argparse
import json
import time
from itertools import combinations

import numpy as np
import torch

from research.design.pggnn import OUT, PGGNN, Graph, clearance_steps, rollout

STEPS = 300
BATCH = 256


def load_plan(selftest):
    """The demo plan: MAIN's data/design/demo_plan.json, or the stub one."""
    if selftest:
        from research.design.toyplans import demo_plan
        return demo_plan()
    return json.loads((OUT.parents[1] / "data" / "design" / "demo_plan.json").read_text())


def all_layouts(plan):
    """Every set of candidate exits that keeps the main entrance and has at least 2 exits."""
    k = len(plan["candidates"])
    main = next(i for i, c in enumerate(plan["candidates"]) if c["id"] == plan["main_entrance"])
    others = [i for i in range(k) if i != main]
    out = []
    for n in range(1, k):
        for pick in combinations(others, n):
            out.append(1 << main | sum(1 << i for i in pick))
    return out


def cases(plan, mask):
    """The situations a layout must survive: (exits actually usable, fire or None)."""
    out = [(mask, f) for f in [None] + plan["fires"]]
    bits = [i for i in range(len(plan["candidates"])) if mask >> i & 1]
    out += [(mask ^ 1 << i, None) for i in bits if len(bits) > 1]       # one exit lost
    return out


@torch.no_grad()
def screen(model, plan, layouts, panic=1.0):
    """Worst-case clearance (seconds) of every layout, scored in batches by the model."""
    jobs = [(li, m, f) for li, L in enumerate(layouts) for m, f in cases(plan, L)]
    worst = np.zeros(len(layouts))
    never = STEPS * plan["dt_s"]
    for s in range(0, len(jobs), BATCH):
        chunk = jobs[s:s + BATCH]
        b = Graph.batch([Graph(plan, m, f, panic) for _, m, f in chunk])
        traj = rollout(model, b, torch.tensor(b.people0, dtype=torch.float32), 0, STEPS)
        for (li, _, _), c in zip(chunk, clearance_steps(traj, b)):
            worst[li] = max(worst[li], never if c is None else c * plan["dt_s"])
    return worst


def candidate_value(plan, layouts, worst):
    """Average seconds saved when a candidate is added to a layout that lacks it."""
    index = {L: i for i, L in enumerate(layouts)}
    out = []
    for k, c in enumerate(plan["candidates"]):
        gains = [worst[i] - worst[index[L | 1 << k]] for i, L in enumerate(layouts) if not L >> k & 1 and (L | 1 << k) in index]
        out.append({"id": c["id"], "score": round(float(np.mean(gains)), 1) if gains else 0.0})
    return out


def verify(plan, top):
    """Re-check layouts in MAIN's detailed simulator (M5). None until engine.design lands."""
    try:
        from engine.design import verify as main_verify       # MAIN's entry point (name per BUILD.md M5)
    except ImportError:
        return [None] * len(top)
    return [r["worst_case_s"] if isinstance(r, dict) else r for r in main_verify(plan, top)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    plan = load_plan(a.selftest)
    model = PGGNN()
    model.load_state_dict(torch.load(OUT / ("pggnn_selftest.pt" if a.selftest else "pggnn.pt")))
    layouts = all_layouts(plan)
    t = time.perf_counter()
    worst = screen(model, plan, layouts)
    secs = time.perf_counter() - t
    n_of = np.array([bin(L).count("1") for L in layouts])
    passing = worst <= plan["safe_limit_s"]
    fewest = int(n_of[passing].min()) if passing.any() else None
    pool = np.nonzero(n_of == fewest)[0] if fewest else np.arange(len(layouts))
    top = [layouts[i] for i in pool[np.argsort(worst[pool])][:5]]
    checked = verify(plan, top)
    res = {"screened": len(layouts), "screen_seconds": round(secs, 1), "fewest_exits": fewest,
           "candidate_value": candidate_value(plan, layouts, worst),
           "top5": [{"exits": L, "predicted_s": float(worst[layouts.index(L)]), "verified_s": v} for L, v in zip(top, checked)],
           "curve": [{"n_exits": int(n), "best_s": float(worst[n_of == n].min())} for n in sorted(set(n_of))],
           "setup": {"panic": 1.0, "steps": STEPS, "cases": "no fire + every fire + any one exit lost",
                     "source": "SELFTEST" if a.selftest else "MAIN demo plan"}}
    print(json.dumps({k: v for k, v in res.items() if k != "candidate_value"}, indent=1))
    (OUT / ("recommend_selftest.json" if a.selftest else "recommend.json")).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
