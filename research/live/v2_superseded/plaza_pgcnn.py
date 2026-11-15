"""
PG-CNN for QueuePilot Live: WHERE in the plaza the crowd piles up (the venue-scale model is research/live/venue_pggnn.py).

The plaza is a 20 x 32 grid of 2 m cells (engine/plaza.py). Every 5-second step, for every cell
(exactly engine.plaza.step, written in torch so we can learn through it):

  PHYSICS (hard-coded, never learned)
    people_next = people + arriving - leaving            nobody is created or lost
    each cell sends 0.6 of its people to the neighbour closest to the gate
    a cell takes in only  passability x 24 - people     (24 = 6 people/m2 x 4 m2)
    gate cells let 6.5 people per step out

  LEARNED (bounded)
    passability per cell = sigmoid(CNN(survey image: clutter, distance to gate, gate)) in [0, 1]
    So the network can only decide how much of a cell is usable floor. It can never create people.

Three forecasters, as in research/design/pgcnn.py: "physics" (the site plan: passability 1 everywhere),
"cnn" (a CNN predicts the change in people directly, no physics), "pgcnn" (ours). Trained by rolling the physics
over the whole 20-minute wave and backpropagating through it. Tested on 12 plazas never seen in training.

    python -m engine.plaza                     # once: MAIN's plaza data -> data/crowd/plaza_train.npz
    python -m research.live.plaza_pgcnn        # trains, tests, writes pgcnn_plaza.json + pgcnn_plaza_demo.json
"""
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

from engine import plaza as P

OUT = Path(__file__).parent
DATA = OUT.parents[1] / "data" / "crowd"
torch.set_num_threads(4)
DIRS = P.DIRS                    # right, up, down: where a cell sends people


# ---------------------------------------------------------------- the physics (same as engine/plaza.step)
def shift(a, sy, sx):
    """out[y, x] = a[y - sy, x - sx]; cells from outside the plaza are 0 (walls). a is (B, H, W)."""
    p = F.pad(a, (1, 1, 1, 1))
    return p[:, 1 - sy:1 - sy + P.H, 1 - sx:1 - sx + P.W]


def step(p, waiting, passab, nxt, gate):
    """One step for a batch of plazas. Returns (people, still waiting outside, people through the gate this step)."""
    room = torch.relu(passab * P.CAP - p)
    enter = torch.minimum(waiting[:, None] / P.H, room[:, :, 0])             # the left edge takes only what fits
    p = p + F.pad(enter[:, :, None], (0, P.W - 1))
    waiting = waiting - enter.sum(1)
    room = torch.relu(passab * P.CAP - p)
    want = P.MOVE * p
    out = sum(torch.where(nxt == d, torch.minimum(want, shift(room, -sy, -sx)), 0.0) for d, (sy, sx) in enumerate(DIRS))
    arrive = sum(shift(torch.where(nxt == d, out, 0.0), sy, sx) for d, (sy, sx) in enumerate(DIRS))
    over = torch.clamp(arrive / room.clamp(min=1e-3), min=1.0)              # several cells feeding one share its room
    scale = torch.ones_like(p)
    for d, (sy, sx) in enumerate(DIRS):
        scale = torch.where(nxt == d, 1.0 / shift(over, -sy, -sx).clamp(min=1.0), scale)
    out = out * scale
    arrive = sum(shift(torch.where(nxt == d, out, 0.0), sy, sx) for d, (sy, sx) in enumerate(DIRS))
    p = p - out + arrive
    left = torch.minimum(p, torch.full_like(p, P.GATE)) * gate
    return p - left, waiting, left.sum((1, 2))


def waves(total, steps=P.STEPS):
    """The arrival wave engine.plaza.run uses (people arriving at the left edge per step), for each plaza."""
    w = np.sin(np.linspace(0, np.pi, int(steps * 0.7))) ** 2
    w = np.concatenate([w / w.sum(), np.zeros(steps - len(w))])
    return torch.tensor(np.outer(np.asarray(total), w), dtype=torch.float32)


def run(passab, d, steps=P.STEPS):
    """Roll the physics over the whole wave; returns people (B, steps, H, W) and cumulative through (B, steps)."""
    p = torch.zeros_like(d["clutter"])
    waiting = torch.zeros(len(p))
    frames, thr = [], []
    for t in range(steps):
        waiting = waiting + d["wave"][:, t]
        p, waiting, o = step(p, waiting, passab, d["nxt"], d["gate"])
        frames.append(p); thr.append(o)
    return torch.stack(frames, 1), torch.cumsum(torch.stack(thr, 1), 1)


def survey(d):
    """What the city knows about the plaza: the clutter survey, how far each cell is from the gate, the gate."""
    return torch.stack([d["clutter"], d["dist"] / 50.0, d["gate"]], 1)


# ---------------------------------------------------------------- the models
class Passability(nn.Module):
    """Ours: a small CNN reads the survey image and outputs usable floor per cell in [0, 1] (sigmoid)."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(3, 16, 3, padding=1), nn.Tanh(), nn.Conv2d(16, 16, 3, padding=1), nn.Tanh(), nn.Conv2d(16, 1, 1))
        nn.init.constant_(self.net[-1].bias, 3.0)              # start near the site plan's 1

    def forward(self, d):
        return torch.sigmoid(self.net(survey(d)))[:, 0]

    def predict(self, d):
        return run(self(d), d)[0]


class CNNOnly(nn.Module):
    """Baseline: a CNN predicts the change in people directly from people, arrivals and the survey. No physics."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(5, 32, 3, padding=1), nn.Tanh(), nn.Conv2d(32, 32, 3, padding=1), nn.Tanh(), nn.Conv2d(32, 1, 3, padding=1))

    def predict(self, d):
        p, out = torch.zeros_like(d["clutter"]), []
        edge = torch.zeros_like(p); edge[:, :, 0] = 1
        for t in range(P.STEPS):
            inflow = edge * (d["wave"][:, t] / P.H)[:, None, None] / P.CAP
            x = torch.cat([(p / P.CAP)[:, None], inflow[:, None], survey(d)], 1)
            p = torch.relu(p + 2.0 * self.net(x)[:, 0])
            out.append(p)
        return torch.stack(out, 1)


class Physics:
    """Baseline: the site plan, every cell fully usable (passability 1)."""

    def __call__(self, d):
        return torch.ones_like(d["clutter"])

    def predict(self, d):
        return run(self(d), d)[0]


# ---------------------------------------------------------------- data, training, test
def load():
    z = np.load(DATA / "plaza_train.npz")
    T = lambda k: torch.tensor(z[k], dtype=torch.float32)
    d = {k: T(k) for k in ("people", "clutter", "dist", "gate", "pass_true")}
    d["nxt"] = torch.tensor(z["nxt"], dtype=torch.long)
    d["wave"] = waves(z["total"])
    return d, z["is_test"].astype(bool)


def part(d, idx):
    return {k: v[idx] for k, v in d.items()}


def train(model, d, iters=250, batch=8, lr=1e-2):
    """Roll the whole 20-minute wave and match the simulator's people in every cell (saved every 2nd step)."""
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    r = np.random.default_rng(0)
    n = len(d["people"])
    for i in range(iters):
        b = part(d, torch.tensor(r.integers(n, size=batch)))
        pred = model.predict(b)[:, ::2]
        loss = ((pred - b["people"]) / P.CAP).pow(2).mean() * 100
        opt.zero_grad(); loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if i % 25 == 0:
            print(f"    iter {i:4d}  loss {loss.item():.4f}", flush=True)
    return model


def density(people, passab):
    """People per m2 of USABLE floor (what a crowd actually feels), as in engine.plaza.demo."""
    return people / (passab[:, None] * P.CELL_M2).clamp(min=1e-3)


@torch.no_grad()
def test(name, model, d):
    """Held-out plazas: density error, people created from nothing, danger cells found / missed."""
    pred = model.predict(d)[:, ::2]
    truth_rho = density(d["people"], d["pass_true"])
    if name == "cnn":
        pass_m = torch.ones_like(d["clutter"])                 # no physics, so no idea of usable floor
    else:
        pass_m = model(d)
    rho = density(pred, pass_m)
    err = float((rho - truth_rho).abs().mean())
    arrived = torch.cumsum(d["wave"], 1)[:, ::2]                # people who have reached the plaza so far
    created = float(torch.relu(pred.sum((2, 3)) - arrived).max(1).values.mean())
    hot_t = (truth_rho >= P.DANGER).any(1)
    hot_p = (rho >= P.DANGER).any(1)
    return {"density_error": round(err, 3), "people_created": round(created, 1),
            "danger_cells_true": int(hot_t.sum()), "danger_cells_found": int((hot_t & hot_p).sum()),
            "danger_cells_missed": int((hot_t & ~hot_p).sum()), "false_alarm_cells": int((~hot_t & hot_p).sum()),
            "plazas": len(pred)}


@torch.no_grad()
def demo(model):
    """Our predicted density for the demo plaza, in the shape of plaza_demo.json (every 6 steps = 30 s)."""
    pl = P.make_plaza(7)
    demo_json = json.loads((DATA / "plaza_demo.json").read_text())
    T = lambda x, dt=torch.float32: torch.tensor(np.asarray(x), dtype=dt)[None]
    d = {"clutter": T(pl["clutter"]), "dist": T(pl["dist"]), "gate": T(pl["gate"], torch.float32),
         "nxt": T(pl["nxt"], torch.long), "wave": waves([demo_json["total_people"]])}
    pas = model(d)
    people, thr = run(pas, d)
    rho = density(people, pas)[0]
    truth = np.array(demo_json["truth"]["density"])
    book = np.array(demo_json["textbook"]["density"])
    ours = rho[::6].numpy()
    hot = lambda a: (a >= P.DANGER).any(0)
    missed_by_book = hot(truth) & ~hot(book)
    return {"simulated": True, "frame_s": 30.0, "density": np.round(ours, 2).tolist(),
            "peak_density": round(float(rho.max()), 2), "danger_cells": int(hot(ours).sum()),
            "passability": np.round(pas[0].numpy(), 2).tolist(),
            "textbook_missed_cells_we_catch": int((missed_by_book & hot(ours)).sum()),
            "textbook_missed_cells": int(missed_by_book.sum()),
            "density_error_vs_truth": round(float(np.abs(ours - truth).mean()), 3),
            "textbook_density_error_vs_truth": round(float(np.abs(book - truth).mean()), 3)}


def main():
    torch.manual_seed(0)
    d, is_test = load()
    tr, te = part(d, torch.tensor(~is_test)), part(d, torch.tensor(is_test))
    ours, box = Passability(), CNNOnly()
    print("training PG-CNN", flush=True); train(ours, tr)
    print("training CNN only", flush=True); train(box, tr, iters=150, lr=3e-3)
    models = {"physics": Physics(), "cnn": box, "pgcnn": ours}
    res = {"models": {k: test(k, m, te) for k, m in models.items()}}
    with torch.no_grad():
        res["passability_error"] = {"site_plan": round(float((1 - te["pass_true"]).abs().mean()), 3),
                                    "pgcnn": round(float((ours(te) - te["pass_true"]).abs().mean()), 3)}
    res["setup"] = {"source": "MAIN engine.plaza (data/crowd/plaza_train.npz)", "train_plazas": int((~is_test).sum()),
                    "test_plazas": int(is_test.sum()), "unseen": "12 plazas never seen in training", "steps": P.STEPS,
                    "dt_s": 5, "grid": [P.H, P.W], "cell_m": 2, "simulated": True}
    print(json.dumps(res, indent=1))
    (OUT / "pgcnn_plaza.json").write_text(json.dumps(res, indent=1))
    dm = demo(ours)
    print({k: v for k, v in dm.items() if not isinstance(v, list)})
    (OUT / "pgcnn_plaza_demo.json").write_text(json.dumps(dm))
    torch.save(ours.state_dict(), OUT / "pgcnn_plaza.pt")


if __name__ == "__main__":
    main()
