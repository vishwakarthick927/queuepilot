"""
The flood twin: water -> people -> queues, for one storm, two ways. Exports what the browser plays back.

  TODAY       people leave when water is already in their street; they take the shortest road
              that is dry RIGHT NOW to the nearest shelter, and queue there.
  QUEUEPILOT  people leave when the AI forecast says their street floods within 2 hours; the route
              avoids roads the AI says will be under water by the time they get there (graph search);
              the shelter is picked by travel time + expected wait at its intake desks (the queue).
Same storm, same people, same roads. The real (simulated) water decides who gets through.

Run after water.py:  .venv/Scripts/python -m research.flood.twin
"""
import heapq
import json
from pathlib import Path

import numpy as np
import torch

from research.flood import water as W

OUT = Path(__file__).parent
WEB = OUT.parent.parent / "frontend" / "src" / "flood" / "twin.json"
STORM_SEED = 104
STEPS = 96                       # 8 hours, 14:00 -> 22:00
GROUP = 100                      # people per evacuation group (one bus / convoy)
SPEED = 2.0 / 8                  # km per minute on wet roads (2 km road segment = 8 min)
SEG_KM = 2.0
HOME_DEEP = 0.6                  # water this deep at home = trapped, needs a boat rescue
DESKS, DESK_MIN = 2, 6           # each shelter: 2 registration desks, 6 min per group
ALERT_AHEAD = 24                 # QueuePilot evacuates when flooding is forecast within 2 h (24 steps)

# ---------------------------------------------------------------- roads: a grid of junctions every 4 cells (2 km)
NODES = [(x, y) for y in range(2, W.NY, 4) for x in range(2, W.NX, 4)]
idx = {p: i for i, p in enumerate(NODES)}
EDGES = []
for (x, y) in NODES:
    for dx, dy in [(4, 0), (0, 4)]:
        if (x + dx, y + dy) in idx:
            cells = [(x + round(dx * k / 4), y + round(dy * k / 4)) for k in range(5)]
            EDGES.append((idx[(x, y)], idx[(x + dx, y + dy)], cells))
ADJ = {i: [] for i in range(len(NODES))}
for e, (a, b, _) in enumerate(EDGES):
    ADJ[a].append((b, e)); ADJ[b].append((a, e))


def nearest_node(x, y):
    return min(range(len(NODES)), key=lambda i: (NODES[i][0] - x) ** 2 + (NODES[i][1] - y) ** 2)


def edge_depth(frames, e, t):
    """Deepest water on road segment e at step t."""
    return max(frames[min(t, len(frames) - 1)][y, x] for x, y in EDGES[e][2])


def route(src, dsts, blocked):
    """Shortest path (in segments) from src to any shelter node, skipping blocked(edge, arrival_step)."""
    seg_steps = SEG_KM / SPEED / W.DT_MIN
    best = {src: 0.0}; prev = {}
    pq = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if u in dsts:
            path = [u]
            while path[-1] != src:
                path.append(prev[path[-1]][0])
            path.reverse()
            edges = [prev[n][1] for n in path[1:]]
            return path, edges, d
        if d > best.get(u, 1e9):
            continue
        for v, e in ADJ[u]:
            nd = d + seg_steps
            if blocked(e, nd) or nd >= best.get(v, 1e9):
                continue
            best[v] = nd; prev[v] = (u, e)
            heapq.heappush(pq, (nd, v))
    return None


# ---------------------------------------------------------------- the city's people and shelters
def pick_zones_and_shelters(frames):
    peak = frames.max(0)
    z = W.CITY["z"]
    # neighbourhoods: places that really flood in this storm + a few that stay dry
    cand = sorted(((peak[y, x], x, y) for (x, y) in NODES if not W.CITY["river"][y, x]), reverse=True)
    zones, used = [], set()
    for depth, x, y in cand:
        if len(zones) == 9:
            break
        if all(abs(x - a) + abs(y - b) > 6 for a, b in used):
            used.add((x, y))
            zones.append({"x": x, "y": y, "groups": int(np.random.default_rng(x * 31 + y).integers(14, 30))})
    names = ["Lakeside", "Old Market", "Riverbend", "Tank Road", "Mill Colony", "Hill View", "Station Road", "Temple Street", "Ring Road East"]
    for zn, nm in zip(zones, names):
        zn["name"] = nm
    # shelters: schools on the highest dry junctions, spread out
    high = sorted(((z[y, x], x, y) for (x, y) in NODES if peak[y, x] < 0.05), reverse=True)
    shelters, used = [], set()
    for _, x, y in high:
        if len(shelters) == 4:
            break
        if all(abs(x - a) + abs(y - b) > 12 for a, b in used):
            used.add((x, y))
            shelters.append({"x": x, "y": y, "name": f"Shelter {len(shelters) + 1}", "capacity": 70})
    return zones, shelters


# ---------------------------------------------------------------- one storm, one policy
def evacuate(policy, frames, forecasts, zones, shelters):
    shelter_nodes = {idx[(s["x"], s["y"])]: i for i, s in enumerate(shelters)}
    desk_free = [[0.0] * DESKS for _ in shelters]
    load = [0] * len(shelters)
    groups = []
    for zi, zn in enumerate(zones):
        node = idx[(zn["x"], zn["y"])]
        # when does this zone start leaving?
        start = None
        for t in range(STEPS):
            if policy == "today" and frames[t][zn["y"], zn["x"]] >= 0.15:
                start = t; break
            if policy == "queuepilot" and t % 3 == 0 and forecasts[t] is not None and forecasts[t][zn["y"], zn["x"]] <= ALERT_AHEAD:
                start = t; break
        for g in range(zn["groups"]):
            dep = None if start is None else start + g * 0.5          # two groups leave every 5 minutes
            rec = {"zone": zi, "depart": dep, "path": [], "times": [], "shelter": None, "arrive": None, "start": None, "trapped": None}
            groups.append(rec)
            if dep is None:
                continue
            t0 = int(dep)
            if frames[min(t0, STEPS - 1)][zn["y"], zn["x"]] >= HOME_DEEP:
                rec["trapped"] = {"t": dep, "x": zn["x"], "y": zn["y"], "where": "home"}
                continue
            if policy == "today":
                blocked = lambda e, d, t0=t0: edge_depth(frames, e, t0) >= W.FLOOD_M          # dry right now?
            else:
                fc = forecasts[t0 - t0 % 3] if forecasts[t0 - t0 % 3] is not None else None
                blocked = lambda e, d, fc=fc: fc is not None and min(fc[y, x] for x, y in EDGES[e][2]) <= d + 6   # will it be dry when I pass (+30 min margin)?
            # shelter choice: today = nearest; QueuePilot = travel + expected queue at the desks
            best = None
            for snode, si in shelter_nodes.items():
                r = route(node, {snode}, blocked)
                if r is None or load[si] >= shelters[si]["capacity"]:
                    continue
                path, edges, steps_ = r
                cost = steps_ if policy == "today" else steps_ + max(0.0, min(desk_free[si]) - (dep + steps_) * W.DT_MIN) / W.DT_MIN
                if best is None or cost < best[0]:
                    best = (cost, si, path, edges, steps_)
            if best is None:
                rec["trapped"] = {"t": dep, "x": zn["x"], "y": zn["y"], "where": "no dry road"}
                continue
            _, si, path, edges, _ = best
            # drive it: the REAL water decides
            tt = dep; rec["path"] = [list(NODES[n]) for n in path]; rec["times"] = [round(tt * W.DT_MIN, 1)]
            stuck = False
            for e in edges:
                tt += SEG_KM / SPEED / W.DT_MIN
                if edge_depth(frames, e, int(tt)) >= W.FLOOD_M:
                    a, b, cells = EDGES[e]
                    mx, my = cells[2]
                    rec["trapped"] = {"t": tt, "x": mx, "y": my, "where": "road flooded"}
                    stuck = True; break
                rec["times"].append(round(tt * W.DT_MIN, 1))
            if stuck:
                continue
            load[si] += 1
            arrive = tt * W.DT_MIN
            d = min(range(DESKS), key=lambda k: desk_free[si][k])
            begin = max(arrive, desk_free[si][d]); desk_free[si][d] = begin + DESK_MIN
            rec.update(shelter=si, arrive=round(arrive, 1), start=round(begin, 1))
    peak = frames.max(0)
    floods = [peak[z["y"], z["x"]] >= W.FLOOD_M for z in zones]          # did this neighbourhood really flood?
    at_risk = [g for g in groups if floods[g["zone"]]]
    safe = [g for g in at_risk if g["shelter"] is not None and g["start"] is not None]
    trapped = [g for g in at_risk if g["shelter"] is None]                 # trapped on a road, at home, or never left
    needless = [g for g in groups if not floods[g["zone"]] and g["depart"] is not None]
    waits = [g["start"] - g["arrive"] for g in groups if g["shelter"] is not None]
    lead = [g["depart"] for g in at_risk if g["depart"] is not None]
    return groups, {
        "people_in_flooding_areas": len(at_risk) * GROUP,
        "people_safe": len(safe) * GROUP,
        "people_trapped": len(trapped) * GROUP,
        "needless_evacuations": len(needless) * GROUP,
        "avg_shelter_wait_min": round(float(np.mean(waits)), 1) if waits else 0,
        "max_shelter_wait_min": round(float(np.max(waits)), 1) if waits else 0,
        "first_departure_min": round(min(lead) * W.DT_MIN) if lead else None,
    }


def main():
    rain = W.storm(STORM_SEED, STEPS)
    frames = W.truth_run(rain).numpy()
    eff = torch.tensor(np.load(OUT / "eff_learned.npy"), dtype=torch.float32)
    rain_t = torch.tensor(rain, dtype=torch.float32)

    # the AI forecast, re-run every 15 minutes from the observed water: steps until each cell floods
    def forecast(t, efficiency):
        h0 = torch.tensor(frames[t - 1] if t > 0 else np.zeros((W.NY, W.NX)), dtype=torch.float32).unsqueeze(0)
        r = rain_t[t:t + 36]                                    # rain radar: next 3 h (assumed known)
        if len(r) == 0:
            return None
        with torch.no_grad():
            hs = W.run(h0, r.unsqueeze(0), efficiency.unsqueeze(0))[0].numpy()
        when = np.full((W.NY, W.NX), 999.0)
        for k in range(len(hs) - 1, -1, -1):
            when[hs[k] >= W.FLOOD_M] = k
        return when
    forecasts = [forecast(t, eff) if t % 3 == 0 else None for t in range(STEPS)]
    phys = [forecast(t, torch.ones(W.NY, W.NX)) if t % 3 == 0 else None for t in range(STEPS)]

    zones, shelters = pick_zones_and_shelters(frames)
    runs = {p: evacuate(p, frames, forecasts, zones, shelters) for p in ["today", "queuepilot"]}
    for p, (_, m) in runs.items():
        print(p, m)

    # for the browser: per step, cells the AI says will flood within 2 h (and what physics alone says)
    def soon(fc_list):
        out, last = [], None
        for t in range(STEPS):
            if fc_list[t] is not None:
                last = fc_list[t]
            cells = [] if last is None else [int(y * W.NX + x) for y, x in zip(*np.where((last <= 24) & (frames[t] < W.FLOOD_M)))]
            out.append(cells)
        return out
    roads_flood_at = [next((t for t in range(STEPS) if edge_depth(frames, e, t) >= W.FLOOD_M), None) for e in range(len(EDGES))]
    data = {
        "nx": W.NX, "ny": W.NY, "steps": STEPS, "step_min": W.DT_MIN, "flood_m": W.FLOOD_M, "group": GROUP,
        "z": np.round(W.CITY["z"] - W.CITY["z"].min(), 1).tolist(),
        "river": W.CITY["river"].astype(int).tolist(),
        "eff_true": np.round(W.CITY["eff_true"], 2).tolist(), "eff_learned": np.round(eff.numpy(), 2).tolist(),
        "depth_cm": [np.round(f * 100).astype(int).tolist() for f in frames],
        "rain_mmh": [np.round(r * 12000).astype(int).tolist() for r in rain],     # m per 5 min -> mm/h
        "ai_soon": soon(forecasts), "physics_soon": soon(phys),
        "nodes": NODES, "edges": [[a, b] for a, b, _ in EDGES], "edge_flood_step": roads_flood_at,
        "zones": zones, "shelters": shelters,
        "runs": {p: {"groups": g, "metrics": m} for p, (g, m) in runs.items()},
        "water_results": json.loads((OUT / "water_results.json").read_text()),
    }
    WEB.parent.mkdir(parents=True, exist_ok=True)
    WEB.write_text(json.dumps(data, separators=(",", ":")))
    print("exported", WEB, round(WEB.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
