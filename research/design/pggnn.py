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

    python -m research.design.pggnn --quick     # makes its own runs with engine.evac (no dataset file needed)
    python -m research.design.pggnn             # MAIN's dataset data/design/train.npz (engine.design_data)
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
        for i in range(self.n):
            if np.isfinite(near[i]) and near[i] > 0:
                phys[hop[i, int(np.argmin(dist[i]))]] = 1.0
        return dict(near=near, fam=fam, via=via, phys=phys)

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
        b.route = {s: {k: np.concatenate([g.route_at(s)[k] for g in gs]) for k in ("near", "fam", "via", "phys")} for s in b.stages}
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
def physics_step(g, people, share, eff, open_):
    """One time step of conservation of people. share, eff: one number per directed door."""
    density = people / g.t_area * (1 - g.t_exit)
    speed = g.walk * torch.clamp(1 - density / g.max_density, MIN_SPEED, 1.0)
    walk = torch.clamp(speed[g.t_src] * g.dt / g.t_len, max=1.0)
    want = people[g.t_src] * share * walk * open_                     # who wants to go through this door now
    both = want + want[g.t_pair]                                      # both directions share the door
    flow = want * torch.clamp(g.t_cap_door * eff / (both + 1e-9), max=1.0)
    incoming = torch.zeros(g.n).index_add(0, g.t_dst, flow)
    free = torch.relu(g.t_cap_people - people)                        # room law: space left in j
    flow = flow * torch.clamp(free / (incoming + 1e-9), max=1.0)[g.t_dst]
    out = torch.zeros(g.n).index_add(0, g.t_src, flow)
    inn = torch.zeros(g.n).index_add(0, g.t_dst, flow)
    return people - out + inn


# ---------------------------------------------------------------- the GNN (message passing by hand)
def static_node(g, s):
    """The fixed part of what a node knows at fire stage s: size, type, distance to an exit, fire, panic."""
    kind = np.eye(4)[g.kind]
    near = np.minimum(np.nan_to_num(g.route[s]["near"], posinf=300.0), 300) / 50
    x = np.column_stack([np.log(g.area) / 5, kind, near, g.fire, g.panic])
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


N_NODE, N_EDGE = 9, 6


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
    """Ours: the physics step, with a learned door efficiency (sigmoid) and learned shares (softmax)."""

    def __init__(self):
        super().__init__()
        self.mp = MessagePassing()
        self.eff_head = mlp(2 * HIDDEN + N_EDGE, 1)
        self.share_head = mlp(2 * HIDDEN + N_EDGE, 1)
        nn.init.constant_(self.eff_head[-1].bias, 3.0)              # start near "doors work as designed"

    def terms(self, g, people, step, open_):
        """The two learned, bounded terms: door efficiency in [0, 1] and shares that sum to 1."""
        h, e = self.mp(g, people, step, open_)
        x = torch.cat([h[g.t_src], h[g.t_dst], e], 1)
        eff = torch.sigmoid(self.eff_head(x)[:, 0])
        # start from the textbook route (+6 on its door) and let the network move people off it
        share = masked_softmax(self.share_head(x)[:, 0] + 6 * e[:, 2], g.t_src, g.n, open_)
        return eff, share

    def step(self, g, people, step):
        open_ = g.open_at(step)
        eff, share = self.terms(g, people, step, open_)
        return physics_step(g, people, share, eff, open_)


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
    """Roll a model forward; returns people[step][node] (steps x n). Exit nodes keep everyone who left."""
    out = []
    for k in range(steps):
        people = model.step(g, people, start + k)
        out.append(people)
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
def people_with_start(plan, people):
    """Prepend the starting crowd to the simulator's people[step][node]."""
    p0 = np.array([float(n["people0"]) for n in plan["nodes"]], dtype=np.float32)
    people = np.asarray(people, dtype=np.float32).reshape(-1, len(p0))
    return torch.tensor(np.vstack([p0[None], people]))


def sim_runs(seeds, per_plan, max_steps, rng):
    """Make runs directly with engine.evac (the same simulator engine.design_data uses): random plans,
    random layouts, fires, lost exits, panic 0..1."""
    from engine import evac, plans
    runs = []
    for seed in seeds:
        plan = plans.make_plan(int(seed))
        ids = [c["id"] for c in plan["candidates"] if c["id"] != plan["main_entrance"]]
        for _ in range(per_plan):
            exits = [plan["main_entrance"]] + [int(x) for x in rng.choice(ids, size=int(rng.integers(1, 5)), replace=False)]
            fire = plan["fires"][int(rng.integers(len(plan["fires"])))] if rng.random() < 0.5 and plan["fires"] else None
            lost = int(rng.choice(exits)) if fire is None and rng.random() < 0.3 else None
            panic = float(rng.uniform(0, 1))
            r = evac.simulate(plan, exits, fire=fire, panic=panic, lost_exit=lost, max_steps=max_steps)
            runs.append((Graph(plan, exits, fire, panic, lost), people_with_start(plan, r["people"])))
    return runs


def main_runs(max_steps=300):
    """Rows of MAIN's train.npz (or sample.npz) + plans.json, as (graph, people[step][node]) and plan index."""
    plans = json.loads((DATA / "plans.json").read_text())
    f = DATA / "train.npz" if (DATA / "train.npz").exists() else DATA / "sample.npz"
    z = np.load(f, allow_pickle=True)
    runs, plan_of = [], []
    for r in range(len(z["plan_index"])):
        plan = plans[int(z["plan_index"][r])]
        fire = int(z["fire"][r]) if "fire" in z else -1
        lost = int(z["lost_exit"][r]) if "lost_exit" in z and int(z["lost_exit"][r]) >= 0 else None
        g = Graph(plan, int(z["exits"][r]), plan["fires"][fire] if fire >= 0 else None, float(z["panic"][r]), lost)
        people = np.asarray(z["people"][r], dtype=np.float32)[:max_steps, :g.n]
        runs.append((g, people_with_start(plan, people)))
        plan_of.append(int(z["plan_index"][r]))
    print(f"loaded {len(runs)} runs on {len(plans)} plans from {f.name}")
    return runs, np.array(plan_of)


# ---------------------------------------------------------------- training + test
def train(model, runs, iters, horizon=40, lr=2e-3, batch=8):
    """Pick runs and start times, roll the model forward `horizon` steps, match the simulator inside the building.
    Runs in one batch share a start time, so the fire stage is right for all of them.
    Loss = error per node + error in the number of people still inside (what decides the clearance time)."""
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, iters)
    r = np.random.default_rng(0)
    for i in range(iters):
        t0 = int(r.integers(0, 100))
        picks = [runs[int(k)] for k in r.integers(len(runs), size=4 * batch)]
        picks = [(g, t) for g, t in picks if len(t) > t0 + horizon][:batch]
        if not picks:
            continue
        b = Graph.batch([g for g, _ in picks])
        p0 = torch.cat([t[t0] for _, t in picks])
        target = torch.cat([t[t0 + 1:t0 + 1 + horizon] for _, t in picks], 1)
        pred = rollout(model, b, p0, t0, horizon)
        keep = 1 - b.t_exit
        node_err = ((((pred - target) * keep) / 10) ** 2).mean()
        inside_err = (((inside(pred, b) - inside(target, b)) / 10) ** 2).mean()
        loss = node_err + 0.1 * inside_err
        opt.zero_grad(); loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); opt.step(); sched.step()
        if i % 100 == 0:
            print(f"    iter {i:4d}  loss {loss.item():.4f}", flush=True)
    return model


@torch.no_grad()
def test(model, runs, max_steps=300):
    """Full rollouts on floor plans never seen in training: clearance-time error and people created/lost."""
    errs, lost = [], []
    for g, truth in runs:
        pred = rollout(model, g, truth[0], 0, max_steps)
        c_pred = clearance_steps(pred, g)[0]
        c_true = len(truth) - 1 if len(truth) - 1 < max_steps else None    # MAIN's runs stop at clearance
        errs.append(abs((c_pred or max_steps) - (c_true or max_steps)) * g.dt)
        lost.append(float((pred.sum(1) - truth[0].sum()).abs().max()))
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
    ap.add_argument("--quick", action="store_true", help="make runs with engine.evac instead of reading train.npz")
    ap.add_argument("--iters", type=int, default=800)
    a = ap.parse_args()
    torch.manual_seed(0)
    if a.quick:
        rng = np.random.default_rng(0)
        train_runs = sim_runs(range(100, 200), 8, 300, rng)              # 100 plans for training
        test_runs = sim_runs(range(900, 912), 6, 300, rng)               # 12 plans never seen in training
    else:
        runs, plan_of = main_runs()
        unseen = plan_of % 5 == 0                                        # every 5th floor plan is never trained on
        train_runs = [r for r, u in zip(runs, unseen) if not u]
        test_runs = [r for r, u in zip(runs, unseen) if u]
    models = {"physics": PhysicsOnly(), "gnn": GNNOnly(), "pggnn": PGGNN()}
    for name in ("pggnn", "gnn"):
        print("training", name, flush=True)
        train(models[name], train_runs, a.iters)
    res = {"models": {k: test(m, test_runs) for k, m in models.items()},
           "speed": {"pggnn_per_s": speed(models["pggnn"], test_runs[0][0]), "simulator_per_s": sim_speed()},
           "setup": {"source": "engine.evac runs made here (--quick)" if a.quick else "MAIN engine.design_data",
                     "train_runs": len(train_runs), "test_runs": len(test_runs), "dt_s": 2, "max_steps": 300,
                     "unseen": "test floor plans never appear in training", "simulated": True}}
    print(json.dumps(res, indent=1))
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    torch.save(models["pggnn"].state_dict(), OUT / "pggnn.pt")


if __name__ == "__main__":
    main()
