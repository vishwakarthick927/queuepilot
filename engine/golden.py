"""
GOLDEN HOUR: where should each ambulance go?
Today an ambulance drives to the NEAREST hospital. After a mass-casualty event that hospital fills up and patients
wait in the corridor. QueuePilot sends each patient where TREATMENT STARTS SOONEST.

Physics (queueing theory, standard results):
  drive time            t_drive = distance / speed                         (Manhattan distance, 30 km/h in traffic)
  emergency room        c doctors, each treats mu patients per minute       (an M/M/c queue)
  queue conservation    dn/dt = arrivals - c * mu     (while everyone is busy)
  expected wait         W_h = max(0, n_h - c_h + 1) / (c_h * mu_h)          n_h = patients there + ambulances on the way
  decision              h* = argmin over hospitals of ( t_drive + W_h )
What the plan on paper does NOT know: one hospital is short-staffed tonight and treats slower than its nameplate rate.
Learned from data (the paper's residual idea): each hospital's real rate mu_h, from its last treatments
(running average of observed treatment times). Three policies are compared on the SAME calls:
  nearest | QueuePilot with nameplate rates | QueuePilot with learned rates.

Run from repo root:  python -m engine.golden      (writes data/golden/golden.json)
Simulated city and calls. Speeds, treatment times and the event size are stated assumptions, not measurements.
"""
import json
import random
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent.parent / "data" / "golden"
SPEED_KM_MIN = 0.5            # 30 km/h
ON_SCENE_MIN = 5.0            # loading the patient
TREAT_MIN = 20.0              # nameplate mean treatment time per doctor
GOLDEN_MIN = 60.0
HORIZON = 240                 # minutes simulated
HOSPITALS = [                 # name, x km, y km, doctors, real mean treatment time (min)
    ("City General", 9.0, 7.0, 6, 34.0),      # hidden: short-staffed tonight, much slower than the nameplate 20 min
    ("St. Mary's", 4.0, 10.5, 4, 20.0), ("Lakeside", 15.5, 10.0, 4, 20.0), ("Ring Road", 17.0, 3.5, 5, 20.0),
    ("Northgate", 10.0, 12.5, 3, 20.0), ("Riverside", 3.5, 3.0, 4, 20.0)]
EVENT = dict(name="Festival crowd crush", x=9.8, y=6.2, at_min=60, casualties=60, over_min=12)


def make_calls(seed):
    rng = random.Random(seed)
    calls, t = [], 0.0
    while True:                                       # ordinary emergencies: one every 2.5 min on average, anywhere
        t += rng.expovariate(1 / 2.5)
        if t > HORIZON - 60:
            break
        calls.append(dict(t=t, x=rng.uniform(0, 20), y=rng.uniform(0, 14), event=False))
    for _ in range(EVENT["casualties"]):              # the event: many casualties at one place in a few minutes
        calls.append(dict(t=EVENT["at_min"] + rng.uniform(0, EVENT["over_min"]), x=EVENT["x"] + rng.gauss(0, 0.3),
                          y=EVENT["y"] + rng.gauss(0, 0.3), event=True))
    calls.sort(key=lambda c: c["t"])
    for i, c in enumerate(calls):
        c["id"] = i
        c["u"] = rng.random()                         # the same luck for every policy: treatment time = -mean * ln(u)
    return calls


def simulate(calls, policy):
    """policy: 'nearest' | 'nameplate' | 'learned'. Returns per-patient records and per-minute hospital load."""
    H = len(HOSPITALS)
    free = [[0.0] * h[3] for h in HOSPITALS]          # when each doctor is next free
    inbound = [[] for _ in range(H)]                  # arrival times of ambulances on the way
    learned = [TREAT_MIN] * H                         # running estimate of each hospital's treatment time
    seen = [[] for _ in range(H)]                     # (finish time, duration) of treatments, to learn from
    out = []
    for c in calls:
        t = c["t"]
        drive = [ON_SCENE_MIN + (abs(c["x"] - h[1]) + abs(c["y"] - h[2])) / SPEED_KM_MIN for h in HOSPITALS]
        if policy == "nearest":
            h = int(np.argmin(drive))
        else:
            cost = []
            for i, hosp in enumerate(HOSPITALS):
                if policy == "learned":               # learn from treatments that have FINISHED by now
                    done = [d for f, d in seen[i] if f <= t][-12:]
                    learned[i] = float(np.mean(done)) if len(done) >= 3 else TREAT_MIN
                mean = learned[i] if policy == "learned" else TREAT_MIN
                arrive = t + drive[i]
                n = sum(f > arrive for f in free[i]) + sum(a <= arrive for a in inbound[i])   # people ahead of me when I arrive
                cost.append(drive[i] + max(0, n - hosp[3] + 1) * mean / hosp[3])
            h = int(np.argmin(cost))
        arrive = t + drive[h]
        inbound[h].append(arrive)
        out.append(dict(c, h=h, arrive=arrive, drive=drive[h]))
    # treat in order of arrival at each hospital (first come, first served)
    for h in range(H):
        for p in sorted([p for p in out if p["h"] == h], key=lambda p: p["arrive"]):
            k = int(np.argmin(free[h]))
            start = max(p["arrive"], free[h][k])
            dur = -HOSPITALS[h][4] * np.log(max(p["u"], 1e-9))
            free[h][k] = start + dur
            p["start"], p["to_treatment"] = start, start - p["t"]
            seen[h].append((start + dur, dur))
    if policy == "learned":                           # second pass so routing can use what was learned by each call time
        return _replay_learned(calls, seen)
    return out


def _replay_learned(calls, seen_first):
    """Learning needs treatments to have happened. Run event by event: route a call using only treatments finished so far."""
    H = len(HOSPITALS)
    free = [[0.0] * h[3] for h in HOSPITALS]
    waiting = [[] for _ in range(H)]                  # patients routed to h: (arrive, record)
    finished = [[] for _ in range(H)]                 # (finish time, duration)
    out = []

    def settle(h, now):
        """Start treatment for everyone at hospital h who can start before `now`."""
        waiting[h].sort(key=lambda w: w[0])
        while waiting[h]:
            arrive, p = waiting[h][0]
            k = int(np.argmin(free[h]))
            start = max(arrive, free[h][k])
            if start > now:
                break
            dur = -HOSPITALS[h][4] * np.log(max(p["u"], 1e-9))
            free[h][k] = start + dur
            p["start"], p["to_treatment"] = start, start - p["t"]
            finished[h].append((start + dur, dur))
            waiting[h].pop(0)

    for c in calls:
        t = c["t"]
        cost, drive = [], []
        for i, hosp in enumerate(HOSPITALS):
            settle(i, t)
            d = ON_SCENE_MIN + (abs(c["x"] - hosp[1]) + abs(c["y"] - hosp[2])) / SPEED_KM_MIN
            done = [dur for f, dur in finished[i] if f <= t][-12:]
            mean = float(np.mean(done)) if len(done) >= 3 else TREAT_MIN
            arrive = t + d
            n = sum(f > arrive for f in free[i]) + sum(a <= arrive for a, _ in waiting[i])
            drive.append(d); cost.append(d + max(0, n - hosp[3] + 1) * mean / hosp[3])
        h = int(np.argmin(cost))
        p = dict(c, h=h, arrive=t + drive[h], drive=drive[h])
        waiting[h].append((p["arrive"], p)); out.append(p)
    for h in range(H):
        settle(h, 1e9)
    return out


def summary(recs):
    tt = np.array([p["to_treatment"] for p in recs])
    ev = np.array([p["event"] for p in recs])
    return dict(patients=len(recs), late=int((tt > GOLDEN_MIN).sum()), late_event=int((tt[ev] > GOLDEN_MIN).sum()),
                mean_min=round(float(tt.mean()), 1), worst_min=round(float(tt.max()), 1), event_mean_min=round(float(tt[ev].mean()), 1))


def load_curve(recs):
    """People waiting (arrived, not yet started) at each hospital, every minute."""
    return [[int(sum(p["arrive"] <= m < p["start"] for p in recs if p["h"] == h)) for h in range(len(HOSPITALS))] for m in range(HORIZON)]


def main(seeds=30):
    OUT.mkdir(parents=True, exist_ok=True)
    policies = ["nearest", "nameplate", "learned"]
    stats = {p: [] for p in policies}
    for s in range(seeds):
        calls = make_calls(s)
        for p in policies:
            stats[p].append(summary(simulate(calls, p)))
    agg = {}
    for p in policies:
        late = np.array([x["late"] for x in stats[p]]); mean = np.array([x["mean_min"] for x in stats[p]])
        ev = np.array([x["late_event"] for x in stats[p]])
        agg[p] = dict(late_mean=round(float(late.mean()), 1), late_ci95=round(float(1.96 * late.std() / np.sqrt(seeds)), 1),
                      late_event_mean=round(float(ev.mean()), 1), mean_min=round(float(mean.mean()), 1),
                      worst_min=round(float(np.mean([x["worst_min"] for x in stats[p]])), 1), seeds=seeds)
    calls = make_calls(0)
    demo = {}
    for p in policies:
        recs = simulate(calls, p)
        demo[p] = dict(summary=summary(recs), waiting=load_curve(recs),
                       patients=[dict(t=round(r["t"], 1), x=round(r["x"], 2), y=round(r["y"], 2), event=r["event"], h=r["h"],
                                      arrive=round(r["arrive"], 1), start=round(r["start"], 1), wait=round(r["to_treatment"], 1)) for r in recs])
    radar = json.loads((Path(__file__).parent.parent / "research" / "golden" / "radar_results.json").read_text())
    out = dict(simulated=True, city_km=[20, 14], horizon_min=HORIZON, golden_min=GOLDEN_MIN, speed_kmh=SPEED_KM_MIN * 60,
               nameplate_treat_min=TREAT_MIN, event=EVENT,
               hospitals=[dict(name=h[0], x=h[1], y=h[2], doctors=h[3], real_treat_min=h[4]) for h in HOSPITALS],
               labels=dict(nearest="Nearest hospital (today)", nameplate="QueuePilot, plan on paper", learned="QueuePilot, learned from tonight's data"),
               across_days=agg, demo=demo, load_forecast_model=radar)
    (OUT / "golden.json").write_text(json.dumps(out))
    for p in policies:
        print(p, agg[p], "| demo", demo[p]["summary"])


if __name__ == "__main__":
    main()
