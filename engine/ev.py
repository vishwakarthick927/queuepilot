"""
QueuePilot-EV: a queue whose service time is governed by battery physics.

Real problem: highway / city EV fast-charging hubs (India's EV fleet is growing fast,
chargers are scarce). A car's "service time" is not a constant:

1. Battery physics (CC-CV charging). Below ~80% state of charge (SOC) a battery takes
   full power (constant-current phase). Above 80% the charger must cut power to keep
   cell voltage and heat safe (constant-voltage phase): power tapers roughly linearly
   to ~10% at 100% SOC. So the last 20% takes about as long as the 10->80% part.
       dSOC/dt = P_accepted(SOC, T) / E_battery
       P_accepted = P_max                                  SOC < 0.8
                  = P_max * (1 - 0.9 * (SOC-0.8)/0.2)      SOC >= 0.8
   Heat derating (hot day): P_max shrinks by a temperature factor.

2. Shared grid limit. All stalls share one transformer (site cap, kW). Power is a
   conserved, limited resource that must be split between cars every minute.

QueuePilot-EV makes three physics-aware decisions every minute:
  a) POWER SPLIT (water-filling): give power to the cars that can actually absorb it
     (CC-phase cars), instead of an equal split that wastes power on tapering cars.
  b) DYNAMIC TARGET: when cars are waiting, cap charging at 80% (the efficient part
     of the curve) unless the driver needs more for their trip; release the cap when
     the queue is empty.
  c) POOLED QUEUE: one virtual queue; a freed stall takes the next car in line.

Baseline: what hubs do today. Equal power split, everyone charges to the SOC they want,
first come first served.

Run:  python -m engine.ev
"""
import random

STALLS = 4
P_STALL = 60.0      # kW max per stall
SITE_CAP = 150.0    # kW transformer limit (less than 4 x 60: typical, grid is the bottleneck)
E_BATT = 60.0       # kWh battery
DT = 1.0            # minute time step


def accept_power(soc, temp_factor=1.0):
    """Max power (kW) the battery accepts at this SOC (CC-CV curve)."""
    p = P_STALL * temp_factor
    if soc < 0.8:
        return p
    return p * max(0.1, 1 - 0.9 * (soc - 0.8) / 0.2)


def make_cars(n=60, avg_gap=18.0, seed=0):
    """Busy hours at a 4-stall hub: a car every ~18 min on average."""
    rng = random.Random(seed)
    cars, t = [], 0.0
    for i in range(n):
        t += rng.expovariate(1 / avg_gap)
        soc0 = rng.uniform(0.10, 0.40)
        want = 1.0 if rng.random() < 0.5 else 0.8           # half the drivers want "full"
        need = min(want, soc0 + rng.uniform(0.35, 0.60))     # SOC truly needed for their trip
        cars.append({"id": i, "arrive": t, "soc0": soc0, "want": want, "need": max(need, 0.6)})
    return cars


def split_equal(cars_on, cap, temp):
    """Baseline: split site power equally between plugged cars (capped by what each accepts)."""
    if not cars_on:
        return {}
    share = cap / len(cars_on)
    return {c["id"]: min(share, accept_power(c["soc"], temp)) for c in cars_on}


def split_waterfill(cars_on, cap, temp):
    """Physics-aware: water-filling. Each car can absorb at most accept_power(SOC).
    Raise a common power level until the site cap is used up; power a tapering car
    cannot take flows to the cars that can. No kW is wasted."""
    alloc, left, todo = {}, cap, sorted(cars_on, key=lambda c: accept_power(c["soc"], temp))
    while todo:
        share = left / len(todo)
        c = todo[0]
        a = accept_power(c["soc"], temp)
        if a <= share:            # this car is saturated, give it all it accepts
            alloc[c["id"]] = a
            left -= a
            todo.pop(0)
        else:                     # everyone left gets an equal share
            for c in todo:
                alloc[c["id"]] = share
            break
    return alloc


def simulate(cars, policy="baseline", temp=1.0, horizon=24 * 60):
    """Minute-by-minute simulation. Returns wait, time in system, throughput, energy."""
    queue, stalls, done, i, t = [], [], [], 0, 0.0
    energy, wasted = 0.0, 0.0
    cars = [dict(c) for c in cars]
    while t < horizon and (i < len(cars) or queue or stalls):
        while i < len(cars) and cars[i]["arrive"] <= t:
            queue.append(cars[i]); i += 1
        while queue and len(stalls) < STALLS:           # free stall takes next car (FCFS / pooled)
            c = queue.pop(0)
            c["start"], c["soc"] = t, c["soc0"]
            stalls.append(c)
        # target SOC
        for c in stalls:
            if policy in ("queuepilot", "cap_only"):
                c["target"] = max(c["need"], 0.8) if queue else c["want"]
                c["target"] = min(c["target"], c["want"])
            else:
                c["target"] = c["want"]
        split = split_waterfill if policy in ("queuepilot", "waterfill_only") else split_equal
        alloc = split(stalls, SITE_CAP, temp)
        used = sum(alloc.values())
        wasted += (SITE_CAP - used) * DT / 60 if len(stalls) == STALLS else 0
        for c in stalls:
            kw = alloc.get(c["id"], 0.0)
            c["soc"] = min(c["target"], c["soc"] + kw * DT / 60 / E_BATT)
            energy += kw * DT / 60
        for c in [c for c in stalls if c["soc"] >= c["target"] - 1e-9]:
            c["end"] = t + DT
            stalls.remove(c); done.append(c)
        t += DT
    waits = [c["start"] - c["arrive"] for c in done]
    sys = [c["end"] - c["arrive"] for c in done]
    return {
        "served": len(done),
        "avg_wait": sum(waits) / len(waits),
        "max_wait": max(waits),
        "avg_time_in_system": sum(sys) / len(sys),
        "energy_kwh": round(energy),
        "need_met": sum(c["soc"] >= c["need"] - 1e-6 for c in done) / len(done),
        "avg_final_soc": sum(c["soc"] for c in done) / len(done),
    }


POLICIES = {
    "baseline": "Today: equal power split, everyone charges to what they asked for",
    "waterfill_only": "Physics power split only (water-filling)",
    "cap_only": "Dynamic 80% cap only (when cars are waiting)",
    "queuepilot": "QueuePilot-EV: both",
}


def compare(runs=80, temp=1.0, avg_gap=18.0):
    import statistics as st
    out = {}
    for pol in POLICIES:
        rs = [simulate(make_cars(avg_gap=avg_gap, seed=s), pol, temp) for s in range(runs)]
        w = [r["avg_wait"] for r in rs]
        out[pol] = {k: round(st.mean(r[k] for r in rs), 2) for k in rs[0]}
        out[pol]["avg_wait_ci95"] = round(1.96 * st.stdev(w) / runs ** 0.5, 2)
    out["labels"] = POLICIES
    return out


if __name__ == "__main__":
    for k, v in compare().items():
        if k != "labels":
            print(f"{k:15}", v)
