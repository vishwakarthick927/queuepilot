"""
Stand-in floor plans in the BUILD.md "Contract" shape, used ONLY until MAIN's engine/plans.py lands.

A plan is a graph: rooms and corridor segments are nodes, doors are edges. Candidate exits are
nodes of kind "exit" that are only connected (attach_to -> exit) when the layout picks them.

    python -m research.design.toyplans      # writes a stub demo plan for the page
"""
import json
from pathlib import Path

import numpy as np

STUB_DIR = Path(__file__).resolve().parents[2] / "frontend" / "src" / "design" / "stub"


def make_plan(seed, n_seg=6, name=None):
    """A corridor spine running west -> east, rooms on both sides, exits possible at the ends,
    on the corridor's side walls and on the outer walls of some rooms."""
    r = np.random.default_rng(seed)
    nodes, edges, cands = [], [], []

    def node(kind, x, y, area, people=0, w=2.0, h=2.0, name=""):
        """w_m, h_m, name are optional drawing hints for the page (not used by the models)."""
        nodes.append({"id": len(nodes), "kind": kind, "x": round(float(x), 1), "y": round(float(y), 1),
                      "area_m2": round(float(area), 1), "people0": int(people),
                      "w_m": round(float(w), 1), "h_m": round(float(h), 1), "name": name})
        return len(nodes) - 1

    seg_len, cor_w = 12.0, 2.4
    spine = [node("corridor", 6 + seg_len * k, 0, seg_len * cor_w, 0, seg_len, cor_w, f"Corridor {k + 1}") for k in range(n_seg)]
    for a, b in zip(spine, spine[1:]):
        edges.append({"a": a, "b": b, "width_m": cor_w, "length_m": seg_len})
    rooms = []
    for k, c in enumerate(spine):
        for side in (-1, 1):
            if r.random() < 0.15:
                continue                                    # an empty plot on this side
            area = r.uniform(60, 160) if not (k == 1 and side == 1) else 420.0   # one big hall
            depth = area / seg_len
            people = area * r.uniform(0.3, 0.9) if area < 400 else area * 1.0
            rm = node("room", 6 + seg_len * k, side * (cor_w / 2 + depth / 2), area, people, seg_len, depth,
                      "Hall" if area >= 400 else f"Room {len(rooms) + 1}")
            edges.append({"a": rm, "b": c, "width_m": 1.8 if area > 400 else round(float(r.choice([0.9, 1.2, 1.5])), 1),
                          "length_m": round(depth / 2, 1)})
            rooms.append((rm, side, depth))

    def cand(attach, x, y, fam, width=1.5):
        ex = node("exit", x, y, 0, name=f"Exit E{len(cands) + 1}")
        cands.append({"id": f"E{len(cands) + 1}", "node": ex, "attach_to": attach, "width_m": width, "familiarity": fam})

    cand(spine[0], 0 - 3, 0, 1.0, 2.0)                      # west end = main entrance (everyone knows it)
    cand(spine[-1], 6 + seg_len * (n_seg - 1) + 9, 0, round(float(r.uniform(0.2, 0.5)), 2))
    for rm, side, depth in rooms:
        if len(cands) >= 12:
            break
        if r.random() < 0.7 or nodes[rm]["area_m2"] > 400:
            n = nodes[rm]
            cand(rm, n["x"], n["y"] + side * (depth / 2 + 2), round(float(r.uniform(0.05, 0.3)), 2), 1.2)
    fires = []
    for f, start in enumerate(r.choice([rm for rm, _, _ in rooms], size=min(3, len(rooms)), replace=False)):
        near = [i for i, e in enumerate(edges) if start in (e["a"], e["b"])]
        fires.append({"id": f"F{f + 1}", "start_node": int(start), "close": [{"edge": i, "step": 15} for i in near]})
    return {"id": f"toy-{seed}", "name": name or f"Toy plan {seed}", "safe_limit_s": 240, "dt_s": 2,
            "max_density": 4.0, "flow_per_m_s": 1.3, "nodes": nodes, "edges": edges,
            "candidates": cands, "main_entrance": "E1", "fires": fires}


def demo_plan():
    return make_plan(7, n_seg=7, name="Convention block, ground floor (stub)")


if __name__ == "__main__":
    STUB_DIR.mkdir(parents=True, exist_ok=True)
    p = demo_plan()
    (STUB_DIR / "demo_plan.json").write_text(json.dumps(p, indent=1))
    print(len(p["nodes"]), "nodes,", len(p["edges"]), "edges,", len(p["candidates"]), "candidates,",
          sum(n["people0"] for n in p["nodes"]), "people")
