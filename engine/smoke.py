"""
SMOKE layer (the PG-CNN's job): where does the smoke go, and which corridors does it block, and when?

The floor plan is drawn onto a grid (an image): every 6 m tile of the plan becomes 3 x 3 cells of 2 m.
Physics, per cell, every step (dt = 2 s):
    smoke_next = smoke + fire source - vented + spread in from linked neighbours - spread out
    spread     = SPREAD x (difference in smoke) across every open link (inside a room, through a door)
    vented     = vent x smoke                      windows and vents let smoke out
Smoke is never created except at the fire, and only leaves through vents.

What the textbook does NOT know: how well each room really vents. It assumes one number everywhere.
HIDDEN truth: rooms with more window area vent much more (see true_vent). The PG-CNN must learn that from
what the architect's drawing shows (room or corridor, size, window share).

A corridor piece is BLOCKED when the smoke in it passes BLOCK. Those block times become the fire scenario
(the same {edge, step} list the evacuation model and the PG-GNN already read).

Run from repo root:  python -m engine.smoke            (writes data/design/smoke_demo.json, smoke_sample.npz,
                                                        smoke_train.npz, and adds "smoke_fires" to demo_plan.json)
"""
import json
import random
from pathlib import Path

import numpy as np

from engine import plans

OUT = Path(__file__).parent.parent / "data" / "design"
SUB = 3                      # cells per tile side
H, W = 24, 42                # fixed image size (plans are padded into it)
STEPS = 75                   # 150 s
SPREAD = 0.2                 # share of the smoke difference that moves across a link per step
SOURCE = 0.12                # smoke added per fire cell per step (assumption: first corridor blocked ~1 min after ignition)
VENT_TEXTBOOK = 0.03         # what the textbook assumes for every room and corridor
VENT_MAX = 0.15              # the most any space can vent per step
BLOCK = 0.6                  # smoke level at which a corridor piece cannot be walked through


def true_vent(kind, windows):
    """HIDDEN: how much smoke a space really loses per step. The PG-CNN is never told this formula."""
    if kind == "corridor":
        return 0.01
    return 0.015 + 0.13 * windows ** 2          # a room with big windows clears smoke fast


def add_windows(plan):
    """Give every room a window share 0..1 (an input the architect knows). Own random stream, so plans stay the same."""
    rng = random.Random(hash(plan["id"]) % 10 ** 6 if False else sum(map(ord, plan["id"])) * 7 + 1)
    for n in plan["nodes"]:
        n["windows"] = round(rng.random(), 2) if n["kind"] == "room" else 0.0
    return plan


def grid(plan):
    """Draw the plan as an image. Returns dict with:
    inside[H,W] 1 where there is floor; node[H,W] node id (-1 outside); link_r / link_d [H,W] 1 if smoke can pass
    to the cell on the right / below; feats[4,H,W] = is room, is corridor, area/100, window share."""
    if "windows" not in plan["nodes"][0]:
        add_windows(plan)
    xs = [n["x"] for n in plan["nodes"]]; ys = [n["y"] for n in plan["nodes"]]
    gx0, gy0 = round(min(xs) / plans.CELL), round(min(ys) / plans.CELL)
    node = np.full((H, W), -1, dtype=int)
    tile = {}
    for n in plan["nodes"]:
        if n["kind"] == "exit":
            continue                                         # exits are outside air; smoke does not travel through them
        tx, ty = round(n["x"] / plans.CELL) - gx0, round(n["y"] / plans.CELL) - gy0
        tile[n["id"]] = (tx, ty)
        node[ty * SUB:(ty + 1) * SUB, tx * SUB:(tx + 1) * SUB] = n["id"]
    inside = (node >= 0).astype(np.float32)
    link_r = np.zeros((H, W), np.float32); link_d = np.zeros((H, W), np.float32)
    link_r[:, :-1] = (node[:, :-1] == node[:, 1:]) & (node[:, :-1] >= 0)      # same space: open
    link_d[:-1, :] = (node[:-1, :] == node[1:, :]) & (node[:-1, :] >= 0)
    kind = {n["id"]: n["kind"] for n in plan["nodes"]}
    for e in plan["edges"]:                                  # doors and corridor joints between two tiles
        if e["candidate"] is not None:
            continue
        (ax, ay), (bx, by) = tile[e["a"]], tile[e["b"]]
        wide = kind[e["a"]] == "corridor" and kind[e["b"]] == "corridor"
        rows = range(SUB) if wide else [1]                   # corridor joint: full width; room door: one cell
        if ay == by:
            x = min(ax, bx) * SUB + SUB - 1
            for r in rows:
                link_r[ay * SUB + r, x] = 1
        else:
            y = min(ay, by) * SUB + SUB - 1
            for r in rows:
                link_d[y, ax * SUB + r] = 1
    feats = np.zeros((4, H, W), np.float32)
    vent = np.zeros((H, W), np.float32)
    for n in plan["nodes"]:
        if n["id"] in tile:
            m = node == n["id"]
            feats[0][m] = n["kind"] == "room"; feats[1][m] = n["kind"] == "corridor"
            feats[2][m] = n["area_m2"] / 100; feats[3][m] = n["windows"]
            vent[m] = true_vent(n["kind"], n["windows"])
    return dict(inside=inside, node=node, link_r=link_r, link_d=link_d, feats=feats, vent_true=vent, tile=tile)


def step(s, src, vent, g):
    """One step of the smoke physics (numpy). The PG-CNN uses the same step with its own vent."""
    s = s + src
    fr = SPREAD * g["link_r"][:, :-1] * (s[:, :-1] - s[:, 1:])           # flow to the right neighbour
    fd = SPREAD * g["link_d"][:-1, :] * (s[:-1, :] - s[1:, :])           # flow to the neighbour below
    s = s.copy()
    s[:, :-1] -= fr; s[:, 1:] += fr
    s[:-1, :] -= fd; s[1:, :] += fd
    return s * (1 - vent) * g["inside"]


def run(plan, start_node, vent=None, g=None, steps=STEPS):
    """Smoke for one fire. Returns smoke[steps, H, W]. vent=None uses the hidden truth."""
    g = g or grid(plan)
    vent = g["vent_true"] if vent is None else vent
    src = SOURCE * (g["node"] == start_node)
    s = np.zeros((H, W), np.float32)
    out = []
    for _ in range(steps):
        s = step(s, src, vent, g)
        out.append(s)
    return np.array(out, dtype=np.float32)


def blocked_edges(plan, smoke, g):
    """When does smoke block each corridor passage? A passage closes at the first step where the smoke in BOTH
    corridor pieces it joins has passed BLOCK (the smoke has filled across it). Returns [{edge, step}] by step."""
    level = {n: smoke[:, g["node"] == n].mean(1) for n in g["tile"]}      # mean smoke per node per step
    kind = {n["id"]: n["kind"] for n in plan["nodes"]}
    out = []
    for i, e in enumerate(plan["edges"]):
        if e["candidate"] is None and kind[e["a"]] == "corridor" and kind[e["b"]] == "corridor":
            hit = np.nonzero(np.minimum(level[e["a"]], level[e["b"]]) >= BLOCK)[0]
            if len(hit):
                out.append(dict(edge=i, step=int(hit[0]) + 1))
    return sorted(out, key=lambda c: c["step"])


def smoke_fire(plan, start_node, fire_id=0, vent=None, g=None):
    """A fire scenario in the format the evacuation model reads, made by the smoke model."""
    g = g or grid(plan)
    return dict(id=fire_id, start_node=start_node, close=blocked_edges(plan, run(plan, start_node, vent, g), g))


def fire_starts(plan, n=3):
    """Corridor pieces where a fire could start (the existing fire scenarios' start nodes, so they are comparable)."""
    return [f["start_node"] for f in plan["fires"]][:n]


def dataset(n_plans=60, name="smoke_train", first_seed=5000):
    """Training set for the PG-CNN: smoke[R, STEPS, H, W], feats[R, 4, H, W], inside, link_r, link_d, source, is_test."""
    rows = []
    for i in range(n_plans):
        p = add_windows(plans.make_plan(first_seed + i))
        g = grid(p)
        for start in fire_starts(p):
            rows.append((i, g, start, run(p, start, g=g)))
    n_test = max(1, n_plans // 5)
    d = dict(plan_index=np.array([r[0] for r in rows], np.int32),
             is_test=np.array([r[0] >= n_plans - n_test for r in rows], np.int8),
             smoke=np.array([r[3] for r in rows], np.float32),
             feats=np.array([r[1]["feats"] for r in rows]), inside=np.array([r[1]["inside"] for r in rows]),
             link_r=np.array([r[1]["link_r"] for r in rows]), link_d=np.array([r[1]["link_d"] for r in rows]),
             source=np.array([SOURCE * (r[1]["node"] == r[2]) for r in rows], np.float32),
             vent_true=np.array([r[1]["vent_true"] for r in rows]))
    np.savez_compressed(OUT / f"{name}.npz", **d)
    print(f"{name}: {len(rows)} fires on {n_plans} plans ({n_test} held out), smoke {d['smoke'].shape}")


def demo_for(plan):
    """For one plan: add smoke-made fire scenarios to it, and return the smoke frames the page draws."""
    add_windows(plan)
    g = grid(plan)
    textbook = np.where(g["feats"][0] + g["feats"][1] > 0, VENT_TEXTBOOK, 0).astype(np.float32)
    fires, shown = [], []
    for i, start in enumerate(fire_starts(plan)):
        truth, book = run(plan, start, g=g), run(plan, start, textbook, g)
        fire = dict(id=i, start_node=start, close=blocked_edges(plan, truth, g))
        fires.append(fire)
        shown.append(dict(fire=i, start_node=start, close=fire["close"], close_textbook=blocked_edges(plan, book, g),
                          smoke=np.round(truth[::3], 2).tolist(), smoke_textbook=np.round(book[::3], 2).tolist()))
    plan["smoke_fires"] = fires
    return dict(
        simulated=True, sub=SUB, cell_m=plans.CELL / SUB, dt_s=plan["dt_s"], frame_every_steps=3, block_level=BLOCK,
        height=H, width=W, inside=g["inside"].astype(int).tolist(), node=g["node"].tolist(),
        origin_tile=[round(min(n["x"] for n in plan["nodes"]) / plans.CELL), round(min(n["y"] for n in plan["nodes"]) / plans.CELL)],
        fires=shown)


def demo():
    """Demo plan: smoke frames for the page + smoke-made fire scenarios + what the textbook would have predicted."""
    path = OUT / "demo_plan.json"
    plan = json.loads(path.read_text())
    shown = demo_for(plan)
    path.write_text(json.dumps(plan, indent=1))
    (OUT / "smoke_demo.json").write_text(json.dumps(shown))
    for f in shown["fires"]:
        print("fire at node", f["start_node"], "| truth blocks", [(c["edge"], c["step"] * 2) for c in f["close"]],
              "| textbook says", [(c["edge"], c["step"] * 2) for c in f["close_textbook"]], "(edge, seconds)")


if __name__ == "__main__":
    demo()
    dataset(20, "smoke_sample")
    dataset(60, "smoke_train")
