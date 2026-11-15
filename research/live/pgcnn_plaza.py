"""
PG-CNN for the Crush-Point Finder (QueuePilot Live, docs/STAMPEDE.md version 3).
Question: inside the plaza in front of the gate, WHERE will people be crushed?

PHYSICS (hard-coded; exactly engine/plaza.py, written in torch so we can learn through it)
  continuity: people move cell to cell, nobody is created or lost         flux = rho * v
  Weidmann (1993): v(rho) = v0 (1 - exp(-gamma (1/rho - 1/rho_max)))       v0 1.34 m/s, gamma 1.913, rho_max 5.4
  Hughes (2002): everyone heads down the quickest path to the gate, |grad T| = 1/v(rho); re-solved every 10 s with
                 engine.plaza.quickest_paths on the current (detached) speeds, then used as a fixed input
  a cell holds at most usable floor x rho_max; the gate passes 1.3 people/s per metre

LEARNED (bounded)
  u(x) = sigmoid(CNN(survey image: clutter, gate)) in [0, 1] = share of each cell's floor that is really usable.
  The network can only shrink the floor. It cannot move, create or delete a person.

Baselines: "physics on the plan as drawn" (u = 1, MAIN's models.hughes) and "CNN only" (predicts the change in
density frame to frame, no physics). Trained by rolling the physics forward and backpropagating through it.
Tested on 12 plazas never seen in training, and on the demo plaza.

    python -m engine.plaza                     # once: MAIN's data -> data/crowd/plaza_train.npz
    python -m research.live.pgcnn_plaza        # trains, tests, writes pgcnn_plaza.json (+ pgcnn_plaza.pt)
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
CELL = P.DX * P.DX


# ---------------------------------------------------------------- the physics (same as engine.plaza.step)
def shift(a, sy, sx):
    """out[y, x] = a[y - sy, x - sx]; nothing comes in through the walls. a is (B, H, W)."""
    return F.pad(a, (1, 1, 1, 1))[:, 1 - sy:1 - sy + P.H, 1 - sx:1 - sx + P.W]


def weidmann(rho):
    rho = rho.clamp(1e-3, P.RHO_MAX - 1e-3)
    return (P.V0 * (1 - torch.exp(-P.GAMMA * (1 / rho - 1 / P.RHO_MAX)))).clamp(0.03, P.V0)


def step(p, waiting, usable, nxt, gate):
    """One second for a batch of plazas. usable = usable floor in m2 per cell."""
    cap = usable * P.RHO_MAX
    enter = torch.minimum(waiting[:, None] / P.H, torch.relu(cap[:, :, 0] - p[:, :, 0]))
    p = p + F.pad(enter[:, :, None], (0, P.W - 1))
    waiting = waiting - enter.sum(1)
    v = weidmann(p / usable.clamp(min=1e-6))
    want = p * torch.clamp(v * P.DT / P.DX, max=1.0)
    room = torch.relu(cap - p)
    out = sum(torch.where(nxt == d, torch.minimum(want, shift(room, -sy, -sx)), 0.0) for d, (sy, sx) in enumerate(P.DIRS))
    arrive = sum(shift(torch.where(nxt == d, out, 0.0), sy, sx) for d, (sy, sx) in enumerate(P.DIRS))
    over = torch.clamp(arrive / room.clamp(min=1e-3), min=1.0)
    scale = torch.ones_like(p)
    for d, (sy, sx) in enumerate(P.DIRS):
        scale = torch.where(nxt == d, 1.0 / shift(over, -sy, -sx).clamp(min=1.0), scale)
    out = out * scale
    arrive = sum(shift(torch.where(nxt == d, out, 0.0), sy, sx) for d, (sy, sx) in enumerate(P.DIRS))
    p = p - out + arrive
    left = torch.minimum(p, torch.full_like(p, P.GATE_RATE)) * gate
    return p - left, waiting, v


def waves(total, steps=P.STEPS):
    w = np.sin(np.linspace(0, np.pi, int(steps * 0.7))) ** 2
    w = np.concatenate([w / w.sum(), np.zeros(steps - len(w))])
    return torch.tensor(np.outer(np.asarray(total), w), dtype=torch.float32)


def run(share, d, steps=P.STEPS):
    """Roll the physics with a believed usable share (B, H, W). Returns people per m2 of the BELIEVED usable floor
    every 30 s (B, frames, H, W): what the model would show, using nothing it is not allowed to know."""
    usable = share * CELL
    gate_np = d["gate"].numpy().astype(bool)
    p = torch.zeros_like(share)
    waiting = torch.zeros(len(p))
    frames = []
    for t in range(steps):
        if t % P.REROUTE == 0:                                       # Hughes routing on the current speeds (fixed input)
            sp = weidmann(p / usable.clamp(min=1e-6)).detach().numpy()
            nxt = torch.tensor(np.stack([P.quickest_paths(sp[b], gate_np[b])[0] for b in range(len(p))]))
        waiting = waiting + d["wave"][:, t]
        p, waiting, _ = step(p, waiting, usable, nxt, d["gate"])
        if t % P.SAVE == P.SAVE - 1:
            frames.append(p / usable.clamp(min=1e-6))
    return torch.stack(frames, 1)


def survey(d):
    return torch.stack([d["clutter"], d["gate"]], 1)


# ---------------------------------------------------------------- the models
class UsableFloor(nn.Module):
    """Ours: a small CNN reads the survey image and outputs the usable share of each cell in [0, 1] (sigmoid)."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(2, 16, 3, padding=1), nn.Tanh(), nn.Conv2d(16, 16, 3, padding=1), nn.Tanh(), nn.Conv2d(16, 1, 1))
        nn.init.constant_(self.net[-1].bias, 3.0)                    # start near the site plan's "all usable"

    def forward(self, d):
        return torch.sigmoid(self.net(survey(d)))[:, 0]

    def predict(self, d, steps=P.STEPS):
        return run(self(d), d, steps)


class CNNOnly(nn.Module):
    """Baseline: a CNN predicts the next 30 s density frame from the last one, the arrivals and the survey. No physics."""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(4, 32, 3, padding=1), nn.Tanh(), nn.Conv2d(32, 32, 3, padding=1), nn.Tanh(), nn.Conv2d(32, 1, 3, padding=1))

    def predict(self, d, steps=P.STEPS):
        rho, out = torch.zeros_like(d["clutter"]), []
        edge = torch.zeros_like(rho); edge[:, :, 0] = 1
        per = d["wave"].unfold(1, P.SAVE, P.SAVE).sum(2)             # people arriving in each 30 s window
        for k in range(steps // P.SAVE):
            inflow = edge * (per[:, k] / P.H / CELL)[:, None, None]
            x = torch.cat([rho[:, None], inflow[:, None], survey(d)], 1)
            rho = torch.relu(rho + self.net(x)[:, 0])
            out.append(rho)
        return torch.stack(out, 1)


# ---------------------------------------------------------------- data, training, test
def load():
    z = np.load(DATA / "plaza_train.npz")
    T = lambda k: torch.tensor(z[k], dtype=torch.float32)
    d = {k: T(k) for k in ("density", "clutter", "gate", "usable_share_true")}
    d["wave"] = waves(z["total"])
    d["total"] = T("total")
    return d, z["is_test"].astype(bool)


def part(d, idx):
    return {k: v[idx] for k, v in d.items()}


def train(model, d, iters, batch, steps, lr):
    """Roll the first `steps` seconds (the build-up and the crush) and match the camera-like density frames."""
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    r = np.random.default_rng(0)
    n = len(d["density"])
    k = steps // P.SAVE
    for i in range(iters):
        b = part(d, torch.tensor(r.integers(n, size=batch)))
        loss = ((model.predict(b, steps) - b["density"][:, :k]) ** 2).mean()
        opt.zero_grad(); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step()
        if i % 10 == 0:
            print(f"    iter {i:4d}  loss {loss.item():.4f}", flush=True)
    return model


def compare(truth, pred):
    """engine.plaza.compare, summed over plazas: density error, crush cells found / missed / false alarms."""
    t_hot, p_hot = (truth >= P.DANGER).any(1), (pred >= P.DANGER).any(1)
    return dict(density_error=round(float((truth - pred).abs().mean()), 3), crush_cells_true=int(t_hot.sum()),
                found=int((t_hot & p_hot).sum()), missed=int((t_hot & ~p_hot).sum()), false_alarms=int((~t_hot & p_hot).sum()))


@torch.no_grad()
def main():
    torch.manual_seed(0)
    d, is_test = load()
    tr, te = part(d, torch.tensor(~is_test)), part(d, torch.tensor(is_test))
    ours, box = UsableFloor(), CNNOnly()
    with torch.enable_grad():
        print("training PG-CNN", flush=True); train(ours, tr, iters=60, batch=6, steps=720, lr=2e-2)
        print("training CNN only", flush=True); train(box, tr, iters=300, batch=16, steps=P.STEPS, lr=3e-3)
    held = {"plan_as_drawn": compare(te["density"], run(torch.ones_like(te["clutter"]), te)),
            "cnn_only": compare(te["density"], box.predict(te)),
            "pgcnn": compare(te["density"], ours.predict(te)),
            "plazas": int(is_test.sum())}
    held["usable_share_error"] = {"plan_as_drawn": round(float((1 - te["usable_share_true"]).abs().mean()), 3),
                                  "pgcnn": round(float((ours(te) - te["usable_share_true"]).abs().mean()), 3)}
    # the demo plaza (seed 7, never in training), same shape as plaza_demo.json models.*
    demo = json.loads((DATA / "plaza_demo.json").read_text())
    pl = P.make_plaza(7)
    dd = {"clutter": torch.tensor(pl["clutter"])[None], "gate": torch.tensor(pl["gate"], dtype=torch.float32)[None],
          "wave": waves([demo["total_people"]])}
    share = ours(dd)
    pred = run(share, dd)
    truth = torch.tensor(demo["truth"]["density"])[None]
    res = dict(label="PG-CNN (crowd physics + learned usable floor)", simulated=True,
               density=np.round(pred[0].numpy(), 2).tolist(), **compare(truth, pred),
               usable_share_learned=np.round(share[0].numpy(), 2).tolist(), held_out=held,
               setup={"source": "MAIN engine.plaza v3 (data/crowd/plaza_train.npz)", "train_plazas": int((~is_test).sum()),
                      "test_plazas": int(is_test.sum()), "train_window_s": 720, "dt_s": P.DT, "simulated": True})
    print(json.dumps({k: v for k, v in res.items() if k not in ("density", "usable_share_learned")}, indent=1), flush=True)
    (OUT / "pgcnn_plaza.json").write_text(json.dumps(res))
    torch.save(ours.state_dict(), OUT / "pgcnn_plaza.pt")


if __name__ == "__main__":
    main()
