"""
READY-MIX CONCRETE: a queue where the thing waiting is going hard.
A truck is loaded at the batching plant, drives to the site and waits for the pump. Concrete must be placed before
it starts to set. If a truck waits too long, the whole load is rejected and dumped.

Physics and rules:
  time limit        concrete must be discharged within 90 minutes of batching at about 30 C (the industry's 90-minute rule)
  heat              setting is a chemical reaction; it runs about twice as fast for every +10 C:
                    limit(T) = 90 min * 2^(-(T - 30) / 10)                    (Q10 rule; an assumption for the demo)
  remaining life    slack = limit(T) - (now - batch time)
  queue             dn/dt = trucks arriving - trucks pumped                    (conservation)
What the plan on paper does NOT know: the pump is slower today than its nameplate rate (long hose, congested pour).
Three ways to run the same pour, same trucks, same traffic:
  today         the plant sends a truck every `plan` minutes (set for the nameplate pump), first come first served
  smart queue   same dispatch; at the site the truck with the LEAST slack that can still be saved goes first
  QueuePilot    smart queue + the plant is paced by the pump's real rate, LEARNED from the unloads seen so far
                (send the next truck when the queue it would join still leaves it enough slack)

Run from repo root:  python -m engine.concrete      (writes data/concrete/concrete.json)
Simulated. Prices, travel times and pump rates are stated assumptions.
"""
import json
import random
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent.parent / "data" / "concrete"
TRUCKS = 40                    # a 240 m3 slab pour
LOAD_M3 = 6.0
PRICE_PER_M3 = 6500.0          # rupees (assumption)
PUMP_PLAN_MIN = 9.0            # nameplate: minutes to pump one truck
PUMP_REAL_MIN = 12.5           # hidden: what it really takes today
TRAVEL_MEAN, TRAVEL_SD = 38.0, 9.0
SAFETY_MIN = 8.0               # QueuePilot keeps this much slack in hand when pacing the plant


def limit_min(temp_c):
    return 90.0 * 2 ** (-(temp_c - 30.0) / 10.0)


def run(policy, temp_c, seed):
    rng = random.Random(seed)
    travel = [max(15.0, rng.gauss(TRAVEL_MEAN, TRAVEL_SD)) for _ in range(TRUCKS)]
    pump = [max(6.0, rng.gauss(PUMP_REAL_MIN, 1.5)) for _ in range(TRUCKS)]
    L = limit_min(temp_c)
    trucks, yard, seen = [], [], []           # yard = trucks waiting at the site; seen = unload times observed so far
    t, pump_free, next_batch, sent, placed = 0.0, 0.0, 0.0, 0, 0
    on_road = []
    while placed + sum(tr.get("rejected", False) for tr in trucks) < TRUCKS:
        # 1. the plant decides whether to batch the next truck now
        if sent < TRUCKS and t >= next_batch:
            go = True
            if policy == "queuepilot":
                rate = float(np.mean(seen[-6:])) if len(seen) >= 2 else PUMP_PLAN_MIN       # learned pump time per truck
                ahead = len(yard) + len(on_road) + (1 if pump_free > t else 0)
                wait_at_site = max(0.0, pump_free - t - TRAVEL_MEAN) + max(0, ahead - 1) * rate
                go = TRAVEL_MEAN + wait_at_site + SAFETY_MIN <= L and ahead * rate <= TRAVEL_MEAN + rate
            if go:
                tr = dict(id=sent, batch=t, arrive=t + travel[sent], limit=t + L)
                trucks.append(tr); on_road.append(tr); sent += 1
                next_batch = t + PUMP_PLAN_MIN if policy != "queuepilot" else t + 1.0
            else:
                next_batch = t + 1.0
        # 2. trucks arrive
        for tr in [x for x in on_road if x["arrive"] <= t]:
            on_road.remove(tr); yard.append(tr)
        # 3. loads that have passed their limit while waiting are rejected
        for tr in [x for x in yard if x["limit"] <= t]:
            yard.remove(tr); tr["rejected"], tr["start"] = True, None
        # 4. the pump takes the next truck
        if pump_free <= t and yard:
            tr = min(yard, key=lambda x: x["arrive"]) if policy == "today" else min(yard, key=lambda x: x["limit"])
            yard.remove(tr)
            tr["start"], tr["end"], tr["rejected"] = t, t + pump[tr["id"]], False
            pump_free = tr["end"]; seen.append(pump[tr["id"]]); placed += 1
        t += 0.5
        if t > 3000:
            break
    rejected = [tr for tr in trucks if tr["rejected"]]
    ok = [tr for tr in trucks if not tr["rejected"]]
    return dict(trucks=trucks, rejected=len(rejected), lost_rs=len(rejected) * LOAD_M3 * PRICE_PER_M3,
                age_at_pour=float(np.mean([tr["start"] - tr["batch"] for tr in ok])) if ok else None,
                closest_call=float(min(tr["limit"] - tr["start"] for tr in ok)) if ok else None,
                finish=float(max(tr["end"] for tr in ok)) if ok else None, limit_min=L)


def main(seeds=30):
    OUT.mkdir(parents=True, exist_ok=True)
    policies = ["today", "smart_queue", "queuepilot"]
    temps = [25, 30, 38]
    table = {}
    for T in temps:
        table[str(T)] = {}
        for p in policies:
            rs = [run(p, T, s) for s in range(seeds)]
            rej = np.array([r["rejected"] for r in rs])
            table[str(T)][p] = dict(rejected_mean=round(float(rej.mean()), 1), rejected_ci95=round(float(1.96 * rej.std() / np.sqrt(seeds)), 1),
                                    lost_rs_mean=round(float(np.mean([r["lost_rs"] for r in rs]))),
                                    age_at_pour_min=round(float(np.mean([r["age_at_pour"] for r in rs if r["age_at_pour"]])), 1),
                                    finish_min=round(float(np.mean([r["finish"] for r in rs if r["finish"]]))), seeds=seeds)
            print(T, "C", p, table[str(T)][p])
    demo = {}
    for T in temps:
        demo[str(T)] = {}
        for p in policies:
            r = run(p, T, 0)
            demo[str(T)][p] = dict(rejected=r["rejected"], lost_rs=r["lost_rs"], finish=round(r["finish"], 1), limit_min=round(r["limit_min"], 1),
                                   trucks=[dict(id=t["id"], batch=round(t["batch"], 1), arrive=round(t["arrive"], 1), limit=round(t["limit"], 1),
                                                start=None if t["start"] is None else round(t["start"], 1),
                                                end=None if t["rejected"] else round(t["end"], 1), rejected=t["rejected"]) for t in r["trucks"]])
    out = dict(simulated=True, trucks=TRUCKS, load_m3=LOAD_M3, price_per_m3=PRICE_PER_M3, pump_plan_min=PUMP_PLAN_MIN, pump_real_min=PUMP_REAL_MIN,
               travel_mean_min=TRAVEL_MEAN, temps=temps, limits={str(T): round(limit_min(T), 1) for T in temps},
               labels=dict(today="Today: fixed dispatch, first come first served", smart_queue="Smart queue at the site only",
                           queuepilot="QueuePilot: smart queue + plant paced by the learned pump rate"),
               across_pours=table, demo=demo)
    (OUT / "concrete.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main()
