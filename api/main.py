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

@app.post("/simulate")
def simulate(req: SimRequest):
    out = {}
    for key, strat in [("fcfs", sim.pick_shortest_line), ("queuepilot", sim.pick_queuepilot)]:
        results = [sim.simulate(sim.make_people(req.n_people, seed=s), strat) for s in range(req.runs)]
        util = {c: round(sum(r["utilisation"][c] for r in results) / req.runs)
                for c in results[0]["utilisation"]}
        out[key] = {
            "avg_wait": round(sum(r["avg_wait"] for r in results) / req.runs, 1),
            "max_wait": round(sum(r["max_wait"] for r in results) / req.runs, 1),
            "utilisation": util,
        }
    return out
