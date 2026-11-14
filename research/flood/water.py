"""
WATER layer of the flood twin: forecast street flooding hours ahead.

The physics (conservation of water), per 500 m x 500 m cell, every 5 minutes:
    depth_next = depth + rain - drained - flowed_out + flowed_in
    drained    = min(depth, DRAIN * efficiency)          storm drains
    flow       = water moves to lower neighbours, in proportion to the height difference,
                 never more than the cell holds              (water is never created or lost)

What the city's physics model does NOT know: many drains are clogged (garbage, silt, old pipes).
So the engineer's model assumes efficiency = 1 everywhere and under-predicts floods.

Three forecasters (Yu & Wang, PNAS 2024):
    physics   efficiency = 1 everywhere
    AI only   a CNN that predicts the change in depth directly (no physics)
    ours      physics, with efficiency learned by a CNN from what the city knows about each cell
              (height, how built-up it is, drain age). Efficiency is squeezed into [0, 1], so the
              learned part can only REMOVE drainage, never invent water: conservation holds by design.
Trained by rolling the physics forward and backpropagating through it ("differentiable physics").

Run from repo root:  .venv/Scripts/python -m research.flood.water   (trains, tests, saves model)
"""
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

OUT = Path(__file__).parent
NX, NY = 40, 28                 # 20 km x 14 km city, 0.5 km cells
DT_MIN = 5
DRAIN = 0.0025                  # m per step a healthy drain removes (~30 mm/h)
FLOW_K = 0.25                   # share of the height difference that moves per step
FLOOD_M = 0.30                  # 30 cm on a street = cars stall, people should not walk
torch.set_num_threads(4)


# ---------------------------------------------------------------- the city
def smooth_noise(seed, scale=6):
    g = np.random.default_rng(seed).normal(size=(NY // scale + 3, NX // scale + 3))
    yy, xx = np.mgrid[0:NY, 0:NX] / scale
    i, j = yy.astype(int), xx.astype(int)
    fy, fx = yy - i, xx - j
    return (g[i, j] * (1 - fy) * (1 - fx) + g[i + 1, j] * fy * (1 - fx) + g[i, j + 1] * (1 - fy) * fx + g[i + 1, j + 1] * fy * fx)


def make_city():
    yy, xx = np.mgrid[0:NY, 0:NX].astype(float)
    river_y = 14 + 4 * np.sin(xx / 6.5)                        # a river winding west -> east
    z = 920 - 0.12 * xx + 3.0 * smooth_noise(1)                # gentle slope east + hills
    z -= 7 * np.exp(-((yy - river_y) / 2.2) ** 2)              # river valley
    lakes = [(8, 6), (31, 21), (22, 5), (12, 22)]              # old lakes, now half built over
    for lx, ly in lakes:
        z -= 4 * np.exp(-(((xx - lx) ** 2 + (yy - ly) ** 2) / 6))
    river = np.abs(yy - river_y) < 1.0
    built = np.clip(0.5 + 0.6 * smooth_noise(2, 5) - 0.4 * river, 0, 1)    # how built-up (0..1)
    age = np.clip(0.5 + 0.6 * smooth_noise(3, 7), 0, 1)                    # drain age (0 new .. 1 old)
    # hidden truth: dense, old areas have clogged drains
    eff = 1 / (1 + np.exp(-(3.0 - 4.0 * built - 3.0 * age)))
    eff[river] = 1.0
    return dict(z=z, river=river, built=built, age=age, eff_true=eff)


CITY = make_city()


def storm(seed, steps=96):
    """Rain in metres per step for each cell. A storm cell crossing the city + background rain."""
    r = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:NY, 0:NX].astype(float)
    peak = r.uniform(0.004, 0.009)                     # 50-110 mm/h at the core
    y0, vy = r.uniform(4, 24), r.uniform(-0.08, 0.08)
    vx = r.uniform(0.25, 0.6)                          # cells per step, west -> east
    start, dur = r.integers(6, 24), r.integers(30, 60)
    width = r.uniform(5, 9)
    rain = np.zeros((steps, NY, NX))
    for t in range(steps):
        k = t - start
        if 0 <= k < dur:
            cx, cy = -5 + vx * k, y0 + vy * k
            ramp = np.sin(np.pi * k / dur)
            rain[t] = peak * ramp * (0.25 + np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * width ** 2))))
    return rain


# ---------------------------------------------------------------- the physics (torch, so we can learn through it)
Z = torch.tensor(CITY["z"], dtype=torch.float32)
RIVER = torch.tensor(CITY["river"], dtype=torch.float32)


def step(h, rain, eff):
    """One 5-minute step of conservation of water. h, rain, eff: (B, NY, NX)."""
    h = h + rain
    h = h - torch.minimum(h, DRAIN * eff)                       # drains (river cells drain freely)
    s = Z + h                                                   # water surface height
    pad = torch.nn.functional.pad(s.unsqueeze(1), (1, 1, 1, 1), mode="replicate").squeeze(1)
    nb = [pad[:, :-2, 1:-1], pad[:, 2:, 1:-1], pad[:, 1:-1, :-2], pad[:, 1:-1, 2:]]  # up, down, left, right
    diff = [torch.relu(s - n) for n in nb]
    total = sum(diff) + 1e-9
    out = torch.minimum(h, FLOW_K * total)                      # can't send more than you hold
    share = [out * d / total for d in diff]
    # what each neighbour sends me = its share towards me
    def from_dir(x, dy, dx):
        x = torch.nn.functional.pad(x.unsqueeze(1), (1, 1, 1, 1)).squeeze(1)
        return x[:, 1 + dy:NY + 1 + dy, 1 + dx:NX + 1 + dx]
    inflow = from_dir(share[1], -1, 0) + from_dir(share[0], 1, 0) + from_dir(share[3], 0, -1) + from_dir(share[2], 0, 1)
    h = h - out + inflow
    h = h * (1 - 0.5 * RIVER * (torch.arange(NX) >= NX - 2).float())   # river carries water out of the city
    return h


def run(h0, rain, eff):
    hs, h = [], h0
    for k in range(rain.shape[1]):
        h = step(h, rain[:, k], eff)
        hs.append(h)
    return torch.stack(hs, 1)


# ---------------------------------------------------------------- the models
FEATS = torch.tensor(np.stack([(CITY["z"] - CITY["z"].mean()) / 5, CITY["built"], CITY["age"], CITY["river"]]), dtype=torch.float32)


class Efficiency(nn.Module):
    """Ours: a small CNN reads what the city knows about each cell and outputs drain efficiency in [0, 1]."""
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(4, 16, 3, padding=1), nn.Tanh(), nn.Conv2d(16, 16, 3, padding=1), nn.Tanh(), nn.Conv2d(16, 1, 1))
        nn.init.constant_(self.net[-1].bias, 2.0)               # start near "drains work"
    def forward(self):
        return torch.sigmoid(self.net(FEATS.unsqueeze(0)))[:, 0]


class BlackBox(nn.Module):
    """AI only: a CNN predicts the change in depth from depth, rain and the same city features."""
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(nn.Conv2d(6, 32, 3, padding=1), nn.Tanh(), nn.Conv2d(32, 32, 3, padding=1), nn.Tanh(), nn.Conv2d(32, 1, 3, padding=1))
    def run(self, h0, rain):
        hs, h = [], h0
        for k in range(rain.shape[1]):
            x = torch.cat([h.unsqueeze(1) * 5, rain[:, k].unsqueeze(1) * 200, FEATS.unsqueeze(0).expand(len(h), -1, -1, -1)], 1)
            h = torch.relu(h + 0.02 * self.net(x)[:, 0])
            hs.append(h)
        return torch.stack(hs, 1)


EFF_TRUE = torch.tensor(CITY["eff_true"], dtype=torch.float32)
ONES = torch.ones(NY, NX)


def truth_run(rain):
    with torch.no_grad():
        return run(torch.zeros(1, NY, NX), torch.tensor(rain, dtype=torch.float32).unsqueeze(0), EFF_TRUE.unsqueeze(0))[0]


def windows(storms, horizon, every):
    h0, rain, target = [], [], []
    for r in storms:
        hs = truth_run(r)
        hs = torch.cat([torch.zeros(1, NY, NX), hs])
        rt = torch.tensor(r, dtype=torch.float32)
        for t in range(0, len(r) - horizon, every):
            if hs[t:t + horizon + 1].max() < 0.02:
                continue                                        # skip dry windows
            h0.append(hs[t]); rain.append(rt[t:t + horizon]); target.append(hs[t + 1:t + horizon + 1])
    return torch.stack(h0), torch.stack(rain), torch.stack(target)


def train(model, data, steps, kind, hide=None):
    """hide = cells whose errors the model never sees in training (generalisation test)."""
    h0, rain, target = data
    keep = torch.ones(NY, NX) if hide is None else (~hide).float()
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    for i in range(steps):
        idx = torch.randint(len(h0), (16,))
        pred = run(h0[idx], rain[idx], model().expand(len(idx), -1, -1)) if kind == "ours" else model.run(h0[idx], rain[idx])
        loss = (((pred - target[idx]) ** 2) * keep).mean() * 1e3
        opt.zero_grad(); loss.backward(); opt.step()
    return model


@torch.no_grad()
def evaluate(predict, data, mask=None):
    """How well each model calls flooded streets 2 hours ahead (the decision that matters)."""
    h0, rain, target = data
    pred = predict(h0, rain)
    p, y = pred[:, -1] >= FLOOD_M, target[:, -1] >= FLOOD_M
    if mask is not None:
        p, y = p[:, mask], y[:, mask]
    hit = (p & y).sum().item(); missed = (~p & y).sum().item(); false = (p & ~y).sum().item()
    return {"flooded_cells_caught_pct": round(100 * hit / max(1, hit + missed), 1),
            "false_alarm_pct": round(100 * false / max(1, hit + false), 1),
            "depth_error_cm": round(100 * (pred[:, -1] - target[:, -1]).abs().mean().item(), 2)}


def main():
    torch.manual_seed(0)
    H = 24                                                       # 2 hours ahead
    train_data = windows([storm(s) for s in range(20)], 12, 6)
    test_data = windows([storm(s) for s in range(100, 112)], H, 6)
    east = torch.zeros(NY, NX, dtype=torch.bool); east[:, 28:] = True     # district hidden from training

    ours, box = Efficiency(), BlackBox()
    train(ours, train_data, 300, "ours")
    train(box, train_data, 300, "box")
    # generalisation test: train another copy of each WITHOUT ever seeing the east district's errors
    ours_w, box_w = Efficiency(), BlackBox()
    train(ours_w, train_data, 300, "ours", hide=east); train(box_w, train_data, 300, "box", hide=east)

    models = {
        "Physics only": lambda h, r: run(h, r, ONES.expand(len(h), -1, -1)),
        "AI only (CNN)": lambda h, r: box.run(h, r),
        "Physics + AI (ours)": lambda h, r: run(h, r, ours().expand(len(h), -1, -1)),
    }
    models_w = {
        "Physics only": models["Physics only"],
        "AI only (CNN)": lambda h, r: box_w.run(h, r),
        "Physics + AI (ours)": lambda h, r: run(h, r, ours_w().expand(len(h), -1, -1)),
    }
    results = {"Unseen storms, 2 h ahead": {k: evaluate(f, test_data) for k, f in models.items()},
               "District never seen in training (east), 2 h ahead": {k: evaluate(f, test_data, east) for k, f in models_w.items()}}
    with torch.no_grad():
        eff = ours()[0].numpy()
    results["learned_drain_efficiency_error"] = round(float(np.abs(eff - CITY["eff_true"]).mean()), 3)
    results["setup"] = {"grid": [NX, NY], "cell_km": 0.5, "step_min": DT_MIN, "train_storms": 20, "test_storms": 12}

    for name, block in results.items():
        if isinstance(block, dict) and "Physics only" in block:
            print(f"\n{name}")
            for k, v in block.items():
                print(f"  {k:22} caught {v['flooded_cells_caught_pct']:5.1f}%  false alarms {v['false_alarm_pct']:5.1f}%  depth error {v['depth_error_cm']:5.2f} cm")
    print("\nlearned drain efficiency, avg error vs hidden truth:", results["learned_drain_efficiency_error"])
    (OUT / "water_results.json").write_text(json.dumps(results, indent=2))
    torch.save(ours.state_dict(), OUT / "efficiency_cnn.pt")
    np.save(OUT / "eff_learned.npy", eff)


if __name__ == "__main__":
    main()
