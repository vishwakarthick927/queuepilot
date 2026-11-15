"""
STUB data for the Design Studio page, in the BUILD.md "Contract" shapes, so the page can be built
before MAIN's design.json (M4) and our real results.json / recommend.json exist.
Every file written here is marked "stub": true and the page shows a STUB badge while it uses them.

    python -m research.design.make_stub
"""
import json

import numpy as np
import torch

from research.design.pggnn import Graph, ToyTruth, rollout, clearance_step
from research.design.toyplans import STUB_DIR, demo_plan

STEPS = 300


def clear_s(plan, mask, fire, panic):
    """Seconds until everyone is out, in the toy truth (STEPS x dt if never)."""
    g = Graph(plan, mask, fire, panic)
    with torch.no_grad():
        traj = rollout(ToyTruth(), g, torch.tensor(g.people0, dtype=torch.float32), 0, STEPS)
    return (clearance_step(traj, g) or STEPS) * plan["dt_s"], traj


def worst(plan, mask, panic=1.0):
    """Worst case over no fire + every fire: (seconds, which fire, people still inside at the end)."""
    cases = []
    for f in [None] + plan["fires"]:
        sec, traj = clear_s(plan, mask, f, panic)
        g_exit = np.array([n["kind"] == "exit" for n in plan["nodes"]])
        cases.append((sec, f["id"] if f else None, float(traj[-1].numpy()[~g_exit].sum())))
    return max(cases, key=lambda c: (c[0], c[2]))


def greedy(plan, n_max):
    """Main entrance first, then add whichever exit cuts the worst case most."""
    mask, out = 1, {}
    for n in range(2, n_max + 1):
        best = min((sum(worst(plan, mask | 1 << k)[::2]), k) for k in range(len(plan["candidates"])) if not mask >> k & 1)
        mask |= 1 << best[1]
        out[n] = mask
    return out


def even(plan, n):
    """Rule of thumb: main entrance + exits spread evenly along the building (by x)."""
    order = sorted(range(1, len(plan["candidates"])), key=lambda k: plan["nodes"][plan["candidates"][k]["node"]]["x"])
    pick = [order[int(round(i))] for i in np.linspace(0, len(order) - 1, n - 1)]
    return 1 | sum(1 << k for k in set(pick))


def main():
    plan = demo_plan()
    limit, n_max = plan["safe_limit_s"], 8
    ours = greedy(plan, n_max)
    layouts, curve = [], []
    for n in range(2, n_max + 1):
        (o, of, _), (r, _, _) = worst(plan, ours[n]), worst(plan, even(plan, n))
        curve.append({"n_exits": n, "ours_s": o, "rule_s": r})
        layouts.append({"exits": ours[n], "clearance_s": clear_s(plan, ours[n], None, 1.0)[0], "worst_case_s": o,
                        "worst_fire": of, "passes": o <= limit})
        print(f"{n} exits  ours {o:4d}s  rule of thumb {r:4d}s")
    n_ours = next((c["n_exits"] for c in curve if c["ours_s"] <= limit), n_max)
    n_rule = next((c["n_exits"] for c in curve if c["rule_s"] <= limit), n_max)
    chosen, rule = ours[n_ours], even(plan, n_rule)
    fire = plan["fires"][0]
    frames = {k: clear_s(plan, m, fire, 1.0)[1].numpy().round(1).tolist() for k, m in (("chosen", chosen), ("rule_of_thumb", rule))}
    hall_door = next(i for i, e in enumerate(plan["edges"]) if plan["nodes"][e["a"]].get("name") == "Hall")
    design = {"stub": True, "layouts": layouts, "chosen": chosen, "rule_of_thumb": rule, "curve": curve,
              "bound_maxflow_s": int(min(c["ours_s"] for c in curve) * 0.8), "min_cut": [hall_door],
              "area_freed_m2": (n_rule - n_ours) * 25, "m2_per_exit": 25,
              "cost_of_panic": {"calm_s": worst(plan, chosen, 0.0)[0], "panic_s": worst(plan, chosen, 1.0)[0]},
              "frames": frames, "frames_fire": fire["id"]}
    base = worst(plan, chosen)[0]
    value = []
    for k, c in enumerate(plan["candidates"]):
        on = chosen >> k & 1
        alt = worst(plan, chosen ^ 1 << k)[0]
        value.append({"id": c["id"], "score": round(float((alt - base) if on else (base - alt)), 1)})
    recommend = {"stub": True, "agreement": {"top1": 0.8, "top5": 1.0}, "candidate_value": value, "screened": 4096,
                 "top5": [{"exits": l["exits"], "predicted_s": l["worst_case_s"] - 6, "verified_s": l["worst_case_s"]}
                          for l in layouts[:5]]}
    st = json.loads((STUB_DIR.parents[3] / "research" / "design" / "results_selftest.json").read_text())
    results = {"stub": True, "models": st["models"], "speed": {"pggnn_per_s": st["speed"]["pggnn_per_s"], "simulator_per_s": 1.0}}
    for name, obj in (("design.json", design), ("recommend.json", recommend), ("results.json", results)):
        (STUB_DIR / name).write_text(json.dumps(obj))
    print("chosen", n_ours, "exits vs rule of thumb", n_rule, "| stub files in", STUB_DIR)


if __name__ == "__main__":
    main()
