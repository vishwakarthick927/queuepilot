"""
PG-GNN: a physics-guided graph neural network for building evacuation (docs/BUILD.md "The model").

A building is a graph. Nodes = rooms, corridor segments, exits. Edges = doors and passages.
Every time step (dt seconds), for every door i -> j:

  PHYSICS (hard-coded, never learned; the textbook rules MAIN listed for the physics-only model)
    people_i(next) = people_i + flow in - flow out               conservation of people
    a door passes at most width x flow_per_m_s x dt per step     door law (both directions share it)
    a space takes at most area x max_density                     room law; nobody goes below zero
    people walk slower in a crowd                                speed = walk speed x clip(1 - density / max, 0.15, 1)

  LEARNED (only what physics does not know, and bounded)
    efficiency_ij in [0, 1]  (sigmoid)   how much of the door's capacity is really used (pushing jams doors)
    share_ij (softmax over the doors leaving i, sums to 1)   which way people really go (familiar exit, herding)

  flow_ij = min(people_i x share_ij x walk, capacity_ij x efficiency_ij, free space in j)
  Shares sum to 1 and efficiency <= 1, so the network cannot create or lose a person.

Three models: "physics" (efficiency 1, everyone walks to the nearest exit), "gnn" (same message passing,
predicts the change in people directly, no physics), "pggnn" (ours). Trained by rolling the physics forward
and backpropagating through it, like research/flood/water.py. Truth = MAIN's detailed simulator (engine/evac.py),
whose hidden rules (exit choice by familiarity + herding, doors jamming under panic) the models are never told.

    python -m engine.design_data                               # once: MAIN's 1,600 runs -> data/design/train.npz
    python -m research.design.pggnn --baselines                # trains all three, writes results.json + pggnn.pt
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from engine.evac import shortest_paths            # MAIN's Dijkstra, read-only use (same routes as the simulator)

OUT = Path(__file__).parent
DATA = OUT.parents[1] / "data" / "design"
HIDDEN = 32
ROUNDS = 3
MIN_SPEED = 0.15
KINDS = ["room", "corridor", "stair", "exit"]
ROUTE_KEYS = ("near", "fam", "via", "phys", "famdoor", "extra", "famt")
torch.set_num_threads(4)


# ---------------------------------------------------------------- plan -> graph tensors
def as_ids(exits, plan):
    """A layout as a list of candidate ids (accepts a list or a bitmask over the candidates)."""
    if isinstance(exits, (int, np.integer)):
        return [c["id"] for k, c in enumerate(plan["candidates"]) if int(exits) >> k & 1]
    return [int(x) for x in exits]


class Graph:
    """Everything the models need about ONE plan + ONE exit layout + ONE fire, as arrays.
    Directed doors use MAIN's numbering: 2e = a -> b on edge e, 2e+1 = b -> a."""

    def __init__(self, plan, exits, fire=None, panic=0.0, lost_exit=None):
        nodes, edges = plan["nodes"], plan["edges"]
        built = set(as_ids(exits, plan)) - {lost_exit}
        self.n, self.dt, self.sizes = len(nodes), plan["dt_s"], [len(nodes)]
        self.max_density, self.flow_per_m, self.walk = plan["max_density"], plan["flow_per_m_s"], plan["walk_speed_m_s"]
        self.area = np.array([max(1.0, nd["area_m2"]) for nd in nodes])
        self.is_exit = np.array([nd["kind"] == "exit" for nd in nodes])
        self.kind = np.array([KINDS.index(nd["kind"]) for nd in nodes])
        self.people0 = np.array([float(nd["people0"]) for nd in nodes])
        self.cap_people = np.where(self.is_exit, 1e9, self.area * self.max_density)
        self.src = np.array([x for e in edges for x in (e["a"], e["b"])])
        self.dst = np.array([x for e in edges for x in (e["b"], e["a"])])
        self.width = np.repeat([e["width_m"] for e in edges], 2).astype(float)
        self.length = np.repeat([e["length_m"] for e in edges], 2).astype(float)
        usable = [e["candidate"] is None or e["candidate"] in built for e in edges]
        closes = {c["edge"]: c["step"] for c in (fire or {}).get("close", [])}
        self.close = np.repeat([closes.get(i, 10 ** 9) if ok else -1 for i, ok in enumerate(usable)], 2)
        self.close = np.where(self.is_exit[self.src], -1, self.close)     # nobody walks back in from an exit
        self.panic = np.full(self.n, panic)
        self.fire = np.zeros(self.n)
        if fire is not None:
            self.fire[fire["start_node"]] = 1.0
        cands = [c for c in plan["candidates"] if c["id"] in built]
        self.exit_nodes = [c["node"] for c in cands]
        self.fam = np.array([c["familiarity"] for c in cands])
        self.stages = sorted({0} | {int(s) for s in self.close if 0 < s < 10 ** 9})
        self.route = {s: self.routes(edges, s) for s in self.stages}
        self.torch()

    def routes(self, edges, step):
        """What a floor-plan reader knows at this fire stage, per directed door:
        the textbook choice (next door toward the nearest exit), the most familiar exit this door leads to,
        and the walking distance to the nearest exit through it."""
        is_open = self.close[0::2] > step
        dist, hop = shortest_paths(self.n, edges, is_open, self.exit_nodes)
        D = len(self.src)
        fam, via, phys = np.zeros(D), np.full(D, np.inf), np.zeros(D)
        for k in range(len(self.exit_nodes)):
            for i in np.nonzero(hop[:, k] >= 0)[0]:
                d = hop[i, k]
                fam[d] = max(fam[d], self.fam[k])
                via[d] = min(via[d], dist[i, k])
        near = dist.min(1) if dist.shape[1] else np.full(self.n, np.inf)
        famdoor, extra, famt = np.zeros(D), np.zeros(self.n), np.zeros(self.n)
        for i in range(self.n):
            if np.isfinite(near[i]) and near[i] > 0:
                phys[hop[i, int(np.argmin(dist[i]))]] = 1.0
                # channel 1: the most familiar exit this node can still reach, and the door toward it
                k = max((k for k in range(len(self.exit_nodes)) if np.isfinite(dist[i, k])), key=lambda k: (self.fam[k], -dist[i, k]))
                famdoor[hop[i, k]] = 1.0
                extra[i], famt[i] = dist[i, k] - near[i], self.fam[k]
        return dict(near=near, fam=fam, via=via, phys=phys, famdoor=famdoor, extra=extra, famt=famt)

    @staticmethod
    def batch(gs):
        """Many graphs as ONE big graph with no doors between them, so one rollout scores them all."""
        b = Graph.__new__(Graph)
        off = np.cumsum([0] + [g.n for g in gs[:-1]])
        cat = lambda k: np.concatenate([getattr(g, k) for g in gs])
        for k in ("area", "is_exit", "kind", "people0", "cap_people", "width", "length", "close", "panic", "fire"):
            setattr(b, k, cat(k))
        b.src = np.concatenate([g.src + o for g, o in zip(gs, off)])
        b.dst = np.concatenate([g.dst + o for g, o in zip(gs, off)])
        b.n, b.dt, b.sizes = int(sum(g.n for g in gs)), gs[0].dt, [g.n for g in gs]
        b.max_density, b.flow_per_m, b.walk = gs[0].max_density, gs[0].flow_per_m, gs[0].walk
        b.stages = sorted({s for g in gs for s in g.stages})
        b.route = {s: {k: np.concatenate([g.route_at(s)[k] for g in gs]) for k in ROUTE_KEYS} for s in b.stages}
        b.torch()
        return b

    def torch(self):
        """Tensor copies used inside the rollout."""
        T = lambda x: torch.tensor(np.asarray(x), dtype=torch.float32)
        self.t_src, self.t_dst = torch.tensor(self.src), torch.tensor(self.dst)
        self.t_pair = torch.tensor(np.arange(len(self.src)) ^ 1)                 # the same door, other direction
        self.t_cap_door = T(self.width * self.flow_per_m * self.dt)
        self.t_len, self.t_cap_people, self.t_area, self.t_exit = T(self.length), T(self.cap_people), T(self.area), T(self.is_exit)
        # everything that only changes when a fire closes a door: computed once per fire stage, not every step
        self.cache = {s: (T(self.close > s), static_node(self, s), static_edge(self, s)) for s in self.stages}

    def stage(self, step):
        return max(s for s in self.stages if s <= step)

    def open_at(self, step):
        """Which directed doors are usable at this step (unbuilt exits, fire, no walking back from exits)."""
        return self.cache[self.stage(step)][0]

    def route_at(self, step):
        return self.route[self.stage(step)]


# ---------------------------------------------------------------- the physics (shared by physics + pggnn)
def walk_share(g, total):
    """Share of a node's people who reach the next door this step: speed x dt / door distance, at most 1.
    People walk slower in a crowd."""
    density = total / g.t_area * (1 - g.t_exit)
    speed = g.walk * torch.clamp(1 - density / g.max_density, MIN_SPEED, 1.0)
    return torch.clamp(speed[g.t_src] * g.dt / g.t_len, max=1.0)


def door_demand(want):
    """People pushing on each door from both sides this step (both directions share the door)."""
    total = sum(want)
    return total + total[torch.arange(len(total)) ^ 1]


def move(g, people, want, eff):
    """Door law + room law + conservation, for one or more groups of people (channels).
    people: list of per-node counts, want: list of per-door wishes (same order), eff: door efficiency in [0, 1]."""
    both = door_demand(want)
    door = torch.clamp(g.t_cap_door * eff / (both + 1e-9), max=1.0)       # door law
    flows = [w * door for w in want]
    incoming = torch.zeros(g.n).index_add(0, g.t_dst, sum(flows))
    total = sum(people)
    room = torch.clamp(torch.relu(g.t_cap_people - total) / (incoming + 1e-9), max=1.0)[g.t_dst]   # room law
    out = []
    for p, f in zip(people, flows):
        f = f * room
        out.append(p - torch.zeros(g.n).index_add(0, g.t_src, f) + torch.zeros(g.n).index_add(0, g.t_dst, f))
    return out                                                            # conservation: what leaves i arrives at j


def physics_step(g, people, share, eff, open_):
    """One time step for a single group of people. share, eff: one number per directed door."""
    want = people[g.t_src] * share * walk_share(g, people) * open_
    return move(g, [people], [want], eff)[0]


# ---------------------------------------------------------------- the GNN (message passing by hand)
def static_node(g, s):
    """The fixed part of what a node knows at fire stage s: size, type, distance to the nearest exit,
    how much further the most familiar exit is and how familiar it is, fire, panic."""
    r = g.route[s]
    kind = np.eye(4)[g.kind]
    near = np.minimum(np.nan_to_num(r["near"], posinf=300.0), 300) / 50
    x = np.column_stack([np.log(g.area) / 5, kind, near, np.minimum(r["extra"], 300) / 50, r["famt"], g.fire, g.panic])
    return torch.tensor(x, dtype=torch.float32)


def static_edge(g, s):
    """What every door knows at fire stage s: width, length, the textbook choice, how familiar and how far
    the exits it leads to are, and whether it is open."""
    r = g.route[s]
    via = np.minimum(np.nan_to_num(r["via"], posinf=300.0), 300) / 50
    x = np.column_stack([g.width / 2, g.length / 10, r["phys"], r["fam"], via, g.close > s])
    return torch.tensor(x, dtype=torch.float32)


def node_features(g, people, step):
    """What every node knows right now: how crowded it is, plus the fixed part above."""
    density = people / g.t_area * (1 - g.t_exit) / g.max_density
    return torch.cat([density[:, None], g.cache[g.stage(step)][1]], 1)


def edge_features(g, step, open_):
    return g.cache[g.stage(step)][2]


N_NODE, N_EDGE = 11, 6


def mlp(i, o):
    return nn.Sequential(nn.Linear(i, HIDDEN), nn.Tanh(), nn.Linear(HIDDEN, o))


class MessagePassing(nn.Module):
    """3 rounds: each door sends a message from i to j; each node adds up what it receives."""

    def __init__(self):
        super().__init__()
        self.enc = mlp(N_NODE, HIDDEN)
        self.msg = nn.ModuleList([mlp(2 * HIDDEN + N_EDGE, HIDDEN) for _ in range(ROUNDS)])
        self.upd = nn.ModuleList([mlp(2 * HIDDEN, HIDDEN) for _ in range(ROUNDS)])

    def forward(self, g, people, step, open_):
        h = self.enc(node_features(g, people, step))
        e = edge_features(g, step, open_)
        for msg, upd in zip(self.msg, self.upd):
            m = msg(torch.cat([h[g.t_src], h[g.t_dst], e], 1))
            agg = torch.zeros(g.n, HIDDEN).index_add(0, g.t_dst, m)          # sum of messages into each node
            h = h + upd(torch.cat([h, agg], 1))
        return h, e


def masked_softmax(logits, src, n, open_):
    """Softmax over the open doors leaving each node, so a node's shares sum to 1."""
    z = torch.exp(torch.clamp(logits, -20, 20)) * open_
    total = torch.zeros(n).index_add(0, src, z)
    return z / (total[src] + 1e-9)


class PGGNN(nn.Module):
    """Ours: physics does the walking; the network learns only bounded terms.
      channels=True  (fix 1)  people carry a destination: channel 0 heads for the NEAREST exit, channel 1 for the
                              MOST FAMILIAR one. Learned: the share of each room in channel 1 (sigmoid) and how
                              fast people re-decide (a rate in [0, 0.15]). Otherwise: learned door shares (softmax).
      ratio=True     (fix 2)  the door-efficiency head sees demand / capacity and panic, the two things a jam needs.
    Splits sum to the node's people and efficiency <= 1, so nobody is created or lost."""

    def __init__(self, channels=True, ratio=True):
        super().__init__()
        self.channels, self.ratio = channels, ratio
        self.mp = MessagePassing()
        self.eff_head = mlp(2 * HIDDEN + N_EDGE + 2, 1)
        self.share_head = mlp(2 * HIDDEN + N_EDGE, 1)
        self.choice_head = mlp(HIDDEN + N_NODE, 1)
        self.rethink = nn.Parameter(torch.tensor(-1.0))
        nn.init.constant_(self.eff_head[-1].bias, 3.0)              # start near "doors work as designed"

    def choice(self, g, h, total, step):
        """Share of each node's people heading for the most familiar exit (learned, in [0, 1])."""
        return torch.sigmoid(self.choice_head(torch.cat([h, node_features(g, total, step)], 1))[:, 0])

    def init(self, g, people0):
        if not self.channels:
            return people0
        h, _ = self.mp(g, people0, 0, g.open_at(0))
        c = self.choice(g, h, people0, 0)
        return torch.stack([people0 * (1 - c), people0 * c], 1)

    @staticmethod
    def total(state):
        return state.sum(1) if state.dim() == 2 else state

    def step(self, g, state, step):
        open_ = g.open_at(step)
        total = self.total(state)
        h, e = self.mp(g, total, step, open_)
        walk = walk_share(g, total) * open_
        if self.channels:
            c = self.choice(g, h, total, step)
            x1 = state[:, 1] + 0.15 * torch.sigmoid(self.rethink) * (c * total - state[:, 1])   # some people re-decide
            people = [total - x1, x1]
            doors = [e[:, 2], torch.tensor(g.route_at(step)["famdoor"], dtype=torch.float32)]
            want = [p[g.t_src] * d * walk for p, d in zip(people, doors)]
        else:
            x = torch.cat([h[g.t_src], h[g.t_dst], e], 1)
            share = masked_softmax(self.share_head(x)[:, 0] + 6 * e[:, 2], g.t_src, g.n, open_)
            people, want = [total], [total[g.t_src] * share * walk]
        ratio = torch.clamp(door_demand(want) / g.t_cap_door, 0, 5) if self.ratio else torch.zeros(len(g.src))
        panic = torch.tensor(g.panic, dtype=torch.float32)[g.t_src] if self.ratio else torch.zeros(len(g.src))
        eff = torch.sigmoid(self.eff_head(torch.cat([h[g.t_src], h[g.t_dst], e, ratio[:, None], panic[:, None]], 1))[:, 0])
        people = move(g, people, want, eff)
        return torch.stack(people, 1) if self.channels else people[0]


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
    """Baseline: efficiency 1, everyone takes the next door toward the nearest exit. Nothing learned."""

    def step(self, g, people, step):
        open_ = g.open_at(step)
        share = g.cache[g.stage(step)][2][:, 2]                        # the textbook door, from the cache
        return physics_step(g, people, share, torch.ones(len(g.src)), open_)


def rollout(model, g, people, start, steps):
    """Roll a model forward from the starting crowd; returns people[step][node] (steps x n).
    Exit nodes keep everyone who left through them."""
    state = model.init(g, people) if hasattr(model, "init") else people
    total = model.total if hasattr(model, "total") else (lambda s: s)
    out = []
    for k in range(steps):
        state = model.step(g, state, start + k)
        out.append(total(state))
    return torch.stack(out)


def inside(traj, g):
    """People still in the building (exit nodes do not count), per step and per graph in a batch."""
    return torch.stack([p.sum(-1) for p in (traj * (1 - g.t_exit)).split(g.sizes, dim=-1)], -1)


def clearance_steps(traj, g):
    """First step with less than one person inside, per graph (None = never). Same rule as engine.evac."""
    left = inside(traj, g)
    out = []
    for k in range(left.shape[1]):
        hit = torch.nonzero(left[:, k] < 1.0)
        out.append(int(hit[0]) + 1 if len(hit) else None)
    return out


# ---------------------------------------------------------------- data from MAIN's simulator
def truth_table(plan, people, flow, steps, exits_built):
    """One tensor per run, [steps + 1, nodes]: people in each room/corridor after each step (row 0 = the start),
    and in each EXIT node the cumulative number of people who left through it (so it matches our exit nodes,
    which keep everyone who arrives). Rows after the run ended: building empty, exit totals held."""
    n, T = len(plan["nodes"]), 300
    t = np.zeros((T + 1, n), np.float32)
    t[0] = [nd["people0"] for nd in plan["nodes"]]
    t[1:steps + 1] = people[:steps, :n]
    for c in plan["candidates"]:
        if c["id"] in exits_built:
            e = next(i for i, ed in enumerate(plan["edges"]) if ed["candidate"] == c["id"])
            out = np.cumsum(np.abs(flow[:T, e]))
            t[1:, c["node"]] = np.concatenate([out[:steps], np.full(T - steps, out[steps - 1] if steps else 0)])
    return torch.tensor(t)


def main_runs():
    """MAIN's train.npz (engine.design_data): (graph, truth table, cleared step or None, is_test) per run."""
    plans = json.loads((DATA / "train_plans.json").read_text())
    z = np.load(DATA / "train.npz")
    runs = []
    for r in range(len(z["plan_index"])):
        plan = plans[int(z["plan_index"][r])]
        built = [c["id"] for k, c in enumerate(plan["candidates"]) if k < z["exits"].shape[1] and z["exits"][r, k]]
        fire = plan["fires"][int(z["fire"][r])] if z["fire"][r] >= 0 else None
        lost = int(z["lost_exit"][r]) if z["lost_exit"][r] >= 0 else None
        g = Graph(plan, built, fire, float(z["panic"][r]), lost)
        steps = int(z["steps"][r])
        truth = truth_table(plan, z["people"][r], z["flow"][r], steps, built)
        cleared = int(z["clearance_step"][r]) if z["clearance_step"][r] >= 0 else None
        runs.append((g, truth, cleared, bool(z["is_test"][r])))
    print(f"loaded {len(runs)} runs ({sum(r[3] for r in runs)} on held-out plans)", flush=True)
    return runs


# ---------------------------------------------------------------- training + test
def train(model, runs, iters, horizon=150, lr=2e-3, batch=8, pggnn=True):
    """From the starting crowd, roll the model forward `horizon` steps and match the simulator (fix 3).
    Loss (people / 10, squared): every room and corridor 1.0, people still inside 0.5,
    cumulative people out through each exit 0.5 (this one checks WHICH exit people chose)."""
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, iters)
    r = np.random.default_rng(0)
    for i in range(iters):
        picks = [runs[int(k)] for k in r.integers(len(runs), size=batch)]
        b = Graph.batch([g for g, *_ in picks])
        truth = torch.cat([t[:horizon + 1] for _, t, *_ in picks], 1)
        pred = rollout(model, b, truth[0], 0, horizon)
        target, keep, ex = truth[1:], 1 - b.t_exit, b.t_exit
        node_err = ((((pred - target) * keep) / 10) ** 2).mean()
        inside_err = (((inside(pred, b) - inside(target, b)) / 10) ** 2).mean()
        exit_err = ((((pred - target) * ex) / 10) ** 2).mean()
        loss = node_err + 0.5 * inside_err + (0.5 * exit_err if pggnn else 0)
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step()
        if i % 50 == 0:
            print(f"    iter {i:4d}  loss {loss.item():.4f}", flush=True)
    return model


@torch.no_grad()
def test(model, runs, max_steps=300, batch=32):
    """Full rollouts on floor plans never seen in training: clearance-time error and people created/lost."""
    errs, lost = [], []
    for s in range(0, len(runs), batch):
        chunk = runs[s:s + batch]
        b = Graph.batch([g for g, *_ in chunk])
        start = torch.cat([t[0] for _, t, *_ in chunk])
        pred = rollout(model, b, start, 0, max_steps)
        for (g, t, cleared, _), c, part, p0 in zip(chunk, clearance_steps(pred, b), pred.split(b.sizes, 1), start.split(b.sizes)):
            errs.append(abs((c or max_steps) - (cleared or max_steps)) * g.dt)
            lost.append(float((part.sum(1) - p0.sum()).abs().max()))
    e = np.array(errs)
    return {"clearance_err_s": round(float(e.mean()), 1), "ci95": round(float(1.96 * e.std() / np.sqrt(len(e))), 1),
            "people_error": round(float(np.mean(lost)), 2), "runs": len(e)}


def speed(model, g, steps=150, n=256):
    """Layouts scored per second: n copies of one layout in a batch, one full rollout."""
    b = Graph.batch([g] * n)
    t = time.perf_counter()
    with torch.no_grad():
        rollout(model, b, torch.tensor(b.people0, dtype=torch.float32), 0, steps)
    return round(n / (time.perf_counter() - t), 1)


def sim_speed(n=20):
    """Detailed-simulator runs per second on the demo plan, for the same comparison."""
    from engine import evac
    plan = json.loads((DATA / "demo_plan.json").read_text())
    t = time.perf_counter()
    for _ in range(n):
        evac.simulate(plan, [plan["main_entrance"], 3, 6], panic=0.8, record=False)
    return round(n / (time.perf_counter() - t), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="", help="suffix for the output files (results_<tag>.json, pggnn_<tag>.pt)")
    ap.add_argument("--no-channels", action="store_true", help="switch off fix 1 (destination channels)")
    ap.add_argument("--no-ratio", action="store_true", help="switch off fix 2 (demand ratio into the efficiency head)")
    ap.add_argument("--baselines", action="store_true", help="also train and test GNN only and physics only")
    ap.add_argument("--iters", type=int, default=600)
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    torch.manual_seed(0)
    runs = main_runs()
    train_runs = [r for r in runs if not r[3]]
    test_runs = [r for r in runs if r[3]]                                # 16 plans never seen in training
    ours = PGGNN(channels=not a.no_channels, ratio=not a.no_ratio)
    print("training pggnn", "channels" if ours.channels else "", "ratio" if ours.ratio else "", flush=True)
    train(ours, train_runs, a.iters)
    models = {"pggnn": ours}
    if a.baselines:
        print("training gnn only", flush=True)
        models["gnn"] = train(GNNOnly(), train_runs, a.iters, pggnn=False)
        models["physics"] = PhysicsOnly()
    res = {"models": {k: test(m, test_runs) for k, m in models.items()},
           "speed": {"pggnn_per_s": speed(ours, test_runs[0][0]), "simulator_per_s": sim_speed()},
           "setup": {"source": "MAIN engine.design_data (data/design/train.npz)", "train_runs": len(train_runs),
                     "test_runs": len(test_runs), "dt_s": 2, "max_steps": 300, "channels": ours.channels, "ratio": ours.ratio,
                     "unseen": "16 floor plans never seen in training", "simulated": True}}
    print(json.dumps(res, indent=1), flush=True)
    tag = f"_{a.tag}" if a.tag else ""
    (OUT / f"results{tag}.json").write_text(json.dumps(res, indent=1))
    torch.save(ours.state_dict(), OUT / f"pggnn{tag}.pt")


if __name__ == "__main__":
    main()
