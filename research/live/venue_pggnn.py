"""
PG-GNN for QueuePilot Live: HOW MANY people are in every zone of the venue (the plaza-scale model is plaza_pgcnn.py).

Same model as research/design/pggnn.py (variant C: destination channels + demand-ratio door efficiency), with the
two additions docs/STAMPEDE.md "VERSION 2" asks for:
  1. arrivals[t, node]: people who reach the venue during the event are added to their node every step and then
     walk like everyone else (they join the "nearest gate" group; the learned re-decide rate moves them).
  2. gate_eff: each gate's capacity is multiplied by its efficiency, a VISIBLE input (in deployment it is the number
     the twin fits from the gate counters every 30 s). Physics still caps every door, so nobody is created or lost.

Three forecasters: "physics" (doors as designed except gate_eff, everyone to the nearest gate), "gnn" (same message
passing, predicts the change in people directly), "pggnn" (ours). The riverbank venue (ghat) is held out entirely.

    python -m engine.crowd_data                 # once: MAIN's 160 venue runs -> data/crowd/venue_train.npz
    python -m research.live.venue_pggnn         # trains, tests, writes pggnn_venue.json + pggnn_venue_demo.json
"""
import json
from pathlib import Path

import numpy as np
import torch

from engine import crowd
from research.design import pggnn as G

OUT = Path(__file__).parent
DATA = OUT.parents[1] / "data" / "crowd"
T = crowd.STEPS
torch.set_num_threads(4)


class VenueGraph(G.Graph):
    """A venue + which gates are open + how well each gate works. Gate efficiency scales the gate's width,
    so it reaches both the door law (capacity) and the network's edge features (width) as a visible input."""

    def __init__(self, plan, exits, gate_eff, panic):
        super().__init__(plan, exits, None, panic)
        for e_i, e in enumerate(plan["edges"]):
            c = e["candidate"]
            if c is not None and c in gate_eff:
                self.width[2 * e_i:2 * e_i + 2] *= gate_eff[c]
        self.torch()


def rollout(model, g, arrivals, steps):
    """From an empty venue: every step add the arrivals, then one model step. Returns people[step][node].
    Exit nodes keep everyone who left through them."""
    people0 = torch.zeros(g.n)
    state = model.init(g, people0) if hasattr(model, "init") else people0
    total = model.total if hasattr(model, "total") else (lambda s: s)
    out = []
    for k in range(steps):
        a = arrivals[k]
        state = state + (torch.stack([a, torch.zeros_like(a)], 1) if state.dim() == 2 else a)
        state = model.step(g, state, k)
        out.append(total(state))
    return torch.stack(out)


def truth_table(plan, people, flow, exits):
    """[T, nodes]: people in each zone after each step; in each gate node, the cumulative people through it."""
    n = len(plan["nodes"])
    t = np.array(people[:, :n], np.float32)
    for c in plan["candidates"]:
        if c["id"] in exits:
            e = next(i for i, ed in enumerate(plan["edges"]) if ed["candidate"] == c["id"])
            t[:, c["node"]] = np.cumsum(np.abs(flow[:, e]))
    return torch.tensor(t)


def load():
    plans = json.loads((DATA / "venue_plans.json").read_text())
    z = np.load(DATA / "venue_train.npz")
    runs = []
    for r in range(len(z["venue"])):
        plan = plans[int(z["venue"][r])]
        n = len(plan["nodes"])
        exits = [c["id"] for c in plan["candidates"] if z["exits"][r, c["id"]]]
        eff = {c["id"]: float(z["gate_eff"][r, c["id"]]) for c in plan["candidates"]}
        g = VenueGraph(plan, exits, eff, float(z["panic"][r]))
        arr = torch.tensor(z["arrivals"][r, :, :n])
        runs.append((g, arr, truth_table(plan, z["people"][r], z["flow"][r], exits), plan, bool(z["is_test"][r])))
    print(f"loaded {len(runs)} runs ({sum(r[4] for r in runs)} on the held-out venue)", flush=True)
    return runs


def zone_density(plan, traj):
    """people per m2 in the watched zones (no sources, no gates), [steps, zones]."""
    w = crowd.watched(plan)
    area = torch.tensor([plan["nodes"][i]["area_m2"] for i in w], dtype=torch.float32)
    return traj[:, w] / area


def train(model, runs, iters, horizon=240, batch=6, lr=2e-3, exits_loss=True):
    """Roll the first 20 minutes (the build-up) and match the simulator in every zone and at every gate."""
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, iters)
    r = np.random.default_rng(0)
    for i in range(iters):
        picks = [runs[int(k)] for k in r.integers(len(runs), size=batch)]
        b = G.Graph.batch([p[0] for p in picks])
        arr = torch.cat([p[1][:horizon] for p in picks], 1)
        truth = torch.cat([p[2][:horizon] for p in picks], 1)
        pred = rollout(model, b, arr, horizon)
        keep, ex = 1 - b.t_exit, b.t_exit
        loss = ((((pred - truth) * keep) / 10) ** 2).mean() + (0.5 * ((((pred - truth) * ex) / 10) ** 2).mean() if exits_loss else 0)
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step()
        if i % 25 == 0:
            print(f"    iter {i:4d}  loss {loss.item():.4f}", flush=True)
    return model


def danger_min(d):
    hit = torch.nonzero((d >= crowd.DANGER).any(1))
    return float(hit[0]) * crowd.DT / 60 if len(hit) else None


@torch.no_grad()
def test(model, runs):
    """Full 40-minute rollouts on the held-out venue: peak density error, danger-start error, people created / lost."""
    peak, start, lost, agree = [], [], [], []
    for g, arr, truth, plan, _ in runs:
        pred = rollout(model, g, arr, T)
        dp, dt = zone_density(plan, pred), zone_density(plan, truth)
        peak.append(abs(float(dp.max()) - float(dt.max())))
        sp, st = danger_min(dp), danger_min(dt)
        agree.append((sp is None) == (st is None))
        if sp is not None or st is not None:
            start.append(abs((sp if sp is not None else crowd.STEPS * crowd.DT / 60) - (st if st is not None else crowd.STEPS * crowd.DT / 60)))
        lost.append(float((pred.sum(1) - arr.sum(1).cumsum(0)).abs().max()))
    pk, st = np.array(peak), np.array(start) if start else np.zeros(1)
    return {"peak_density_err": round(float(pk.mean()), 2), "peak_ci95": round(float(1.96 * pk.std() / np.sqrt(len(pk))), 2),
            "danger_start_err_min": round(float(st.mean()), 1), "danger_yes_no_agree_pct": round(100 * float(np.mean(agree)), 0),
            "people_created_or_lost": round(float(np.mean(lost)), 2), "runs": len(pk)}


@torch.no_grad()
def demo(model):
    """PG-GNN forecast of the worst zone's density for the four demo venues (today: no intervention), every 30 s.
    The main gate's efficiency is the one the twin learned (forecast.hidden_problem.learned_share), as in deployment."""
    out = {}
    for plan, sched in crowd.venues():
        v = json.loads((DATA / f"{plan['id']}.json").read_text())
        main = plan["main_entrance"]
        eff = {main: v["forecast"]["hidden_problem"]["learned_share"]}
        exits = [c["id"] for c in plan["candidates"] if c["open"]]
        g = VenueGraph(plan, exits, eff, crowd.PANIC)
        arr = torch.zeros(T, len(plan["nodes"]))
        for s, lst in sched.items():
            for node, ppl in lst:
                if s < T:
                    arr[s, node] += ppl
        d = zone_density(plan, rollout(model, g, arr, T))
        worst = d.max(1).values
        out[plan["id"]] = {"worst": [round(float(x), 2) for x in worst[::crowd.FRAME]],
                           "danger_at_min": danger_min(d), "peak_density": round(float(worst.max()), 2)}
    return out


def main():
    torch.manual_seed(0)
    runs = load()
    tr = [r for r in runs if not r[4]]
    te = [r for r in runs if r[4]]
    ours = G.PGGNN(channels=True, ratio=True)
    print("training PG-GNN", flush=True); train(ours, tr, 200)
    box = G.GNNOnly()
    print("training GNN only", flush=True); train(box, tr, 120, exits_loss=False)
    models = {"physics": G.PhysicsOnly(), "gnn": box, "pggnn": ours}
    res = {"models": {k: test(m, te) for k, m in models.items()}}
    res["setup"] = {"source": "MAIN engine.crowd_data (data/crowd/venue_train.npz)", "train_runs": len(tr), "test_runs": len(te),
                    "unseen": "the riverbank venue (ghat), never seen in training", "steps": T, "dt_s": crowd.DT,
                    "train_horizon_steps": 240, "simulated": True}
    print(json.dumps(res, indent=1), flush=True)
    (OUT / "pggnn_venue.json").write_text(json.dumps(res, indent=1))
    dm = {"simulated": True, "frame_s": crowd.FRAME * crowd.DT, "venues": demo(ours)}
    (OUT / "pggnn_venue_demo.json").write_text(json.dumps(dm))
    print({k: (v["danger_at_min"], v["peak_density"]) for k, v in dm["venues"].items()})
    torch.save(ours.state_dict(), OUT / "pggnn_venue.pt")


if __name__ == "__main__":
    main()
