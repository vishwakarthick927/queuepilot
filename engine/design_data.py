"""
Training data for the PG-GNN (task M3): many random floor plans x random exit layouts x fires x panic levels,
each run through the detailed simulator (engine/evac.py).

Run from repo root:  python -m engine.design_data                 (80 plans x 20 runs -> data/design/train.npz)
                     python -m engine.design_data 20 5 sample     (small file that is committed)

Files written to data/design/:
  <name>_plans.json   list of plan graphs (same keys as demo_plan.json)
  <name>.npz          one row per run, arrays padded with zeros to the largest plan:
      plan_index[R]            which plan
      is_test[R]               1 if the plan is held out (never use it for training): the last 20% of plans
      exits[R, C]              1 if that candidate is built
      fire[R], lost_exit[R]    fire id / blocked candidate id, -1 if none
      panic[R]                 0..1
      steps[R]                 number of valid steps in this run
      clearance_step[R]        -1 if the building did not clear in 300 steps
      people[R, T, N]          people in each node AFTER each step (float32)
      flow[R, T, E]            net people moving a->b on each edge in each step (float32)
      evacuated[R, T]          cumulative people out
"""
import json
import random
import sys
from pathlib import Path

import numpy as np

from engine import evac, plans

OUT = Path(__file__).parent.parent / "data" / "design"


def random_run(plan, rng):
    """One random situation for a plan: a layout (main entrance + 1..5 others), maybe a fire, a panic level."""
    main = plan["main_entrance"]
    others = [c["id"] for c in plan["candidates"] if c["id"] != main]
    exits = sorted([main] + rng.sample(others, rng.randint(1, min(5, len(others)))))
    fire = rng.choice(plan["fires"]) if rng.random() < 0.4 else None
    lost = rng.choice(exits) if (fire is None and rng.random() < 0.2) else None
    return exits, fire, lost, round(rng.random(), 2)


def generate(n_plans=80, runs_per_plan=20, name="train", seed=0):
    rng = random.Random(seed)
    all_plans = [plans.make_plan(5000 + seed * 1000 + i, n_candidates=rng.randint(6, 10)) for i in range(n_plans)]
    n_test = max(1, n_plans // 5)
    rows = []
    for pi, plan in enumerate(all_plans):
        for _ in range(runs_per_plan):
            exits, fire, lost, panic = random_run(plan, rng)
            r = evac.simulate(plan, exits, fire=fire, lost_exit=lost, panic=panic)
            rows.append((pi, exits, fire, lost, panic, r))
    R = len(rows)
    T = max(len(r["people"]) for *_, r in rows)
    N = max(len(p["nodes"]) for p in all_plans)
    E = max(len(p["edges"]) for p in all_plans)
    C = max(len(p["candidates"]) for p in all_plans)
    d = dict(plan_index=np.zeros(R, np.int32), is_test=np.zeros(R, np.int8), exits=np.zeros((R, C), np.int8),
             fire=np.full(R, -1, np.int32), lost_exit=np.full(R, -1, np.int32), panic=np.zeros(R, np.float32),
             steps=np.zeros(R, np.int32), clearance_step=np.full(R, -1, np.int32),
             people=np.zeros((R, T, N), np.float32), flow=np.zeros((R, T, E), np.float32), evacuated=np.zeros((R, T), np.float32))
    for i, (pi, exits, fire, lost, panic, r) in enumerate(rows):
        t, n, e = r["people"].shape[0], r["people"].shape[1], r["flow"].shape[1]
        d["plan_index"][i], d["is_test"][i], d["panic"][i], d["steps"][i] = pi, pi >= n_plans - n_test, panic, t
        d["exits"][i, exits] = 1
        d["fire"][i] = -1 if fire is None else fire["id"]
        d["lost_exit"][i] = -1 if lost is None else lost
        d["clearance_step"][i] = -1 if r["clearance_step"] is None else r["clearance_step"]
        d["people"][i, :t, :n], d["flow"][i, :t, :e], d["evacuated"][i, :t] = r["people"], r["flow"], r["evacuated"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}_plans.json").write_text(json.dumps(all_plans))
    np.savez_compressed(OUT / f"{name}.npz", **d)
    cleared = (d["clearance_step"] >= 0).mean()
    print(f"{name}: {R} runs on {n_plans} plans ({n_test} held out), T={T}, N={N}, E={E}, C={C}, cleared {cleared:.0%}")


if __name__ == "__main__":
    a = sys.argv[1:]
    generate(int(a[0]) if a else 80, int(a[1]) if len(a) > 1 else 20, a[2] if len(a) > 2 else "train")
