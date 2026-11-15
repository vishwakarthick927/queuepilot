"""
PG-GNN: a physics-guided graph neural network for building evacuation (docs/BUILD.md "The model").

A building is a graph. Nodes = rooms, corridor segments, stairs, exits. Edges = doors.
Every time step (dt seconds), for every door i -> j:

  PHYSICS (hard-coded, never learned)
    people_i(next) = people_i + flow in - flow out          conservation of people
    flow <= door width x flow per metre x dt                 door law
    a node holds at most area x max density                  room law; nobody goes below zero
    people walk slower when it is crowded                    speed = 1.2 m/s x (1 - density / max density)

  LEARNED (only what physics does not know, and bounded)
    efficiency_ij in [0, 1]  (sigmoid)  how much of the door's textbook capacity is really used
    share_ij  (softmax over the doors leaving i, sums to 1)  which way people actually go

  flow_ij = min(people_i x share_ij x walk, capacity_ij x efficiency_ij), then scaled so j never overfills.
  Shares sum to 1 and efficiency <= 1, so the network cannot create or lose a person.

Three models: "physics" (efficiency 1, shortest path), "gnn" (same message passing, predicts the
change in people directly, no physics), "pggnn" (ours). Trained by rolling the physics forward and
backpropagating through it, like research/flood/water.py.

    python -m research.design.pggnn --selftest    # toy plans + a toy "truth", proves the pipeline
    python -m research.design.pggnn               # MAIN's dataset (data/design/), writes results.json
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

OUT = Path(__file__).parent
WALK = 1.2                      # free walking speed, m/s
HIDDEN = 32
ROUNDS = 3
torch.set_num_threads(4)


# ---------------------------------------------------------------- plan -> graph tensors
def shortest_dist(n, src, dst, length, open_, exits):
    """Metres from every node to the nearest open exit (Bellman-Ford on a tiny graph)."""
    d = np.full(n, np.inf)
    d[exits] = 0.0
    for _ in range(n):
        alt = d[dst] + length                                  # walk i -> j, then j's distance
        alt[~open_] = np.inf
        new = d.copy()
        np.minimum.at(new, src, alt)
        if np.allclose(new, d, equal_nan=True):
            break
        d = new
    return d


class Graph:
    """Everything the models need about ONE plan + ONE exit layout + ONE fire, as tensors."""

    def __init__(self, plan, exits, fire=None, panic=0.0):
        nodes, cands = plan["nodes"], plan["candidates"]
        self.n, self.dt = len(nodes), plan["dt_s"]
        self.area = np.array([max(1.0, nd["area_m2"]) for nd in nodes])
        self.is_exit = np.array([nd["kind"] == "exit" for nd in nodes])
        chosen = [c for k, c in enumerate(cands) if exits >> k & 1]
        self.exit_nodes = [c["node"] for c in chosen]
        doors = [(e["a"], e["b"], e["width_m"], e["length_m"], -1) for e in plan["edges"]]
        doors += [(c["attach_to"], c["node"], c["width_m"], 2.0, k) for k, c in enumerate(chosen)]
        src, dst, width, length, close = [], [], [], [], []
        closes = {c["edge"]: c["step"] for c in (fire or {}).get("close", [])}
        for i, (a, b, w, L, k) in enumerate(doors):
            step = closes.get(i, 10 ** 9) if k < 0 else 10 ** 9
            pairs = [(a, b)] if k >= 0 else [(a, b), (b, a)]  # nobody walks back in from outside
            for s, t in pairs:
                src.append(s); dst.append(t); width.append(w); length.append(L); close.append(step)
        self.src, self.dst = np.array(src), np.array(dst)
        self.width, self.length, self.close = np.array(width), np.array(length), np.array(close)
        fam = {c["node"]: c["familiarity"] for c in chosen}
        self.fam_exit = np.array([fam.get(d, 0.0) for d in self.dst])
        self.kind = np.array([["room", "corridor", "stair", "exit"].index(nd["kind"]) for nd in nodes])
        self.people0 = np.array([float(nd["people0"]) for nd in nodes])
        self.cap_people = np.where(self.is_exit, 1e9, self.area * plan["max_density"])
        self.max_density, self.flow_per_m = plan["max_density"], plan["flow_per_m_s"]
        self.panic = np.full(self.n, panic)                       # per node, so graphs can be batched
        self.fire = np.zeros(self.n)
        if fire is not None:
            self.fire[fire["start_node"]] = 1.0
        self.stages = sorted({0} | {int(s) for s in self.close if s < 10 ** 9})
        self.dist = {s: shortest_dist(self.n, self.src, self.dst, self.length, self.close > s, self.exit_nodes) for s in self.stages}
        self.sizes = [self.n]
        self.torch()

    @staticmethod
    def batch(gs):
        """Many graphs as ONE big graph with no doors between them, so one rollout scores them all."""
        b = Graph.__new__(Graph)
        off = np.cumsum([0] + [g.n for g in gs[:-1]])
        cat = lambda k: np.concatenate([getattr(g, k) for g in gs])
        for k in ("area", "is_exit", "kind", "people0", "cap_people", "width", "length", "close", "fam_exit", "panic", "fire"):
            setattr(b, k, cat(k))
        b.src = np.concatenate([g.src + o for g, o in zip(gs, off)])
        b.dst = np.concatenate([g.dst + o for g, o in zip(gs, off)])
        b.n, b.dt, b.sizes = int(sum(g.n for g in gs)), gs[0].dt, [g.n for g in gs]
        b.max_density, b.flow_per_m = gs[0].max_density, gs[0].flow_per_m
        b.stages = sorted({s for g in gs for s in g.stages})
        b.dist = {s: np.concatenate([g.dist_at(s) for g in gs]) for s in b.stages}
        b.torch()
        return b

    def torch(self):
        """Tensor copies used inside the rollout."""
        T = lambda x: torch.tensor(np.asarray(x), dtype=torch.float32)
        self.t_src, self.t_dst = torch.tensor(self.src), torch.tensor(self.dst)
        self.t_cap_door = T(self.width * self.flow_per_m * self.dt)
        self.t_len, self.t_cap_people, self.t_area = T(self.length), T(self.cap_people), T(self.area)
        self.t_exit = T(self.is_exit)

    def open_at(self, step):
        """Which directed doors are still open at this step (fire closes some)."""
        return torch.tensor(self.close > step, dtype=torch.float32)

    def dist_at(self, step):
        """Distance-to-exit field for the fire stage this step belongs to."""
        s = max(x for x in self.stages if x <= step)
        return self.dist[s]


# ---------------------------------------------------------------- the physics (shared by physics + pggnn)
def physics_step(g, people, share, eff, open_):
    """One time step of conservation of people. share, eff: one number per directed door."""
    density = people / g.t_area * (1 - g.t_exit)
    speed = WALK * torch.clamp(1 - density / g.max_density, 0.05, 1.0)
    walk = torch.clamp(speed[g.t_src] * g.dt / torch.clamp(g.t_len, min=1.0), max=1.0)
    want = people[g.t_src] * share * walk                       # who wants to go through this door now
    flow = torch.minimum(want, g.t_cap_door * eff) * open_      # door law
    incoming = torch.zeros(g.n).index_add(0, g.t_dst, flow)
    free = torch.relu(g.t_cap_people - people)                  # room law: space left in j
    flow = flow * torch.clamp(free / (incoming + 1e-6), max=1.0)[g.t_dst]
    out = torch.zeros(g.n).index_add(0, g.t_src, flow)
    inn = torch.zeros(g.n).index_add(0, g.t_dst, flow)
    return people - out + inn, flow


def shortest_path_share(g, step):
    """Physics only: everyone takes the door toward the nearest exit (the textbook)."""
    d = g.dist_at(step)
    ok = (g.close > step) & (d[g.dst] < d[g.src])
    best = np.full(g.n, -1)
    score = np.where(ok, d[g.dst], np.inf)
    for e in np.argsort(score):
        if np.isfinite(score[e]) and best[g.src[e]] < 0:
            best[g.src[e]] = e
    share = np.zeros(len(g.src))
    share[best[best >= 0]] = 1.0
    return torch.tensor(share, dtype=torch.float32)


# ---------------------------------------------------------------- the GNN (message passing by hand)
def node_features(g, people, step):
    """What every node knows right now: crowding, size, type, distance to an exit, fire, panic."""
    density = people / g.t_area * (1 - g.t_exit) / g.max_density
    kind = torch.nn.functional.one_hot(torch.tensor(g.kind), 4).float()
    d = torch.tensor(np.minimum(g.dist_at(step), 300.0) / 100.0, dtype=torch.float32)
    fire, panic = torch.tensor(g.fire, dtype=torch.float32), torch.tensor(g.panic, dtype=torch.float32)
    return torch.cat([density[:, None], torch.log(g.t_area[:, None]) / 5, kind, d[:, None], fire[:, None], panic[:, None]], 1)


def edge_features(g, step, open_):
    """What every door knows: width, length, does it lead to a familiar exit, is it downhill."""
    d = g.dist_at(step)
    with np.errstate(invalid="ignore"):                       # inf - inf where both ends are cut off
        downhill = np.clip((d[g.src] - d[g.dst]) / 20.0, -2, 2)
    downhill[~np.isfinite(downhill)] = 0.0
    x = np.stack([g.width / 2, g.length / 20, g.fam_exit, downhill], 1)
    return torch.cat([torch.tensor(x, dtype=torch.float32), open_[:, None]], 1)


def mlp(i, o):
    return nn.Sequential(nn.Linear(i, HIDDEN), nn.Tanh(), nn.Linear(HIDDEN, o))


class MessagePassing(nn.Module):
    """3 rounds: each door sends a message from i to j; each node adds up what it receives."""

    def __init__(self):
        super().__init__()
        self.enc = mlp(9, HIDDEN)
        self.msg = nn.ModuleList([mlp(2 * HIDDEN + 5, HIDDEN) for _ in range(ROUNDS)])
        self.upd = nn.ModuleList([mlp(2 * HIDDEN, HIDDEN) for _ in range(ROUNDS)])

    def forward(self, g, people, step, open_):
        h = self.enc(node_features(g, people, step))
        e = edge_features(g, step, open_)
        for msg, upd in zip(self.msg, self.upd):
            m = msg(torch.cat([h[g.t_src], h[g.t_dst], e], 1))
            agg = torch.zeros(g.n, HIDDEN).index_add(0, g.t_dst, m)    # sum of messages into each node
            h = h + upd(torch.cat([h, agg], 1))
        return h, e


def masked_softmax(logits, src, n, open_):
    """Softmax over the open doors leaving each node, so a node's shares sum to 1."""
    z = torch.exp(torch.clamp(logits, -20, 20)) * open_
    total = torch.zeros(n).index_add(0, src, z)
    return z / (total[src] + 1e-9)


class PGGNN(nn.Module):
    """Ours: physics step with a learned door efficiency (sigmoid) and learned shares (softmax)."""

    def __init__(self):
        super().__init__()
        self.mp = MessagePassing()
        self.eff_head = mlp(2 * HIDDEN + 5, 1)
        self.share_head = mlp(2 * HIDDEN + 5, 1)
        nn.init.constant_(self.eff_head[-1].bias, 2.0)        # start near "doors work as designed"

    def terms(self, g, people, step, open_):
        h, e = self.mp(g, people, step, open_)
        x = torch.cat([h[g.t_src], h[g.t_dst], e], 1)
        eff = torch.sigmoid(self.eff_head(x)[:, 0])
        share = masked_softmax(self.share_head(x)[:, 0] + 4 * e[:, 3], g.t_src, g.n, open_)
        return eff, share

    def step(self, g, people, step):
        open_ = g.open_at(step)
        eff, share = self.terms(g, people, step, open_)
        return physics_step(g, people, share, eff, open_)[0]


class GNNOnly(nn.Module):
    """Baseline: the same message passing predicts the change in people directly. No physics."""

    def __init__(self):
        super().__init__()
        self.mp = MessagePassing()
        self.head = mlp(HIDDEN, 1)

    def step(self, g, people, step):
        h, _ = self.mp(g, people, step, g.open_at(step))
        return torch.relu(people + 10 * self.head(h)[:, 0])


class PhysicsOnly:
    """Baseline: efficiency 1, shortest path. Nothing learned."""

    def step(self, g, people, step):
        open_ = g.open_at(step)
        return physics_step(g, people, shortest_path_share(g, step), torch.ones(len(g.src)), open_)[0]


def rollout(model, g, people, start, steps):
    """Roll a model forward; returns people[step][node] (steps x n)."""
    out = []
    for k in range(steps):
        people = model.step(g, people, start + k)
        out.append(people)
    return torch.stack(out)


def clearance_step(traj, g):
    """First step with less than one person left inside (exits do not count). None if never."""
    inside = (traj * (1 - g.t_exit)).sum(1)
    hit = torch.nonzero(inside < 1.0)
    return int(hit[0]) + 1 if len(hit) else None


def clearance_steps(traj, b):
    """clearance_step for every graph inside a batch (None = never cleared)."""
    inside = (traj * (1 - b.t_exit)).split(b.sizes, dim=1)
    out = []
    for part in inside:
        hit = torch.nonzero(part.sum(1) < 1.0)
        out.append(int(hit[0]) + 1 if len(hit) else None)
    return out


# ---------------------------------------------------------------- self-test truth (until MAIN's simulator lands)
class ToyTruth:
    """Hidden behaviour the models are never told: doors jam when crowded and panicked,
    and people head for the exit they know (familiarity), not the nearest one."""

    def step(self, g, people, step):
        open_ = g.open_at(step)
        d = torch.tensor(np.nan_to_num(g.dist_at(step), posinf=1e3), dtype=torch.float32)
        via = d[g.t_dst] + g.t_len
        p = torch.tensor(g.panic, dtype=torch.float32)[g.t_src]
        logits = -via / (8 + 12 * p) + (2 + 3 * p) * torch.tensor(g.fam_exit, dtype=torch.float32)
        share = masked_softmax(logits, g.t_src, g.n, open_)
        density = (people / g.t_area * (1 - g.t_exit))[g.t_src] / g.max_density
        eff = 1 / (1 + (0.5 + 2 * p) * density)
        return physics_step(g, people, share, eff, open_)[0]


def selftest_runs(n_plans, seed0, steps):
    from research.design.toyplans import make_plan
    runs, r = [], np.random.default_rng(seed0)
    for p in range(n_plans):
        plan = make_plan(seed0 + p)
        k = len(plan["candidates"])
        for _ in range(4):
            exits = 1 | int(r.integers(1, 2 ** k)) & int(r.integers(1, 2 ** k))   # main entrance + some
            fire = plan["fires"][int(r.integers(len(plan["fires"])))] if r.random() < 0.6 else None
            g = Graph(plan, exits, fire, panic=float(r.uniform(0, 1)))
            with torch.no_grad():
                traj = rollout(ToyTruth(), g, torch.tensor(g.people0, dtype=torch.float32), 0, steps)
            runs.append((g, torch.cat([torch.tensor(g.people0, dtype=torch.float32)[None], traj])))
    return runs


# ---------------------------------------------------------------- training + test
def train(model, runs, iters, horizon=30, lr=3e-3):
    """Pick a run and a start time, roll the model forward `horizon` steps, match the simulator."""
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    r = np.random.default_rng(0)
    for i in range(iters):
        g, truth = runs[int(r.integers(len(runs)))]
        t0 = int(r.integers(0, max(1, len(truth) - horizon - 1)))
        pred = rollout(model, g, truth[t0], t0, horizon)
        scale = truth[0].sum()
        loss = (((pred - truth[t0 + 1:t0 + 1 + horizon]) / scale * 100) ** 2).mean()
        opt.zero_grad(); loss.backward(); opt.step()
        if i % 100 == 0:
            print(f"    iter {i:4d}  loss {loss.item():.4f}")
    return model


@torch.no_grad()
def test(model, runs):
    """Full rollouts on plans never seen in training: clearance-time error and people created/lost."""
    errs, lost = [], []
    for g, truth in runs:
        pred = rollout(model, g, truth[0], 0, len(truth) - 1)
        c_true, c_pred = clearance_step(truth[1:], g), clearance_step(pred, g)
        T = len(truth) - 1
        errs.append(abs((c_pred or T) - (c_true or T)) * g.dt)
        lost.append(float((pred.sum(1) - truth[0].sum()).abs().max()))
    e = np.array(errs)
    return {"clearance_err_s": round(float(e.mean()), 1), "ci95": round(float(1.96 * e.std() / np.sqrt(len(e))), 1),
            "people_error": round(float(np.mean(lost)), 2), "runs": len(e)}


def speed(model, g, steps):
    """Layouts scored per second (one full rollout = one layout under one fire)."""
    t = time.perf_counter()
    with torch.no_grad():
        rollout(model, g, torch.tensor(g.people0, dtype=torch.float32), 0, steps)
    return round(1 / (time.perf_counter() - t), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--iters", type=int, default=600)
    a = ap.parse_args()
    torch.manual_seed(0)
    if not a.selftest:
        raise SystemExit("MAIN's dataset (engine.design_data) has not landed yet: run with --selftest")
    steps = 200
    train_runs, test_runs = selftest_runs(16, 0, steps), selftest_runs(6, 500, steps)   # test = unseen plans
    models = {"physics": PhysicsOnly(), "gnn": GNNOnly(), "pggnn": PGGNN()}
    for name in ("gnn", "pggnn"):
        print("training", name)
        train(models[name], train_runs, a.iters)
    res = {"models": {k: test(m, test_runs) for k, m in models.items()},
           "speed": {"pggnn_per_s": speed(models["pggnn"], test_runs[0][0], steps)},
           "setup": {"source": "SELFTEST toy plans + toy truth (not MAIN's simulator)", "train_runs": len(train_runs),
                     "test_runs": len(test_runs), "steps": steps, "dt_s": 2}}
    print(json.dumps(res, indent=1))
    (OUT / "results_selftest.json").write_text(json.dumps(res, indent=1))
    torch.save(models["pggnn"].state_dict(), OUT / "pggnn_selftest.pt")


if __name__ == "__main__":
    main()
