"""
PLAZA layer of QueuePilot Live (the PG-CNN's job): the crowd INSIDE the critical plaza, on a 2 m grid.
The venue graph (PG-GNN) says how many people reach the plaza; this layer says WHERE in the plaza they pile up.

Physics, per cell, every step (dt = 5 s):
    people_next = people + arriving - leaving          (conservation of people)
    each cell sends a share MOVE of its people to its neighbour that is closest to the gate,
    but a cell takes in only what it has room for:  room = passability x cell capacity - people
    gate cells let GATE people per step out of the plaza.
What the site plan does NOT show: clutter (barricade stubs, parked vehicles, stalls) that narrows the way.
HIDDEN truth: passability falls where clutter is dense (true_pass). The textbook assumes 1 everywhere.
The PG-CNN learns passability in [0, 1] from the survey image (clutter channel) through the same physics step.

Run from repo root:  python -m engine.plaza    (writes data/crowd/plaza_demo.json, plaza_sample.npz, plaza_train.npz)
"""
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent.parent / "data" / "crowd"
H, W = 20, 32               # 40 m x 64 m plaza, 2 m cells
CELL_M2 = 4.0
MAX_DENSITY = 6.0
DANGER = 4.0
CAP = MAX_DENSITY * CELL_M2  # people one cell can hold
MOVE = 0.6                   # share of a cell's people that try to step forward each step
STEPS = 240                  # 20 minutes
GATE = 6.5                   # people per gate cell per step (1.3 people/s per metre x 2 m x 5 s, halved for turnstiles)


def true_pass(clutter):
    """HIDDEN: how much of a cell is really usable. The PG-CNN is never told this formula."""
    return 1.0 - 0.75 * clutter ** 2


def make_plaza(seed):
    """A plaza: people enter along the left edge, the gate is a short opening on the right edge.
    Returns dist (steps to the gate), nxt (index of the neighbour to step to), gate mask, clutter image."""
    rng = np.random.default_rng(seed)
    gate = np.zeros((H, W), bool)
    g0 = rng.integers(4, H - 8)
    gate[g0:g0 + 3, W - 1] = True
    clutter = np.zeros((H, W))
    for _ in range(rng.integers(3, 7)):                           # blobs of clutter
        cy, cx, r = rng.integers(0, H), rng.integers(6, W - 2), rng.uniform(2, 5)
        yy, xx = np.mgrid[0:H, 0:W]
        clutter = np.maximum(clutter, rng.uniform(0.5, 1.0) * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * r ** 2)))
    yy, xx = np.mgrid[0:H, 0:W]
    gy = np.clip(yy, g0, g0 + 2)
    dist = np.abs(yy - gy) + (W - 1 - xx)                         # walking steps to the gate
    nxt = np.zeros((H, W), int)                                   # 0 right, 1 up, 2 down, 3 stay (gate)
    nxt[(yy > g0 + 2)] = 1
    nxt[(yy < g0)] = 2
    nxt[(yy >= g0) & (yy <= g0 + 2)] = 0
    nxt[gate] = 3
    return dict(gate=gate, clutter=clutter.astype(np.float32), dist=dist.astype(np.float32), nxt=nxt, pass_true=true_pass(clutter).astype(np.float32))


def shift(a, sy, sx):
    """Move a grid by (sy, sx) cells; cells that come in from outside the plaza are 0 (walls, no wrap-around)."""
    out = np.zeros_like(a)
    ys = slice(max(sy, 0), H + min(sy, 0)); yd = slice(max(-sy, 0), H + min(-sy, 0))
    xs = slice(max(sx, 0), W + min(sx, 0)); xd = slice(max(-sx, 0), W + min(-sx, 0))
    out[ys, xs] = a[yd, xd]
    return out


DIRS = [(0, 1), (-1, 0), (1, 0)]            # where a cell sends people: right, up, down (toward the gate)


def step(p, waiting, passab, pl):
    """One step of the plaza physics (numpy). The PG-CNN uses the same step with its own passability.
    waiting = people queued outside the left edge. Returns (people, still waiting outside, people through the gate)."""
    room = np.maximum(passab * CAP - p, 0.0)
    enter = np.minimum(waiting / H, room[:, 0])                    # the left edge takes in only what it has room for
    p = p.copy()
    p[:, 0] += enter
    waiting = waiting - enter.sum()
    room = np.maximum(passab * CAP - p, 0.0)
    want = MOVE * p
    out = np.zeros_like(p)
    for d, (sy, sx) in enumerate(DIRS):
        out += np.where(pl["nxt"] == d, np.minimum(want, shift(room, -sy, -sx)), 0.0)   # limited by room in the next cell
    arrive = sum(shift(np.where(pl["nxt"] == d, out, 0.0), sy, sx) for d, (sy, sx) in enumerate(DIRS))
    over = np.maximum(arrive / np.maximum(room, 1e-9), 1.0)       # several cells feeding one cell share its room
    scale = np.ones_like(p)
    for d, (sy, sx) in enumerate(DIRS):
        scale = np.where(pl["nxt"] == d, 1.0 / np.maximum(shift(over, -sy, -sx), 1.0), scale)
    out = out * scale
    arrive = sum(shift(np.where(pl["nxt"] == d, out, 0.0), sy, sx) for d, (sy, sx) in enumerate(DIRS))
    p = p - out + arrive
    left = np.minimum(p, GATE) * pl["gate"]                       # through the gate
    return p - left, waiting, float(left.sum())


def run(pl, total, passab=None, steps=STEPS):
    """Crowd in the plaza for one arrival wave of `total` people.
    Returns people[steps, H, W], cumulative people through the gate, people waiting outside per step."""
    passab = pl["pass_true"] if passab is None else passab
    wave = np.sin(np.linspace(0, np.pi, int(steps * 0.7))) ** 2
    wave = np.concatenate([wave / wave.sum() * total, np.zeros(steps - len(wave))])
    p = np.zeros((H, W), np.float32)
    waiting, frames, through, outside = 0.0, [], [], []
    for t in range(steps):
        waiting += wave[t]
        p, waiting, out = step(p, waiting, passab, pl)
        frames.append(p); through.append(out); outside.append(waiting)
    return np.array(frames, np.float32), np.cumsum(through), np.array(outside)


def dataset(n=60, name="plaza_train"):
    rows = []
    rng = np.random.default_rng(1)
    for i in range(n):
        pl = make_plaza(100 + i)
        total = float(rng.uniform(1500, 4500))
        frames, _, _ = run(pl, total)
        rows.append((pl, total, frames))
    n_test = max(1, n // 5)
    np.savez_compressed(
        OUT / f"{name}.npz", is_test=np.array([i >= n - n_test for i in range(n)], np.int8),
        total=np.array([r[1] for r in rows], np.float32), people=np.array([r[2][::2] for r in rows], np.float32),   # every 2nd step
        clutter=np.array([r[0]["clutter"] for r in rows]), dist=np.array([r[0]["dist"] for r in rows]),
        nxt=np.array([r[0]["nxt"] for r in rows], np.int8), gate=np.array([r[0]["gate"] for r in rows], np.int8),
        pass_true=np.array([r[0]["pass_true"] for r in rows]))
    print(f"{name}: {n} plazas ({n_test} held out), people {np.array([r[2][::2] for r in rows]).shape}")


def demo():
    """One plaza for the page: truth vs what the textbook (no clutter) predicts."""
    pl = make_plaza(7)
    total = 3200.0
    truth, thr, wait = run(pl, total)
    book, thr_b, wait_b = run(pl, total, np.ones((H, W), np.float32))
    usable = pl["pass_true"] * CELL_M2                                 # real standing room in each cell
    eff = lambda f, area: f / area                                     # people per m2 of usable floor
    dens = lambda f, area: np.round(eff(f, area)[::6], 2).tolist()
    peak = lambda f, area: float(eff(f, area).max())
    hot = lambda f, area: int((eff(f, area) >= DANGER).any(0).sum())
    hidden = int(((eff(truth, usable) >= DANGER).any(0) & ~((book / CELL_M2) >= DANGER).any(0)).sum())
    out = dict(simulated=True, height=H, width=W, cell_m=2.0, dt_s=5.0, frame_s=30.0, danger_density=DANGER, max_density=MAX_DENSITY,
               total_people=total, gate=pl["gate"].astype(int).tolist(), clutter=np.round(pl["clutter"], 2).tolist(),
               passability_true=np.round(pl["pass_true"], 2).tolist(),
               truth=dict(density=dens(truth, usable), peak_density=round(peak(truth, usable), 2), danger_cells=hot(truth, usable), through=np.round(thr[::6]).tolist()),
               danger_cells_textbook_misses=hidden,
               textbook=dict(density=dens(book, CELL_M2), peak_density=round(peak(book, CELL_M2), 2), danger_cells=hot(book, CELL_M2), through=np.round(thr_b[::6]).tolist()))
    (OUT / "plaza_demo.json").write_text(json.dumps(out))
    print("demo plaza: truth peak", out["truth"]["peak_density"], "danger cells", out["truth"]["danger_cells"],
          "| textbook peak", out["textbook"]["peak_density"], "danger cells", out["textbook"]["danger_cells"],
          "| danger cells the textbook misses", hidden, "| conservation", round(float(truth[-1].sum() + thr[-1] + wait[-1] - total), 3))


if __name__ == "__main__":
    demo()
    dataset(12, "plaza_sample")
    dataset(60, "plaza_train")
