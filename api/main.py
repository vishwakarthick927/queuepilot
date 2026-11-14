"""QueuePilot API. Run from repo root:  uvicorn api.main:app --reload"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from engine import simulation as sim

app = FastAPI(title="QueuePilot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class SimRequest(BaseModel):
    n_people: int = 150
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
    out = {}
    for key in STRATEGIES:
        results = [_run(key, sim.make_people(req.n_people, seed=s, priority_share=req.priority_share), closures)
                   for s in range(req.runs)]
        mean = lambda k: round(sum(r[k] for r in results) / req.runs, 2 if k == "jain_fairness" else 1)
        out[key] = {k: mean(k) for k in ("avg_wait", "max_wait", "p95_wait", "jain_fairness")}
        out[key]["utilisation"] = {c: round(sum(r["utilisation"][c] for r in results) / req.runs)
                                   for c in results[0]["utilisation"]}
        for extra in ("avg_wait_priority", "avg_wait_normal"):
            if extra in results[0]:
                out[key][extra] = mean(extra)
        if req.trace:  # one crowd (seed 0) for animation
            one = _run(key, sim.make_people(req.n_people, seed=0, priority_share=req.priority_share), closures)
            out[key]["timeline"] = sim.timeline(one)
    out["labels"] = STRATEGIES
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
