"""
Training data for the PG-GNN on VENUES (QueuePilot Live). Same idea as engine/design_data.py, with arrivals.
Each of the four venues is varied 40 times (crowd size, how badly the main gate is failing, which gates are open).
The riverbank venue ("ghat") is held out completely: it is the unseen-venue test.

Run from repo root:  python -m engine.crowd_data     (writes data/crowd/venue_train.npz + venue_plans.json)
Arrays, one row per run, zero-padded:  venue[R] (index into venue_plans.json), is_test[R], exits[R,C] (1 = open),
gate_eff[R,C] (share of design throughput; in deployment this comes from the gate-counter fit), panic[R],
arrivals[R,T,N] (people arriving at each node in each 5 s step), people[R,T,N] (after each step), flow[R,T,E],
through[R,T] (cumulative people through the gates). T = 480 steps of 5 s.
"""
import json
import random
from pathlib import Path

import numpy as np

from engine import crowd, evac

OUT = Path(__file__).parent.parent / "data" / "crowd"


def main(per_venue=40, seed=0):
    rng = random.Random(seed)
    vs = crowd.venues()
    rows = []
    for vi, (plan, sched) in enumerate(vs):
        for _ in range(per_venue):
            scale = rng.uniform(0.6, 1.3)
            arr = {s: [(n, p * scale) for n, p in lst] for s, lst in sched.items()}
            main_gate = plan["main_entrance"]
            eff = {main_gate: round(rng.uniform(0.3, 1.0), 2)}
            exits = [c["id"] for c in plan["candidates"] if c["open"] or rng.random() < 0.3]
            r = evac.simulate(plan, exits, panic=crowd.PANIC, max_steps=crowd.STEPS, arrivals=arr, gate_eff=eff)
            rows.append((vi, exits, eff, arr, r))
    R, T = len(rows), crowd.STEPS
    N = max(len(p["nodes"]) for p, _ in vs); E = max(len(p["edges"]) for p, _ in vs); C = max(len(p["candidates"]) for p, _ in vs)
    d = dict(venue=np.zeros(R, np.int32), is_test=np.zeros(R, np.int8), exits=np.zeros((R, C), np.int8), gate_eff=np.ones((R, C), np.float32),
             panic=np.full(R, crowd.PANIC, np.float32), arrivals=np.zeros((R, T, N), np.float32), people=np.zeros((R, T, N), np.float32),
             flow=np.zeros((R, T, E), np.float32), through=np.zeros((R, T), np.float32))
    for i, (vi, exits, eff, arr, r) in enumerate(rows):
        t, n, e = r["people"].shape[0], r["people"].shape[1], r["flow"].shape[1]
        d["venue"][i], d["is_test"][i] = vi, vs[vi][0]["id"] == "ghat"
        d["exits"][i, exits] = 1
        for c, v in eff.items():
            d["gate_eff"][i, c] = v
        for s, lst in arr.items():
            for node, ppl in lst:
                d["arrivals"][i, s, node] += ppl
        d["people"][i, :t, :n], d["flow"][i, :t, :e] = r["people"], r["flow"]
        d["through"][i, :t] = r["evacuated"]; d["through"][i, t:] = r["evacuated"][-1]
    np.savez_compressed(OUT / "venue_train.npz", **d)
    (OUT / "venue_plans.json").write_text(json.dumps([p for p, _ in vs]))
    print(f"venue_train: {R} runs on {len(vs)} venues, held-out venue = ghat ({int(d['is_test'].sum())} runs), people {d['people'].shape}")


if __name__ == "__main__":
    main()
