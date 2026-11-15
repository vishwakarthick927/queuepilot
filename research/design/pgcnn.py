"""
PG-CNN: where the SMOKE goes (constraint 3; the people model is research/design/pggnn.py).

The floor plan is drawn onto a 24 x 42 grid (engine/smoke.py: each 6 m tile = 3 x 3 cells of 2 m).
Every 2-second step, for every cell (exactly engine/smoke.step, written in torch so we can learn through it):

  PHYSICS (hard-coded, never learned)
    smoke += source at the fire
    smoke spreads: 0.2 x the difference moves across every open link (walls are missing links)
    smoke *= (1 - vent) inside the building            spreading only moves smoke; venting only removes it

  LEARNED (bounded)
    vent per cell = sigmoid(CNN(what the architect knows: room / corridor / area / window share)) x 0.15
    So the network can only decide how fast a space clears smoke. It can never create smoke.

Three forecasters, as in research/flood/water.py: "physics" (the textbook: vent 0.03 everywhere),
"cnn" (a CNN predicts the change in smoke directly, no physics), "pgcnn" (ours). Trained by rolling the
physics forward over the whole fire and backpropagating through it. Tested on floor plans never seen in training.

    python -m engine.smoke                      # once: MAIN's smoke data -> data/design/smoke_train.npz
    python -m research.design.pgcnn             # trains, tests, writes pgcnn_results.json + pgcnn_demo.json
"""
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

from engine import plans, smoke as S

OUT = Path(__file__).parent
DATA = OUT.parents[1] / "data" / "design"
torch.set_num_threads(4)


# ---------------------------------------------------------------- the physics (same as engine/smoke.step)
def step(s, src, vent, link_r, link_d, inside):
    """One step for a batch of grids (B, H, W). Spreading conserves smoke; venting can only remove it."""
    s = s + src
    fr = S.SPREAD * link_r[:, :, :-1] * (s[:, :, :-1] - s[:, :, 1:])        # flow to the right neighbour
    fd = S.SPREAD * link_d[:, :-1, :] * (s[:, :-1, :] - s[:, 1:, :])        # flow to the neighbour below
    s = s - nn.functional.pad(fr, (0, 1)) + nn.functional.pad(fr, (1, 0))
    s = s - nn.functional.pad(fd, (0, 0, 0, 1)) + nn.functional.pad(fd, (0, 0, 1, 0))
    return s * (1 - vent) * inside


def run(vent, d, steps=S.STEPS):
    """Roll the physics forward from no smoke; returns smoke (B, steps, H, W)."""
    s, out = torch.zeros_like(d["source"]), []
    for _ in range(steps):
        s = step(s, d["source"], vent, d["link_r"], d["link_d"], d["inside"])
        out.append(s)
    return torch.stack(out, 1)


# ---------------------------------------------------------------- the models
class Vent(nn.Module):
    """Ours: a small CNN reads the plan and outputs venting per cell in [0, VENT_MAX] (sigmoid)."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(4, 16, 3, padding=1), nn.Tanh(), nn.Conv2d(16, 16, 3, padding=1), nn.Tanh(), nn.Conv2d(16, 1, 1))
        nn.init.constant_(self.net[-1].bias, -1.4)            # start near the textbook 0.03

    def forward(self, feats):
        return torch.sigmoid(self.net(feats))[:, 0] * S.VENT_MAX

    def predict(self, d):
        return run(self(d["feats"]), d)


class CNNOnly(nn.Module):
    """Baseline: a CNN predicts the change in smoke directly from smoke, fire and plan. No physics."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(6, 32, 3, padding=1), nn.Tanh(), nn.Conv2d(32, 32, 3, padding=1), nn.Tanh(), nn.Conv2d(32, 1, 3, padding=1))

    def predict(self, d):
        s, out = torch.zeros_like(d["source"]), []
        for _ in range(S.STEPS):
            x = torch.cat([s[:, None], d["source"][:, None] * 5, d["feats"]], 1)
            s = torch.relu(s + 0.05 * self.net(x)[:, 0]) * d["inside"]
            out.append(s)
        return torch.stack(out, 1)


class Physics:
    """Baseline: the textbook, vent 0.03 in every room and corridor."""

    def predict(self, d):
        return run(torch.full_like(d["source"], S.VENT_TEXTBOOK), d)


# ---------------------------------------------------------------- data, training, test
def load():
    z = np.load(DATA / "smoke_train.npz")
    T = lambda k: torch.tensor(z[k], dtype=torch.float32)
    d = {k: T(k) for k in ("smoke", "feats", "inside", "link_r", "link_d", "source", "vent_true")}
    return d, z["is_test"].astype(bool), z["plan_index"]


def part(d, idx):
    return {k: v[idx] for k, v in d.items()}


def train(model, d, iters=300, batch=16):
    """Roll the whole fire (75 steps) and match the simulator's smoke everywhere."""
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    r = np.random.default_rng(0)
    n = len(d["smoke"])
    for i in range(iters):
        b = part(d, torch.tensor(r.integers(n, size=batch)))
        loss = ((model.predict(b) - b["smoke"]) ** 2).mean() * 100
        opt.zero_grad(); loss.backward(); opt.step()
        if i % 50 == 0:
            print(f"    iter {i:4d}  loss {loss.item():.4f}", flush=True)
    return model


def block_times(plan_i, sm):
    """{edge: step} when each corridor passage is blocked (engine.smoke.blocked_edges on our smoke)."""
    plan = S.add_windows(plans.make_plan(5000 + int(plan_i)))
    return {c["edge"]: c["step"] for c in S.blocked_edges(plan, sm, S.grid(plan))}


@torch.no_grad()
def test(model, d, plan_of):
    """Held-out plans: smoke error, smoke created from nothing, error in seconds until each corridor is blocked."""
    pred = model.predict(d)
    inside = d["inside"][:, None]
    err = float(((pred - d["smoke"]).abs() * inside).sum() / (inside.sum() * pred.shape[1]))
    added = d["source"].sum((1, 2))[:, None] * torch.arange(1, pred.shape[1] + 1)          # smoke put in so far
    created = float(torch.relu(pred.sum((2, 3)) - added).max(1).values.mean())
    gaps = []
    for k in range(len(pred)):
        t, p = block_times(plan_of[k], d["smoke"][k].numpy()), block_times(plan_of[k], pred[k].numpy())
        for e in set(t) | set(p):
            gaps.append(abs(t.get(e, S.STEPS + 1) - p.get(e, S.STEPS + 1)) * 2.0)          # never = after the run
    g = np.array(gaps) if gaps else np.zeros(1)
    return {"smoke_error": round(err, 4), "smoke_created": round(created, 3),
            "block_time_err_s": round(float(g.mean()), 1), "block_time_ci95": round(float(1.96 * g.std() / np.sqrt(len(g))), 1),
            "passages": len(gaps), "fires": len(pred)}


@torch.no_grad()
def demo(vent_model):
    """Our predicted smoke for the demo fires, in the shape of smoke_demo.json (every 3 steps = 6 s)."""
    plan = json.loads((DATA / "demo_plan.json").read_text())
    g = S.grid(plan)
    T = lambda x: torch.tensor(np.asarray(x, dtype=np.float32))[None]
    vent = vent_model(T(g["feats"]))
    out = []
    for f in json.loads((DATA / "smoke_demo.json").read_text())["fires"]:
        d = {"source": T(S.SOURCE * (g["node"] == f["start_node"])), "link_r": T(g["link_r"]), "link_d": T(g["link_d"]), "inside": T(g["inside"])}
        sm = run(vent, d)[0].numpy()
        out.append({"fire": f["fire"], "start_node": f["start_node"], "close": S.blocked_edges(plan, sm, g),
                    "smoke": np.round(sm[::3], 2).tolist()})
    return out


def main():
    torch.manual_seed(0)
    d, is_test, plan_of = load()
    tr, te = part(d, torch.tensor(~is_test)), part(d, torch.tensor(is_test))
    ours, box = Vent(), CNNOnly()
    print("training PG-CNN", flush=True); train(ours, tr)
    print("training CNN only", flush=True); train(box, tr)
    models = {"physics": Physics(), "cnn": box, "pgcnn": ours}
    res = {"models": {k: test(m, te, plan_of[is_test]) for k, m in models.items()}}
    with torch.no_grad():
        inside = te["inside"] > 0
        learned = ours(te["feats"])[inside]
        res["vent_error"] = {"textbook": round(float((S.VENT_TEXTBOOK - te["vent_true"][inside]).abs().mean()), 4),
                             "pgcnn": round(float((learned - te["vent_true"][inside]).abs().mean()), 4)}
    res["setup"] = {"source": "MAIN engine.smoke (data/design/smoke_train.npz)", "train_fires": int((~is_test).sum()),
                    "test_fires": int(is_test.sum()), "unseen": "12 floor plans never seen in training", "steps": S.STEPS,
                    "dt_s": 2, "simulated": True}
    print(json.dumps(res, indent=1))
    (OUT / "pgcnn_results.json").write_text(json.dumps(res, indent=1))
    (OUT / "pgcnn_demo.json").write_text(json.dumps({"simulated": True, "frame_every_steps": 3, "fires": demo(ours)}))
    torch.save(ours.state_dict(), OUT / "pgcnn.pt")


if __name__ == "__main__":
    main()
