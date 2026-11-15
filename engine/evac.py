"""
Detailed evacuation simulator (task M2). This is the "truth" the PG-GNN is trained and checked against.

People are counted per node and per the exit they are heading for. Every step (dt seconds):
  1. CHOOSE   people pick an exit (see exit_probabilities). Calm people pick the nearest, least queued exit.
              Panicked people pick the exit they know and the exit everyone else is running to.
  2. MOVE     people walk one edge along the shortest open path to their exit. They walk slower in a dense space.
  3. DOORS    a door passes at most  width x flow_per_m_s x dt  people per step (both directions share it).
              HIDDEN: under panic a door that is pushed on passes LESS (it jams).
  4. ROOM     a space takes in only as many people as it has room for (area x max_density).
  5. FIRE     edges close at their fire step; people behind them re-route or are trapped.
Nobody is ever created or lost: every person is in a node or counted as evacuated.

What the textbook (WIN's "physics only" model) does NOT know: the HIDDEN constants below.
"""
import heapq
import numpy as np

# ---- hidden behaviour (the PG-GNN is never told these) ----
JAM = 0.55          # how much capacity a door loses when panicked people push on it
MIN_SPEED = 0.15    # walking speed never drops below 15% of free speed


def weights(panic):
    """How people weigh an exit. panic 0 = calm, 1 = full panic."""
    return dict(dist=1.5 - 1.0 * panic,     # per 10 m of walking
                wait=1.0 * (1 - panic),     # per 10 s of queue at the exit
                known=0.5 + 3.5 * panic,    # familiarity of the exit (0..1)
                herd=2.5 * panic,           # share of the crowd already heading there
                rethink=0.02 + 0.10 * (1 - panic))   # share of people who reconsider each step


def shortest_paths(n_nodes, edges, is_open, exit_nodes):
    """Dijkstra from every exit. Returns dist[node, k] in metres and hop[node, k] = directed edge to take
    (2*e if walking a->b on edge e, 2*e+1 if b->a, -1 if exit k cannot be reached)."""
    nbrs = [[] for _ in range(n_nodes)]
    for e, ed in enumerate(edges):
        if is_open[e]:
            nbrs[ed["a"]].append((ed["b"], ed["length_m"], 2 * e + 1))   # from b you step b->a
            nbrs[ed["b"]].append((ed["a"], ed["length_m"], 2 * e))       # from a you step a->b
    dist = np.full((n_nodes, len(exit_nodes)), np.inf)
    hop = np.full((n_nodes, len(exit_nodes)), -1)
    for k, x in enumerate(exit_nodes):
        dist[x, k] = 0.0
        heap = [(0.0, x)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist[u, k]:
                continue
            for v, length, step_edge in nbrs[u]:
                if d + length < dist[v, k]:
                    dist[v, k] = d + length
                    hop[v, k] = step_edge
                    heapq.heappush(heap, (d + length, v))
    return dist, hop


def exit_probabilities(dist, wait_s, known, share, w):
    """Softmax over exits of: -distance - queue + familiarity + herd. Unreachable exits get probability 0."""
    u = -w["dist"] * dist / 10.0 - w["wait"] * wait_s / 10.0 + w["known"] * known + w["herd"] * share
    u = np.where(np.isfinite(dist), u, -np.inf)
    u = u - np.max(np.where(np.isfinite(u), u, -1e9), axis=1, keepdims=True)
    p = np.where(np.isfinite(u), np.exp(u), 0.0)
    s = p.sum(1, keepdims=True)
    return np.divide(p, s, out=np.zeros_like(p), where=s > 0)


def simulate(plan, exits, fire=None, panic=0.0, lost_exit=None, max_steps=300, record=True,
             arrivals=None, gate_eff=None, open_at=None, guide=None, jam=None):
    """Run one evacuation.
    exits      candidate ids that are built          fire   a fire dict from plan["fires"], or None
    lost_exit  a built candidate blocked from t=0    panic  0..1
    Returns people[step][node], flow[step][edge] (net a->b), evacuated[step], clearance_s (None if not cleared),
    trapped (people who can reach no exit), exit_use {candidate id: people}.
    Extra inputs used by the crowd (stampede) scenarios in engine/crowd.py; all default to "off":
      arrivals {step: [(node, people)]}  people who arrive later      gate_eff {candidate: 0..1}  a gate that is partly shut
      open_at {candidate: step}  a built gate that only opens then     guide {step: (share, {candidate: familiarity})}
      jam  overrides the hidden door-jam constant (the forecaster passes 0: it does not know it)"""
    arrivals, gate_eff, open_at, guide = arrivals or {}, gate_eff or {}, open_at or {}, guide or {}
    jam_k = JAM if jam is None else jam
    nodes, edges, cands = plan["nodes"], plan["edges"], plan["candidates"]
    N, E, dt = len(nodes), len(edges), plan["dt_s"]
    built = [c for c in cands if c["id"] in set(exits)]
    exit_nodes = [c["node"] for c in built]
    K = len(built)
    known = np.array([c["familiarity"] for c in built])
    area = np.array([n["area_m2"] for n in nodes])
    room_for = np.where(np.array([n["kind"] == "exit" for n in nodes]), np.inf, area * plan["max_density"])
    width = np.array([e["width_m"] for e in edges])
    length = np.array([e["length_m"] for e in edges])
    cap0 = width * plan["flow_per_m_s"] * dt                       # textbook door capacity per step
    head = np.empty(2 * E + 1, dtype=int)                          # node you arrive at on each directed edge
    head[0:2 * E:2] = [e["b"] for e in edges]
    head[1:2 * E:2] = [e["a"] for e in edges]
    head[2 * E] = 0                                                # dummy "no move" edge
    is_open = np.array([e["candidate"] is None or (e["candidate"] in set(exits) and e["candidate"] != lost_exit
                                                   and open_at.get(e["candidate"], 0) <= 0) for e in edges])
    for e_i, e in enumerate(edges):                                # a partly shut gate passes less
        if e["candidate"] in gate_eff:
            cap0[e_i] *= gate_eff[e["candidate"]]
    close_at = {c["edge"]: c["step"] for c in (fire["close"] if fire else [])}
    exit_edge = {c["id"]: next(i for i, e in enumerate(edges) if e["candidate"] == c["id"]) for c in built}
    exit_cap_s = np.array([cap0[exit_edge[c["id"]]] / dt for c in built])
    attach = np.array([c["attach_to"] for c in built])
    w = weights(panic)

    dist, hop = shortest_paths(N, edges, is_open, exit_nodes)
    people0 = np.array([float(n["people0"]) for n in nodes])
    total = people0.sum() + sum(n for lst in arrivals.values() for _, n in lst)
    P = people0[:, None] * exit_probabilities(dist, np.zeros(K), known, np.zeros(K), w)   # P[node, exit]
    P[:, 0] += people0 - P.sum(1)                                  # people with no reachable exit wait in column 0
    out_per_exit = np.zeros(K)
    rec_people, rec_flow, rec_out = [], [], []
    clearance_step = None
    cols = np.arange(K)[None, :].repeat(N, 0)

    for t in range(max_steps):
        # FIRE: close edges, re-route
        closing = [e for e, s in close_at.items() if s == t and is_open[e]]
        opening = [exit_edge[c] for c, s in open_at.items() if s == t and c in exit_edge and c != lost_exit]
        if closing or opening:
            is_open[closing] = False
            is_open[opening] = True
            dist, hop = shortest_paths(N, edges, is_open, exit_nodes)
        if t in guide:                                              # announcements / signs: people learn about other gates
            for c, fam in guide[t][1].items():
                known[[b["id"] for b in built].index(c)] = fam
        n = P.sum(1)

        # CHOOSE: some people reconsider; anyone heading for an exit they can no longer reach must re-choose
        share = P.sum(0) / max(P.sum(), 1e-9)
        wait_s = P[attach, np.arange(K)] / exit_cap_s
        prob = exit_probabilities(dist, wait_s, known, share, w)
        can_choose = prob.sum(1) > 0
        stuck = np.where(np.isfinite(dist), 0.0, P)                # heading for an unreachable exit
        stuck[~can_choose] = 0.0
        rethink = max(w["rethink"], guide[t][0]) if t in guide else w["rethink"]
        moving_on = rethink * (P - stuck) * can_choose[:, None]
        P = P - stuck - moving_on + (stuck.sum(1) + moving_on.sum(1))[:, None] * prob
        for node, n_new in arrivals.get(t, []):                     # late arrivals pick a gate like everyone else
            P[node] += n_new * prob[node] if can_choose[node] else n_new * (np.arange(K) == 0)
        n = P.sum(1)

        # MOVE: how many WANT to step along their next edge this step
        speed = plan["walk_speed_m_s"] * np.clip(1 - (n / np.maximum(area, 1e-9)) / plan["max_density"], MIN_SPEED, 1)
        hop_e = np.where(hop >= 0, hop, 2 * E)
        step_len = np.append(np.repeat(length, 2), 1.0)[hop_e]
        want = P * np.minimum(1.0, speed[:, None] * dt / step_len) * (hop >= 0)

        # DOORS: both directions share the door; HIDDEN jam under panic
        demand = np.bincount(hop_e.ravel(), weights=want.ravel(), minlength=2 * E + 1)[:2 * E]
        both = demand[0::2] + demand[1::2]
        jam = 1 - jam_k * panic * np.clip((both / np.maximum(cap0, 1e-9) - 1) / 2, 0, 1)
        cap = cap0 * jam * is_open
        door = np.append(np.repeat(np.minimum(1.0, cap / np.maximum(both, 1e-9)), 2), 0.0)
        go = want * door[hop_e]

        # ROOM: the receiving space must have room
        arriving = np.bincount(head[hop_e].ravel(), weights=go.ravel(), minlength=N)
        space = np.minimum(1.0, np.maximum(room_for - n, 0) / np.maximum(arriving, 1e-9))
        go = go * space[head[hop_e]]

        # UPDATE: conservation. What leaves a node arrives at the next one.
        P = P - go
        np.add.at(P, (head[hop_e].ravel(), cols.ravel()), go.ravel())
        out_now = P[exit_nodes, :].sum(1)
        out_per_exit += out_now
        P[exit_nodes, :] = 0.0

        if record:
            f = np.bincount(hop_e.ravel(), weights=go.ravel(), minlength=2 * E + 1)[:2 * E]
            rec_people.append(P.sum(1)); rec_flow.append(f[0::2] - f[1::2]); rec_out.append(out_per_exit.sum())
        if total - out_per_exit.sum() < 1.0 and clearance_step is None:
            clearance_step = t + 1
            break

    left = P.sum(1)
    reachable = np.isfinite(dist).any(1)
    return dict(
        people=np.array(rec_people, dtype=np.float32), flow=np.array(rec_flow, dtype=np.float32),
        evacuated=np.array(rec_out, dtype=np.float32), total=float(total),
        clearance_step=clearance_step, clearance_s=None if clearance_step is None else clearance_step * dt,
        remaining=float(left.sum()), trapped=float(left[~reachable].sum()),
        exit_use={c["id"]: float(out_per_exit[k]) for k, c in enumerate(built)})
