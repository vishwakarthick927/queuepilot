"""
QueuePilot-Perishable: ONE engine for every queue where the thing waiting changes physically.

The common structure across industries:
  - jobs arrive (trucks, cans, loads),
  - each job has a physical STATE that evolves while it waits (sugar content, temperature,
    bacteria count, cement hydration), governed by a known law,
  - a job's VALUE in rupees depends on its state when service starts, and may fall off a
    cliff (rejected load) when the state crosses a limit,
  - a few servers (mill feeders, paver, chillers, pump) process jobs one at a time.

First-come-first-served ignores the physics. QueuePilot computes, for every waiting job,
how many rupees it will lose if it waits one more service slot, and serves the job with the
largest loss per minute of server time (the "c-mu rule" from queueing theory, here with
loss rates computed live from physics, including cliffs). Doomed jobs (already worthless)
go last so they don't block savable ones.

A sector = a dict of functions. Adding a new industry means writing its physics, not a new
system. That is the product.

Run:  python -m engine.perishable
"""
import math
import random

Q10 = 2.0  # rule of thumb: rate doubles per +10 °C (sugar inversion, bacteria, cement hydration)


def q10(temp_c, ref_c=25.0):
    return Q10 ** ((temp_c - ref_c) / 10)


# ---------------- sector physics ----------------
# Each sector: make_job(rng, t) -> job dict; value(job, t) -> rupees if service starts at t;
# service_min(job) -> minutes on the server; servers; arrivals; labels.
# All numbers are illustrative assumptions for a demo, stated in the docstrings.

def _sugar():
    """Sugarcane at a mill. Cut cane loses recoverable sugar ~ exponentially: k = 0.4 %/h of
    its sugar at 25 °C, Q10 = 2. Trucks 5–15 t, cut 2–24 h before arrival. Value = tonnes ×
    recovery × 100 kg sugar/t at 10% recovery × ₹38/kg. Crushing feeder: 1.5 min per tonne."""
    def make(rng, t, temp):
        tons = rng.uniform(5, 15)
        return {"arrive": t, "tons": tons, "age0": rng.uniform(2, 24) * 60, "temp": temp}

    def value(j, t):
        hours = (j["age0"] + (t - j["arrive"])) / 60
        k = 0.004 * q10(j["temp"])
        recovery = 0.10 * math.exp(-k * hours)
        return j["tons"] * 1000 * recovery * 38

    return {"name": "Sugarcane mill", "unit": "truck", "servers": 2, "gap": 7.0, "n": 200,
            "make": make, "value": value, "service": lambda j: 1.5 * j["tons"],
            "physics": "Sucrose inversion: R(t) = R0·e^(−k(T)·t), k doubles per +10 °C",
            "money": "₹ of sugar recovered"}


def _asphalt():
    """Hot-mix asphalt for road paving. Newton cooling dT/dt = −h·(T − T_air), h larger in wind.
    Leaves plant at 160–170 °C after a 20–60 min haul; must be laid at ≥ 125 °C or the load
    (20 t × ₹6,000/t) is rejected. Paver lays a load in ~9 min."""
    def make(rng, t, temp):
        return {"arrive": t, "T0": rng.uniform(150, 162), "air": temp, "tons": 20.0,
                "h": rng.uniform(0.004, 0.007)}

    def value(j, t):
        T = j["air"] + (j["T0"] - j["air"]) * math.exp(-j["h"] * (t - j["arrive"]))
        return j["tons"] * 6000 if T >= 125 else 0.0

    return {"name": "Road paving (hot asphalt)", "unit": "truck", "servers": 1, "gap": 9.5, "n": 60,
            "make": make, "value": value, "service": lambda j: 9.0,
            "physics": "Newton cooling: T(t) = T_air + (T0 − T_air)·e^(−h·t); reject below 125 °C",
            "money": "₹ of asphalt laid (rejected loads = ₹0)"}


def _milk():
    """Village milk collection. Bacteria grow exponentially, doubling ~45 min at 30 °C (Q10 = 2).
    Farmers arrive with 20–60 L, starting count 0.5–3 lakh/mL. Price by grade: < 5 lakh ₹40/L,
    < 10 lakh ₹34/L, < 20 lakh ₹25/L, above that rejected. Chiller intake ~ 0.15 min/L."""
    def make(rng, t, temp):
        return {"arrive": t, "litres": rng.uniform(20, 60), "N0": rng.uniform(0.5, 3.0), "temp": temp}

    def value(j, t):
        doubling = 45 / q10(j["temp"], 30)
        N = j["N0"] * 2 ** ((t - j["arrive"]) / doubling)
        price = 40 if N < 5 else 34 if N < 10 else 25 if N < 20 else 0
        return j["litres"] * price

    return {"name": "Milk chilling centre", "unit": "farmer", "servers": 2, "gap": 2.4, "n": 200,
            "make": make, "value": value, "service": lambda j: 0.15 * j["litres"],
            "physics": "Bacterial growth: N(t) = N0·2^(t/τ(T)), τ halves per +10 °C; price grades by N",
            "money": "₹ paid to farmers for milk"}


def _concrete():
    """Ready-mix concrete. Must be placed before initial set: ~90 min after batching at 30 °C,
    shorter when hotter (Q10 = 2). Trucks arrive 30–75 min after batching. 7 m³ × ₹5,500.
    One pump places a truck in ~12 min. Late = rejected."""
    def make(rng, t, temp):
        return {"arrive": t, "age0": rng.uniform(30, 75), "temp": temp, "m3": 7.0}

    def value(j, t):
        limit = 90 / q10(j["temp"], 30)
        return j["m3"] * 5500 if j["age0"] + (t - j["arrive"]) <= limit else 0.0

    return {"name": "Ready-mix concrete pour", "unit": "truck", "servers": 1, "gap": 12.5, "n": 50,
            "make": make, "value": value, "service": lambda j: 12.0,
            "physics": "Cement hydration: set time ≈ 90 min × 2^(−(T−30)/10)",
            "money": "₹ of concrete placed (rejected loads = ₹0)"}


SECTORS = {"sugarcane": _sugar(), "asphalt": _asphalt(), "milk": _milk(), "concrete": _concrete()}


# ---------------- generic engine ----------------
def make_jobs(sector, seed, temp):
    rng, t, jobs = random.Random(seed), 0.0, []
    for i in range(sector["n"]):
        t += rng.expovariate(1 / sector["gap"])
        j = sector["make"](rng, t, temp)
        j["id"] = i
        jobs.append(j)
    return jobs


def pick_fcfs(waiting, t, sector, lookahead):
    return min(waiting, key=lambda j: j["arrive"])


def pick_queuepilot(waiting, t, sector, lookahead):
    """Serve the job that loses the most rupees per minute of server time if it waits
    one more slot. Worthless jobs go last."""
    def score(j):
        v_now = sector["value"](j, t)
        if v_now <= 0:
            return -1e9
        loss = v_now - sector["value"](j, t + lookahead)
        return loss / sector["service"](j)
    return max(waiting, key=score)


def simulate(sector, policy, seed=0, temp=30.0):
    jobs = make_jobs(sector, seed, temp)
    pick = pick_queuepilot if policy == "queuepilot" else pick_fcfs
    lookahead = sum(sector["service"](j) for j in jobs) / len(jobs) / sector["servers"]
    free = [0.0] * sector["servers"]
    waiting, i, done = [], 0, []
    while i < len(jobs) or waiting:
        s = min(range(len(free)), key=lambda k: free[k])
        t = free[s]
        if not waiting and i < len(jobs) and jobs[i]["arrive"] > t:
            t = jobs[i]["arrive"]
        while i < len(jobs) and jobs[i]["arrive"] <= t:
            waiting.append(jobs[i]); i += 1
        j = pick(waiting, t, sector, lookahead)
        waiting.remove(j)
        v = sector["value"](j, t)
        done.append({"wait": t - j["arrive"], "value": v, "max_value": sector["value"](j, j["arrive"])})
        free[s] = t + sector["service"](j)
    lost = sum(d["max_value"] - d["value"] for d in done)
    return {
        "jobs": len(done),
        "value_rs": round(sum(d["value"] for d in done)),
        "lost_rs": round(lost),
        "rejected": sum(1 for d in done if d["value"] <= 0 < d["max_value"]),
        "avg_wait": round(sum(d["wait"] for d in done) / len(done), 1),
    }


def compare_sector(key, runs=40, temp=30.0):
    import statistics as st
    sec = SECTORS[key]
    res = {p: [simulate(sec, p, s, temp) for s in range(runs)] for p in ("fcfs", "queuepilot")}
    out = {"sector": sec["name"], "unit": sec["unit"], "physics": sec["physics"], "money": sec["money"],
           "servers": sec["servers"], "temp_c": temp}
    for p, rs in res.items():
        out[p] = {k: round(st.mean(r[k] for r in rs), 1) for k in rs[0]}
    f, q = out["fcfs"], out["queuepilot"]
    out["loss_cut_pct"] = round(100 * (f["lost_rs"] - q["lost_rs"]) / f["lost_rs"], 1) if f["lost_rs"] else 0.0
    out["saved_rs_per_day"] = round(f["lost_rs"] - q["lost_rs"])
    out["win_rate"] = round(sum(a["lost_rs"] < b["lost_rs"] for a, b in zip(res["queuepilot"], res["fcfs"])) / runs, 2)
    return out


if __name__ == "__main__":
    for key in SECTORS:
        for temp in (30.0, 38.0):
            r = compare_sector(key, temp=temp)
            print(f"{r['sector']:28} {temp:.0f}°C  FCFS lost ₹{r['fcfs']['lost_rs']:>9,.0f} rej {r['fcfs']['rejected']:5}"
                  f" | QP lost ₹{r['queuepilot']['lost_rs']:>9,.0f} rej {r['queuepilot']['rejected']:5}"
                  f" | cut {r['loss_cut_pct']:5.1f}%  win {r['win_rate']}  wait {r['fcfs']['avg_wait']}→{r['queuepilot']['avg_wait']}")
