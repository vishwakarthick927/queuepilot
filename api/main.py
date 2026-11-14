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

@app.post("/simulate")
def simulate(req: SimRequest):
    out = {}
    for key, strat in [("fcfs", sim.pick_shortest_line), ("queuepilot", sim.pick_queuepilot)]:
        results = [sim.simulate(sim.make_people(req.n_people, seed=s), strat,
                                {k: [tuple(w) for w in v] for k, v in req.closures.items()}) for s in range(req.runs)]
        util = {c: round(sum(r["utilisation"][c] for r in results) / req.runs)
                for c in results[0]["utilisation"]}
        out[key] = {
            "avg_wait": round(sum(r["avg_wait"] for r in results) / req.runs, 1),
            "max_wait": round(sum(r["max_wait"] for r in results) / req.runs, 1),
            "utilisation": util,
        }
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
