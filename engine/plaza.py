"""
CRUSH-POINT FINDER (the PG-CNN's job in QueuePilot Live).
Question it answers: "Inside the plaza in front of the gate, WHERE exactly will people be crushed?"
The plaza is a top-down image: a 40 m x 64 m space cut into 2 m cells, like a camera's density map.

The physics is the standard continuum crowd model (Hughes 2002) with a measured speed law (Weidmann 1993):
  1. Conservation of people (continuity equation):      d(rho)/dt + div(rho * v) = 0
  2. Speed falls with density (Weidmann):               v(rho) = v0 * (1 - exp(-gamma * (1/rho - 1/rho_max)))
                                                        v0 = 1.34 m/s, gamma = 1.913 /m2, rho_max = 5.4 /m2
  3. People take the QUICKEST path, not the shortest (eikonal equation):   |grad T| = 1 / v(rho),  T = 0 at the gate
     so the route bends around dense patches. Solved on the grid with Dijkstra, every 10 s.
  4. Crowd pressure (Helbing et al. 2007), the crush indicator:            P = rho * Var(v)
What the site plan does NOT show: clutter (barricade stubs, parked vehicles, stalls) that takes away floor.
HIDDEN truth: usable floor share falls where clutter is dense (true_pass). The textbook assumes all floor is usable.
The PG-CNN learns the usable share in [0, 1] from the survey image, inside this same physics.

Run from repo root:  python -m engine.plaza    (writes data/crowd/plaza_demo.json, plaza_sample.npz, plaza_train.npz)
All numbers are simulated. Constants are from the cited papers; verify the citations before quoting them.
"""
import heapq
import json
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent.parent / "data" / "crowd"
H, W = 20, 32
DX = 2.0                     # metres per cell
DT = 1.0                     # seconds per step
STEPS = 1200                 # 20 minutes
V0, GAMMA, RHO_MAX = 1.34, 1.913, 5.4      # Weidmann (1993)
DANGER = 4.0                 # people per m2
GATE_RATE = 1.3 * DX * DT    # people per gate cell per step (1.3 people/s per metre of gate)
REROUTE = 10                 # re-solve the quickest paths every 10 s
SAVE = 30                    # save a frame every 30 s
DIRS = [(0, 1), (-1, 0), (1, 0), (0, -1)]


def weidmann(rho):
    """Walking speed (m/s) at density rho (people per m2 of usable floor)."""
    rho = np.clip(rho, 1e-3, RHO_MAX - 1e-3)
    return np.clip(V0 * (1 - np.exp(-GAMMA * (1 / rho - 1 / RHO_MAX))), 0.03, V0)


def true_pass(clutter):
    """HIDDEN: share of a cell's floor that is really usable. The PG-CNN is never told this formula."""
    return 1.0 - 0.75 * clutter ** 2


def make_plaza(seed):
    """People enter along the left edge; the gate is a 6 m opening on the right edge; blobs of clutter in between."""
    rng = np.random.default_rng(seed)
    gate = np.zeros((H, W), bool)
    g0 = int(rng.integers(4, H - 8))
    gate[g0:g0 + 3, W - 1] = True
    yy, xx = np.mgrid[0:H, 0:W]
    clutter = np.zeros((H, W))
    for _ in range(int(rng.integers(3, 7))):
        cy, cx, r = rng.integers(0, H), rng.integers(6, W - 2), rng.uniform(2, 5)
        clutter = np.maximum(clutter, rng.uniform(0.5, 1.0) * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * r ** 2)))
    return dict(gate=gate, clutter=clutter.astype(np.float32), pass_true=true_pass(clutter).astype(np.float32))


def quickest_paths(speed, gate):
    """Eikonal equation on the grid: travel time T to the gate when each cell is crossed at its own speed.
    Returns nxt[H, W] = which neighbour to step to (index into DIRS, -1 at the gate)."""
    T = np.full((H, W), np.inf)
    nxt = np.full((H, W), -1)
    heap = []
    for y, x in zip(*np.nonzero(gate)):
        T[y, x] = 0.0
        heap.append((0.0, int(y), int(x)))
    heapq.heapify(heap)
    while heap:
        t, y, x = heapq.heappop(heap)
        if t > T[y, x]:
            continue
        for d, (sy, sx) in enumerate(DIRS):
            ny, nx = y - sy, x - sx                       # the neighbour that would step (sy, sx) to reach (y, x)
            if 0 <= ny < H and 0 <= nx < W:
                t2 = t + DX / speed[ny, nx]
                if t2 < T[ny, nx]:
                    T[ny, nx] = t2
                    nxt[ny, nx] = d
                    heapq.heappush(heap, (t2, ny, nx))
    return nxt, T


def shift(a, sy, sx):
    """Move a grid by (sy, sx) cells; nothing wraps around the walls."""
    out = np.zeros_like(a)
    ys = slice(max(sy, 0), H + min(sy, 0)); yd = slice(max(-sy, 0), H + min(-sy, 0))
    xs = slice(max(sx, 0), W + min(sx, 0)); xd = slice(max(-sx, 0), W + min(-sx, 0))
    out[ys, xs] = a[yd, xd]
    return out


def step(p, waiting, usable, nxt, gate):
    """One second of the Hughes model. p = people per cell, usable = usable floor (m2) per cell.
    Returns people, people still waiting outside, people through the gate, speed field."""
    cap = usable * RHO_MAX
    enter = np.minimum(waiting / H, np.maximum(cap[:, 0] - p[:, 0], 0))     # the left edge takes what it has room for
    p = p.copy()
    p[:, 0] += enter
    waiting -= enter.sum()
    v = weidmann(p / np.maximum(usable, 1e-6))
    want = p * np.minimum(1.0, v * DT / DX)                                  # continuity: flux = rho * v
    room = np.maximum(cap - p, 0)
    out = np.zeros_like(p)
    for d, (sy, sx) in enumerate(DIRS):
        out += np.where(nxt == d, np.minimum(want, shift(room, -sy, -sx)), 0.0)
    arrive = sum(shift(np.where(nxt == d, out, 0.0), sy, sx) for d, (sy, sx) in enumerate(DIRS))
    over = np.maximum(arrive / np.maximum(room, 1e-9), 1.0)                  # cells feeding one cell share its room
    scale = np.ones_like(p)
    for d, (sy, sx) in enumerate(DIRS):
        scale = np.where(nxt == d, 1.0 / np.maximum(shift(over, -sy, -sx), 1.0), scale)
    out *= scale
    arrive = sum(shift(np.where(nxt == d, out, 0.0), sy, sx) for d, (sy, sx) in enumerate(DIRS))
    p = p - out + arrive
    left = np.minimum(p, GATE_RATE) * gate
    return p - left, waiting, float(left.sum()), v


def pressure(rho, v):
    """Crowd pressure P = rho * Var(v) (Helbing 2007). Variance of speed over each cell's 3 x 3 neighbourhood."""
    m = sum(shift(v, sy, sx) for sy in (-1, 0, 1) for sx in (-1, 0, 1)) / 9
    m2 = sum(shift(v * v, sy, sx) for sy in (-1, 0, 1) for sx in (-1, 0, 1)) / 9
    return rho * np.maximum(m2 - m * m, 0)


def run(pl, total, pass_used=None, quickest=True, steps=STEPS):
    """One arrival wave of `total` people.
    pass_used  usable floor share the MODEL believes (None = the hidden truth)      quickest  False = everyone walks straight
    Returns density[frames, H, W] (people per m2 of REAL usable floor), pressure[frames, H, W], through[frames], waiting[frames]."""
    belief = pl["pass_true"] if pass_used is None else pass_used
    usable = belief * DX * DX
    real = pl["pass_true"] * DX * DX
    wave = np.sin(np.linspace(0, np.pi, int(steps * 0.7))) ** 2
    wave = np.concatenate([wave / wave.sum() * total, np.zeros(steps - len(wave))])
    p = np.zeros((H, W))
    waiting, done = 0.0, 0.0
    dens, pres, thr, wait = [], [], [], []
    straight, _ = quickest_paths(np.full((H, W), V0), pl["gate"])
    nxt = straight
    for t in range(steps):
        if quickest and t % REROUTE == 0:
            nxt, _ = quickest_paths(weidmann(p / np.maximum(usable, 1e-6)), pl["gate"])
        waiting += wave[t]
        p, waiting, out, v = step(p, waiting, usable, nxt, pl["gate"])
        done += out
        if t % SAVE == SAVE - 1:
            rho = p / real
            dens.append(rho); pres.append(pressure(rho, v)); thr.append(done); wait.append(waiting)
    return np.array(dens, np.float32), np.array(pres, np.float32), np.array(thr), np.array(wait)


def compare(truth, pred):
    """How close is a prediction to what really happens? Density error, and crush cells found / missed / false."""
    t_hot, p_hot = (truth >= DANGER).any(0), (pred >= DANGER).any(0)
    return dict(density_error=round(float(np.abs(truth - pred).mean()), 3), crush_cells_true=int(t_hot.sum()),
                found=int((t_hot & p_hot).sum()), missed=int((t_hot & ~p_hot).sum()), false_alarms=int((~t_hot & p_hot).sum()))


def demo(seed=7, total=3200.0):
    pl = make_plaza(seed)
    ones = np.ones((H, W), np.float32)
    truth, pres, thr, wait = run(pl, total)
    naive, _, _, _ = run(pl, total, ones, quickest=False)          # shortest path, plan as drawn
    hughes, pres_h, _, _ = run(pl, total, ones)                    # full physics, plan as drawn (no clutter known)
    r = lambda a: np.round(a, 2).tolist()
    out = dict(simulated=True, height=H, width=W, cell_m=DX, frame_s=SAVE * DT, danger_density=DANGER, max_density=RHO_MAX,
               total_people=total, gate=pl["gate"].astype(int).tolist(), clutter=r(pl["clutter"]), usable_share_true=r(pl["pass_true"]),
               constants=dict(v0=V0, gamma=GAMMA, rho_max=RHO_MAX, source="Weidmann 1993; Hughes 2002; Helbing et al. 2007"),
               truth=dict(density=r(truth), pressure=np.round(pres, 3).tolist(), peak_density=round(float(truth.max()), 2),
                          peak_pressure=round(float(pres.max()), 3), through=np.round(thr).tolist(), waiting_outside=np.round(wait).tolist()),
               models=dict(
                   shortest_path=dict(label="Shortest path, site plan as drawn", density=r(naive), **compare(truth, naive)),
                   hughes=dict(label="Crowd physics (Hughes + Weidmann), site plan as drawn", density=r(hughes), **compare(truth, hughes))))
    (OUT / "plaza_demo.json").write_text(json.dumps(out))
    print("demo: truth peak", out["truth"]["peak_density"], "/m2, peak pressure", out["truth"]["peak_pressure"],
          "| conservation", round(float((truth[-1] * pl["pass_true"] * DX * DX).sum() + thr[-1] + wait[-1] - total), 3))
    for k, m in out["models"].items():
        print(" ", k, {x: m[x] for x in m if x not in ("density", "label")})


def dataset(n=60, name="plaza_train"):
    rng = np.random.default_rng(1)
    rows = []
    for i in range(n):
        pl = make_plaza(100 + i)
        total = float(rng.uniform(1500, 4500))
        d, _, _, _ = run(pl, total)
        rows.append((pl, total, d))
    n_test = max(1, n // 5)
    np.savez_compressed(OUT / f"{name}.npz", is_test=np.array([i >= n - n_test for i in range(n)], np.int8),
                        total=np.array([r[1] for r in rows], np.float32), density=np.array([r[2] for r in rows], np.float32),
                        clutter=np.array([r[0]["clutter"] for r in rows]), gate=np.array([r[0]["gate"] for r in rows], np.int8),
                        usable_share_true=np.array([r[0]["pass_true"] for r in rows]))
    print(f"{name}: {n} plazas ({n_test} held out), density {np.array([r[2] for r in rows]).shape}")


if __name__ == "__main__":
    demo()
    dataset(12, "plaza_sample")
    dataset(60, "plaza_train")
