"""
Floor plans as graphs (task M1). One floor of a building:

    nodes   rooms, corridor pieces, and one "exit" node per place an exit COULD go (a candidate)
    edges   doors and corridor passages, each with a width (m) and a length (m)

An exit LAYOUT is just a list of candidate ids that are built. A candidate that is not built is a
wall: its edge is closed. The architect's question is: which candidates do we build?

Run from repo root:  python -m engine.plans      (writes data/design/demo_plan.json)
"""
import json
import random
from pathlib import Path

CELL = 6.0                 # metres between two corridor pieces (the drawing grid)
CORRIDOR_AREA = CELL * 2.4  # one corridor piece: 6 m long, 2.4 m wide
SIDES = [(1, 0), (-1, 0), (0, 1), (0, -1)]

# What the textbook knows. These go into every plan so WIN's physics model uses the same numbers.
CONSTANTS = dict(
    dt_s=2.0,               # one simulation step
    max_density=4.0,        # people per m2 a space can hold
    flow_per_m_s=1.3,       # people per second through each metre of door width
    walk_speed_m_s=1.3,     # free walking speed
    safe_limit_s=150.0,     # everyone must be out by this time (design parameter, set by the fire engineer)
    max_travel_m=45.0,      # longest allowed walk from a room to its nearest exit (code-style rule, a parameter)
)


def corridor_cells(shape, rng):
    """Corridor pieces on an integer grid, for four common building shapes."""
    if shape == "bar":
        n = rng.randint(7, 10)
        return [(x, 0) for x in range(n)]
    if shape == "L":
        n, m = rng.randint(5, 7), rng.randint(3, 4)
        return [(x, 0) for x in range(n)] + [(n - 1, y) for y in range(1, m + 1)]
    if shape == "T":
        n, m = rng.randint(7, 9), rng.randint(3, 4)
        return [(x, 0) for x in range(n)] + [(n // 2, y) for y in range(1, m + 1)]
    if shape == "ring":
        w, h = rng.randint(5, 6), 4
        top = [(x, 0) for x in range(w)]
        bottom = [(x, h - 1) for x in range(w)]
        sides = [(0, y) for y in range(1, h - 1)] + [(w - 1, y) for y in range(1, h - 1)]
        return top + bottom + sides
    raise ValueError(shape)


# Building types for the page's plan switcher. Each one only changes what the rooms are like.
STYLES = dict(
    apartment=dict(label="Apartment floor", room="Flat", area=(55, 95), density=[0.05, 0.07, 0.09], doors=[0.9, 1.0], corridor=1.8, fill=0.95),
    school=dict(label="School wing", room="Classroom", area=(55, 70), density=[0.5, 0.6, 0.65], doors=[1.0, 1.2], corridor=2.4, fill=0.9),
    office=dict(label="Office floor", room="Office", area=(40, 120), density=[0.1, 0.15, 0.2, 0.3], doors=[0.9, 1.2, 1.8], corridor=2.4, fill=0.85),
    cinema=dict(label="Cinema level", room="Screen", area=(110, 160), density=[0.7, 0.8, 0.9], doors=[1.8, 2.4], corridor=3.0, fill=0.25),
)


def make_plan(seed, shape=None, n_candidates=10, name=None, style=None):
    """Build one random floor plan. Same seed -> same plan. style = one of STYLES (None = the general mix)."""
    st = STYLES.get(style)
    rng = random.Random(seed)
    shape = shape or rng.choice(["bar", "L", "T", "ring"])
    cells = corridor_cells(shape, rng)
    used = set(cells)                                   # grid squares already taken
    nodes, edges, candidates = [], [], []
    cell_node = {}

    SIZE = dict(room=5.4, corridor=6.0, exit=3.0)        # drawing size of each tile in metres (for the page only)
    count = dict(room=0, corridor=0, exit=0)

    def add_node(kind, gx, gy, area, people):
        count[kind] += 1
        label = dict(room=st["room"] if st else "Room", corridor="Corridor", exit="Exit")[kind] + " " + (chr(64 + count[kind]) if kind == "exit" else str(count[kind]))
        nodes.append(dict(id=len(nodes), kind=kind, name=label, x=gx * CELL, y=gy * CELL, w_m=SIZE[kind], h_m=SIZE[kind],
                          area_m2=round(area, 1), people0=people))
        return len(nodes) - 1

    def add_edge(a, b, width, length, candidate=None):
        edges.append(dict(a=a, b=b, width_m=width, length_m=length, candidate=candidate))
        return len(edges) - 1

    # 1. corridor pieces, joined to their grid neighbours
    corridor_width = st["corridor"] if st else rng.choice([1.8, 2.4, 3.0])
    for c in cells:
        cell_node[c] = add_node("corridor", c[0], c[1], CORRIDOR_AREA, 0)
    for (x, y) in cells:
        for dx, dy in [(1, 0), (0, 1)]:
            if (x + dx, y + dy) in cell_node:
                add_edge(cell_node[(x, y)], cell_node[(x + dx, y + dy)], corridor_width, CELL)
    n_corridor_edges = len(edges)

    # 2. candidate exits: free squares beside the corridor. Dead ends first, then spread along the walls.
    def free_sides(c):
        return [(c[0] + dx, c[1] + dy) for dx, dy in SIDES if (c[0] + dx, c[1] + dy) not in used]

    def n_corridor_neighbours(c):
        return sum((c[0] + dx, c[1] + dy) in cell_node for dx, dy in SIDES)

    spots = []                                           # (corridor cell, free square)
    for c in cells:                                      # dead ends: the exit straight ahead
        if n_corridor_neighbours(c) == 1:
            (nx, ny), = [(c[0] + dx, c[1] + dy) for dx, dy in SIDES if (c[0] + dx, c[1] + dy) in cell_node]
            ahead = (2 * c[0] - nx, 2 * c[1] - ny)
            if ahead not in used:
                spots.append((c, ahead)); used.add(ahead)
    others = [(c, f) for c in cells for f in free_sides(c)]
    rng.shuffle(others)
    for keep_apart in (True, False):                     # first spread them out, then fill up to n_candidates
        for c, f in others:
            if len(spots) >= n_candidates:
                break
            near = keep_apart and any(abs(c[0] - c2[0]) + abs(c[1] - c2[1]) < 2 for c2, _ in spots)
            taken = any(c == c2 for c2, _ in spots)      # one candidate per corridor piece
            if f not in used and not near and not taken:
                spots.append((c, f)); used.add(f)
    main = rng.randrange(len(spots))                     # the front door people came in through
    for i, (c, f) in enumerate(spots):
        exit_node = add_node("exit", f[0], f[1], 0.0, 0)
        width = 2.4 if i == main else 1.8
        add_edge(cell_node[c], exit_node, width, 3.0, candidate=i)
        candidates.append(dict(id=i, node=exit_node, attach_to=cell_node[c], width_m=width,
                               familiarity=1.0 if i == main else round(rng.uniform(0.05, 0.45), 2)))

    # 3. rooms on the remaining free squares
    for c in cells:
        for f in free_sides(c):
            if rng.random() < (st["fill"] if st else 0.8):
                used.add(f)
                area = rng.uniform(*(st["area"] if st else (40, 110)))
                people = int(round(area * rng.choice(st["density"] if st else [0.15, 0.3, 0.45, 0.6])))
                room = add_node("room", f[0], f[1], area, people)
                add_edge(room, cell_node[c], rng.choice(st["doors"] if st else [0.9, 1.2, 1.8]), 4.0)

    # 4. fires: each one cuts the corridor at one place, 10 s after the alarm
    cut_edges = list(range(n_corridor_edges))
    rng.shuffle(cut_edges)
    fires = [dict(id=i, start_node=edges[e]["a"], close=[dict(edge=e, step=5)]) for i, e in enumerate(sorted(cut_edges[:4]))]

    plan = dict(id=f"plan_{seed}" if not st else f"{style}_{seed}", name=name or (st["label"] if st else f"{shape} plan {seed}"),
                shape=shape, building=style or "general", **CONSTANTS,
                nodes=nodes, edges=edges, candidates=candidates, main_entrance=main, fires=fires)
    return plan


def total_people(plan):
    return sum(n["people0"] for n in plan["nodes"])


DEMO_SEED, DEMO_SHAPE = 7, "ring"


def demo_plan():
    return make_plan(DEMO_SEED, DEMO_SHAPE, n_candidates=10, name="Demo: community hall, one floor")


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "data" / "design"
    out.mkdir(parents=True, exist_ok=True)
    p = demo_plan()
    (out / "demo_plan.json").write_text(json.dumps(p, indent=1))
    print(p["name"], "| nodes", len(p["nodes"]), "| edges", len(p["edges"]), "| candidates", len(p["candidates"]),
          "| people", total_people(p), "| main entrance = candidate", p["main_entrance"])
