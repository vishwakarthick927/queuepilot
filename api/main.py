"""QueuePilot API. Run from repo root:  uvicorn api.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import statistics
from engine import simulation as sim

app = FastAPI(title="QueuePilot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SimRequest(BaseModel):
    preset: str = "normal"   # "normal" (stable load) or "stress" (125% certificate load)
    n_people: int | None = None  # override the preset's crowd size
    runs: int = 100          # average over this many random crowds
    closures: dict = {}      # e.g. {"C2": [[60, 150]]} -> C2 closed minutes 60-150
    priority_share: float = 0.0  # e.g. 0.1 -> 10% priority people; QueuePilot serves them first
    trace: bool = False          # include per-5-min timeline (one crowd) for animation

STRATEGIES = {
    "fcfs": "Shortest line (what people do today)",
    "queuepilot": "QueuePilot route-on-arrival",
    "pooled": "QueuePilot pooled virtual queue (late binding)",
}


def _run(key, people, closures):
    if key == "pooled":
        return sim.simulate_pooled(people, closures, use_priority=True)
    strat = sim.pick_shortest_line if key == "fcfs" else sim.pick_queuepilot
    return sim.simulate(people, strat, closures, use_priority=(key == "queuepilot"))


@app.post("/simulate")
def simulate(req: SimRequest):
    closures = {k: [tuple(w) for w in v] for k, v in req.closures.items()}
    pr = sim.PRESETS.get(req.preset, sim.PRESETS["normal"])
    n = req.n_people or pr["n"]
    crowd = lambda seed: sim.make_people(n, avg_gap=pr["avg_gap"], seed=seed, priority_share=req.priority_share)
    out, per_seed = {}, {}
    for key in STRATEGIES:
        results = [_run(key, crowd(s), closures) for s in range(req.runs)]
        per_seed[key] = [r["avg_wait"] for r in results]
        mean = lambda k: round(sum(r[k] for r in results) / req.runs, 2 if k == "jain_fairness" else 1)
        out[key] = {k: mean(k) for k in ("avg_wait", "max_wait", "p95_wait", "jain_fairness")}
        out[key]["utilisation"] = {c: round(sum(r["utilisation"][c] for r in results) / req.runs)
                                   for c in results[0]["utilisation"]}
        out[key]["wait_by_service"] = {sv: round(sum(r["wait_by_service"][sv] for r in results) / req.runs, 1)
                                       for sv in results[0]["wait_by_service"]}
        w = per_seed[key]
        sd = statistics.stdev(w) if len(w) > 1 else 0.0
        out[key]["avg_wait_ci95"] = round(1.96 * sd / len(w) ** 0.5, 2)   # mean ± this
        out[key]["win_rate_vs_fcfs"] = round(sum(a < b for a, b in zip(w, per_seed["fcfs"])) / len(w), 2)
        for extra in ("avg_wait_priority", "avg_wait_normal"):
            if extra in results[0]:
                out[key][extra] = mean(extra)
        if req.trace:  # one crowd (seed 0) for animation
            one = _run(key, crowd(0), closures)
            out[key]["timeline"] = sim.timeline(one)
    out["labels"] = STRATEGIES
    out["preset"] = {"name": req.preset, "n_people": n, "avg_gap": pr["avg_gap"]}
    return out


# ---------- physics-guided forecasting (engine/physics.py) ----------
import numpy as np
from engine import physics as ph

_steady = np.full(480, 6)
_train = [(ph.arrival_profile(), _steady, ph.real_world_day(_steady, seed=s)[1]) for s in (1, 2)]
_model = ph.fit(_train)


@app.get("/forecast")
def forecast():
    shifted = np.where(np.arange(480) < 240, 4, 7)
    test = [(ph.arrival_profile(), shifted, ph.real_world_day(shifted, seed=s)[1]) for s in (10, 11, 12)]
    lam, s, q = test[0]
    start, h = 60, 60
    return {
        "forecast_error": ph.evaluate(_model, test),
        "example": {
            "minutes": list(range(start + 1, start + 1 + h)),
            "actual": [round(float(x), 1) for x in q[start + 1:start + 1 + h]],
            "physics": [round(float(x), 1) for x in ph.rollout("physics", q[start], lam[start:], s[start:], _model, h)],
            "data": [round(float(x), 1) for x in ph.rollout("data", q[start], lam[start:], s[start:], _model, h)],
            "hybrid": [round(float(x), 1) for x in ph.rollout("hybrid", q[start], lam[start:], s[start:], _model, h)],
        },
        "staffing_plan": ph.recommend_staffing(_model),
        "staffing_comparison": ph.compare_staffing(_model),
    }


# ---------- EV charging hub (engine/ev.py) ----------
from engine import ev as evsim


@app.get("/ev")
def ev(runs: int = 80, temp: float = 1.0, avg_gap: float = 18.0):
    """Battery-physics queue: 4 stalls x 60 kW, 150 kW site cap. temp < 1 = heat derating."""
    return {"config": {"stalls": evsim.STALLS, "stall_kw": evsim.P_STALL, "site_cap_kw": evsim.SITE_CAP,
                       "battery_kwh": evsim.E_BATT, "avg_gap_min": avg_gap, "temp_factor": temp},
            "charge_curve": [{"soc": round(x / 100, 2), "kw": round(evsim.accept_power(x / 100, temp), 1)}
                             for x in range(0, 101, 5)],
            "results": evsim.compare(runs, temp, avg_gap)}
