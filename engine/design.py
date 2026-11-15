"""
Exit design (tasks M4, M5): which candidate exits should the architect build?

  score(plan, layout)   run the detailed simulator for one layout under EVERY scenario:
                        no fire, each corridor fire, and "the fire blocks exit X" for each built exit.
                        The layout's score is its WORST clearance time. It passes only if everyone gets out
                        within plan["safe_limit_s"] in every scenario and the code-style rules hold.
  search(plan)          try every layout (the main entrance is always built) and rank them.
  rule_of_thumb(plan,k) what a designer does without a tool: k exits spread as far apart as possible.
  flow_bound(plan,l)    max-flow: the fastest ANY crowd could leave through these exits; min-cut = the bottleneck.
  verify(plan,layouts)  M5: re-check layouts chosen by the PG-GNN in the detailed simulator.

Run from repo root:  python -m engine.design            (writes data/design/design.json)
                     python -m engine.design verify "[[1,4],[1,2,5]]"
"""
import itertools
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np

from engine import evac, plans

OUT = Path(__file__).parent.parent / "data" / "design"
PANIC_LEVELS = [0.0, 0.4, 0.8]
DESIGN_PANIC = 0.8            # layouts are judged under panic, not ideal behaviour
EXIT_CORE_M2 = 20.0           # floor area one exit (door, lobby, protected route) takes: a stated assumption


def scenarios(plan, layout, fires_key="fires"):
    """Every situation a layout must survive: (label, fire, lost_exit).
    fires_key="smoke_fires" uses the fire scenarios made by the smoke model (engine/smoke.py) instead."""
    out = [("no fire", None, None)]
    out += [(f"fire {f['id']} cuts the corridor", f, None) for f in plan[fires_key]]
    out += [(f"fire blocks exit {c}", None, c) for c in layout]
    return out


def travel_ok(plan, layout):
    """Code-style rules: at least 2 exits, and no room further than max_travel_m from its nearest exit."""
    if len(layout) < 2:
        return False, None
    built = [c for c in plan["candidates"] if c["id"] in layout]
    is_open = [e["candidate"] is None or e["candidate"] in layout for e in plan["edges"]]
    dist, _ = evac.shortest_paths(len(plan["nodes"]), plan["edges"], is_open, [c["node"] for c in built])
    rooms = [n["id"] for n in plan["nodes"] if n["kind"] == "room"]
    worst = float(dist[rooms].min(1).max())
    return worst <= plan["max_travel_m"], round(worst, 1)


def score(plan, layout, panic=DESIGN_PANIC, fires_key="fires"):
    """Worst-case clearance time of one layout. A scenario that never clears counts as a failure."""
    layout = sorted(layout)
    worst_s, worst_label, no_fire_s, failed = 0.0, None, None, False
    for label, fire, lost in scenarios(plan, layout, fires_key):
        r = evac.simulate(plan, layout, fire=fire, lost_exit=lost, panic=panic, record=False)
        t = r["clearance_s"]
        if label == "no fire":
            no_fire_s = t
        if t is None:                                   # people still inside after max_steps, or trapped
            failed, t = True, float("inf")
        if t > worst_s:
            worst_s, worst_label = t, label
    code_ok, travel = travel_ok(plan, layout)
    passes = (not failed) and worst_s <= plan["safe_limit_s"] and code_ok
    return dict(exits=layout, clearance_s=no_fire_s, worst_case_s=None if failed else worst_s, worst_fire=worst_label,
                passes=bool(passes), code_ok=bool(code_ok), max_travel_m=travel)


def all_layouts(plan, k):
    """Every layout with k exits. The main entrance is always one of them (the building has a front door)."""
    main = plan["main_entrance"]
    others = [c["id"] for c in plan["candidates"] if c["id"] != main]
    return [sorted((main,) + combo) for combo in itertools.combinations(others, k - 1)]


def rule_of_thumb(plan, k):
    """Spread k exits as far apart as possible (farthest-point rule), starting from the main entrance."""
    xy = {c["id"]: (plan["nodes"][c["node"]]["x"], plan["nodes"][c["node"]]["y"]) for c in plan["candidates"]}
    chosen = [plan["main_entrance"]]
    while len(chosen) < k:
        def gap(c):
            return min((xy[c][0] - xy[d][0]) ** 2 + (xy[c][1] - xy[d][1]) ** 2 for d in chosen)
        chosen.append(max((c for c in xy if c not in chosen), key=gap))
    return sorted(chosen)


def sort_key(s):
    return (not s["passes"], s["worst_case_s"] if s["worst_case_s"] is not None else 1e9)


def search(plan, k_max=None, panic=DESIGN_PANIC):
    """Score every layout for k = 2..k_max. Returns {k: layouts sorted best first}."""
    k_max = k_max or len(plan["candidates"])
    return {k: sorted((score(plan, l, panic) for l in all_layouts(plan, k)), key=sort_key) for k in range(2, k_max + 1)}


def fewest_passing(ranked):
    """Smallest k with a passing layout, and that layout."""
    for k in sorted(ranked):
        if ranked[k][0]["passes"]:
            return k, ranked[k][0]
    return None, None


def fewest_rule_of_thumb(plan, panic=DESIGN_PANIC):
    for k in range(2, len(plan["candidates"]) + 1):
        s = score(plan, rule_of_thumb(plan, k), panic)
        if s["passes"]:
            return k, s
    return None, None


def flow_bound(plan, layout):
    """Max-flow (Edmonds-Karp, written out): the most people per second that can leave through these exits if
    everyone behaved perfectly. total_people / that rate is a lower bound on clearance time.
    The min-cut is the set of doors that limit it: widen those first."""
    n = len(plan["nodes"])
    S, T = n, n + 1
    cap = {}

    def add(u, v, c):
        cap[(u, v)] = cap.get((u, v), 0.0) + c
        cap.setdefault((v, u), 0.0)

    for e in plan["edges"]:
        if e["candidate"] is None or e["candidate"] in layout:
            c = e["width_m"] * plan["flow_per_m_s"]
            add(e["a"], e["b"], c); add(e["b"], e["a"], c)
    for nd in plan["nodes"]:
        if nd["people0"] > 0:
            add(S, nd["id"], 1e9)
        if nd["kind"] == "exit":
            add(nd["id"], T, 1e9)
    nbrs = {}
    for (u, v) in cap:
        nbrs.setdefault(u, []).append(v)

    def bfs():
        parent = {S: None}
        q = deque([S])
        while q:
            u = q.popleft()
            for v in nbrs.get(u, []):
                if v not in parent and cap[(u, v)] > 1e-9:
                    parent[v] = u
                    q.append(v)
        return parent

    rate = 0.0
    while True:
        parent = bfs()
        if T not in parent:
            break
        path, v = [], T
        while parent[v] is not None:
            path.append((parent[v], v)); v = parent[v]
        push = min(cap[e] for e in path)
        for (u, v) in path:
            cap[(u, v)] -= push; cap[(v, u)] += push
        rate += push
    reach = bfs()                                        # nodes still reachable from the source = source side of the cut
    cut = [i for i, e in enumerate(plan["edges"])
           if (e["candidate"] is None or e["candidate"] in layout) and ((e["a"] in reach) != (e["b"] in reach))]
    total = plans.total_people(plan)
    return dict(rate_per_s=round(rate, 2), bound_s=round(total / rate, 1) if rate > 0 else None, min_cut=cut)


def verify(plan, layouts, panic=DESIGN_PANIC):
    """M5: WIN calls this with the PG-GNN's top layouts. Returns their true scores from the detailed simulator."""
    return [score(plan, l, panic) for l in layouts]


def smoke_check(plan, chosen, k_max=5):
    """End-to-end check of the two-model pipeline: fire scenarios made by the SMOKE model (several corridors
    closing over time) instead of the simple one-cut fires. Does the chosen layout still pass? What is best?"""
    key = "smoke_fires"
    out = dict(chosen=score(plan, chosen, fires_key=key), rule_same_count=score(plan, rule_of_thumb(plan, len(chosen)), fires_key=key))
    for k in range(2, k_max + 1):
        best = min((score(plan, l, fires_key=key) for l in all_layouts(plan, k)), key=sort_key)
        rule = score(plan, rule_of_thumb(plan, k), fires_key=key)
        out.setdefault("curve", []).append(dict(n_exits=k, ours_s=best["worst_case_s"], ours_passes=best["passes"], ours_exits=best["exits"],
                                                rule_s=rule["worst_case_s"], rule_passes=rule["passes"]))
    out["fewest_ours"] = next((c["n_exits"] for c in out["curve"] if c["ours_passes"]), None)
    out["fewest_rule"] = next((c["n_exits"] for c in out["curve"] if c["rule_passes"]), None)
    return out


def frames(plan, layout, panic, fire=None, lost_exit=None, label="no fire"):
    """People per node per step, for the page's animation (1 decimal to keep the file small)."""
    r = evac.simulate(plan, layout, fire=fire, lost_exit=lost_exit, panic=panic)
    return dict(exits=sorted(layout), scenario=label, fire=None if fire is None else fire["id"], lost_exit=lost_exit,
                panic=panic, clearance_s=r["clearance_s"], people=np.round(r["people"], 1).tolist(),
                evacuated=np.round(r["evacuated"], 1).tolist(),
                exit_use={str(k): round(v, 1) for k, v in r["exit_use"].items()})


def worst_scenario(plan, layout, panic=DESIGN_PANIC):
    """The scenario (label, fire, lost_exit) in which this layout does worst."""
    def t(sc):
        r = evac.simulate(plan, layout, fire=sc[1], lost_exit=sc[2], panic=panic, record=False)
        return r["clearance_s"] if r["clearance_s"] is not None else float("inf")
    return max(scenarios(plan, layout), key=t)


def demo_frames(plan, chosen, rule_layout):
    """Both layouts in the SAME scenario: the one where the rule-of-thumb layout does worst.
    If that scenario blocks an exit only one layout has, fall back to the worst corridor fire for the rule layout."""
    label, fire, lost = worst_scenario(plan, rule_layout)
    if lost is not None and lost not in chosen:
        label, fire, lost = max(((l, f, x) for l, f, x in scenarios(plan, rule_layout) if f is not None),
                                key=lambda sc: evac.simulate(plan, rule_layout, fire=sc[1], panic=DESIGN_PANIC, record=False)["clearance_s"] or 1e9)
    return dict(chosen=frames(plan, chosen, DESIGN_PANIC, fire, lost, label),
                rule_of_thumb=frames(plan, rule_layout, DESIGN_PANIC, fire, lost, label)), label, fire


def across_plans(n_plans=20, first_seed=1000):
    """Honesty check: not just the demo plan. On random plans, how many exits does each approach need?"""
    rows = []
    for seed in range(first_seed, first_seed + n_plans):
        p = plans.make_plan(seed, n_candidates=8)
        k_ours, _ = fewest_passing(search(p, k_max=5))
        k_rule, _ = fewest_rule_of_thumb(p)
        rows.append(dict(plan=p["id"], shape=p["shape"], people=plans.total_people(p), ours=k_ours, rule=k_rule))
    both = [r for r in rows if r["ours"] and r["rule"]]
    return dict(n_plans=n_plans, solved_both=len(both),
                mean_exits_ours=round(float(np.mean([r["ours"] for r in both])), 2) if both else None,
                mean_exits_rule=round(float(np.mean([r["rule"] for r in both])), 2) if both else None,
                plans_where_ours_needs_fewer=sum(r["ours"] < r["rule"] for r in both),
                plans_where_rule_never_passes=sum(1 for r in rows if r["ours"] and not r["rule"]),
                plans_where_nothing_passes=sum(1 for r in rows if not r["ours"]), rows=rows)


def build(plan, with_across=True):
    by_panic = {}
    for panic in PANIC_LEVELS:
        ranked = search(plan, panic=panic)
        k, best = fewest_passing(ranked)
        k_rule, rule = fewest_rule_of_thumb(plan, panic)
        curve = [dict(n_exits=kk, ours_s=ranked[kk][0]["worst_case_s"], ours_passes=ranked[kk][0]["passes"],
                      rule_s=(s := score(plan, rule_of_thumb(plan, kk), panic))["worst_case_s"], rule_passes=s["passes"])
                 for kk in sorted(ranked)]
        by_panic[str(panic)] = dict(
            panic=panic, chosen=best, chosen_n_exits=k, rule_of_thumb=rule, rule_n_exits=k_rule,
            rule_same_count=None if k is None else score(plan, rule_of_thumb(plan, k), panic),
            exits_saved=None if (k is None or k_rule is None) else k_rule - k,
            area_freed_m2=None if (k is None or k_rule is None) else (k_rule - k) * EXIT_CORE_M2,
            curve=curve, layouts=[l for kk in sorted(ranked) for l in ranked[kk]])
    main = by_panic[str(DESIGN_PANIC)]
    chosen = main["chosen"]["exits"] if main["chosen"] else rule_of_thumb(plan, 2)
    same_count_rule = rule_of_thumb(plan, len(chosen))
    calm = score(plan, chosen, 0.0)
    fr, fr_label, fr_fire = demo_frames(plan, chosen, same_count_rule)
    bound = flow_bound(plan, chosen)
    out = dict(
        plan=plan["id"], safe_limit_s=plan["safe_limit_s"], design_panic=DESIGN_PANIC, panic_levels=PANIC_LEVELS,
        exit_core_m2=EXIT_CORE_M2, m2_per_exit=EXIT_CORE_M2, simulated=True,
        chosen=main["chosen"], rule_of_thumb=main["rule_of_thumb"], by_panic=by_panic,
        bound_maxflow_s=bound["bound_s"], min_cut=bound["min_cut"], maxflow_rate_per_s=bound["rate_per_s"],
        cost_of_panic=dict(calm_s=calm["worst_case_s"], panic_s=main["chosen"]["worst_case_s"] if main["chosen"] else None),
        frames=fr, frames_scenario=fr_label, frames_fire=None if fr_fire is None else fr_fire["id"])
    if with_across:
        out["across_plans"] = across_plans()
    return out


BUILDINGS = [("apartment", "bar", 12), ("school", "L", 12), ("office", "T", 11), ("cinema", "ring", 11)]


def build_buildings():
    """The other buildings for the page's plan switcher. Same pipeline as the demo hall, 8 exit positions each.
    Writes data/design/buildings/<id>/{plan,design,smoke}.json and the index data/design/buildings.json."""
    from engine import smoke
    index = [dict(id="hall", name="Community hall", building="hall", people=plans.total_people(json.loads((OUT / "demo_plan.json").read_text())),
                  plan="demo_plan.json", design="design.json", smoke="smoke_demo.json")]
    for style, shape, seed in BUILDINGS:
        plan = plans.make_plan(seed, shape, n_candidates=8, style=style)
        shown = smoke.demo_for(plan)
        d = build(plan, with_across=False)
        chosen = d["chosen"]["exits"] if d["chosen"] else rule_of_thumb(plan, 2)
        d["smoke_check"] = smoke_check(plan, chosen)
        d["frames_smoke"] = {str(f["id"]): dict(
            chosen=frames(plan, chosen, DESIGN_PANIC, f, None, f"smoke fire {f['id']}"),
            rule_of_thumb=frames(plan, rule_of_thumb(plan, len(chosen)), DESIGN_PANIC, f, None, f"smoke fire {f['id']}")) for f in plan["smoke_fires"]}
        folder = OUT / "buildings" / style
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "plan.json").write_text(json.dumps(plan, indent=1))
        (folder / "design.json").write_text(json.dumps(d))
        (folder / "smoke.json").write_text(json.dumps(shown))
        index.append(dict(id=style, name=plan["name"], building=style, people=plans.total_people(plan),
                          plan=f"buildings/{style}/plan.json", design=f"buildings/{style}/design.json", smoke=f"buildings/{style}/smoke.json"))
        m = d["by_panic"][str(DESIGN_PANIC)]
        print(style, "| people", plans.total_people(plan), "| ours", m["chosen_n_exits"], m["chosen"] and (m["chosen"]["exits"], m["chosen"]["worst_case_s"]),
              "| spread evenly needs", m["rule_n_exits"], "| evenly, same count:", m["rule_same_count"] and (m["rule_same_count"]["worst_case_s"], m["rule_same_count"]["passes"]),
              "| smoke check ours/rule", d["smoke_check"]["fewest_ours"], d["smoke_check"]["fewest_rule"], "| frames:", d["frames_scenario"])
    (OUT / "buildings.json").write_text(json.dumps(index, indent=1))


if __name__ == "__main__":
    plan = json.loads((OUT / "demo_plan.json").read_text())
    if len(sys.argv) > 2 and sys.argv[1] == "verify":
        print(json.dumps(verify(plan, json.loads(sys.argv[2])), indent=1))
    elif len(sys.argv) > 1 and sys.argv[1] == "buildings":
        build_buildings()
    elif len(sys.argv) > 1 and sys.argv[1] == "smoke":            # needs demo_plan.json with smoke_fires (python -m engine.smoke)
        d = json.loads((OUT / "design.json").read_text())
        d["smoke_check"] = smoke_check(plan, d["chosen"]["exits"])
        (OUT / "design.json").write_text(json.dumps(d))
        print({k: v for k, v in d["smoke_check"].items() if k != "curve"}); print(d["smoke_check"]["curve"])
    elif len(sys.argv) > 1 and sys.argv[1] == "across":          # slow part, added to the existing file
        d = json.loads((OUT / "design.json").read_text())
        d["across_plans"] = across_plans()
        (OUT / "design.json").write_text(json.dumps(d))
        print({k: v for k, v in d["across_plans"].items() if k != "rows"})
    else:
        d = build(plan, with_across=False)
        (OUT / "design.json").write_text(json.dumps(d))
        m = d["by_panic"][str(DESIGN_PANIC)]
        print("chosen", m["chosen"]); print("rule  ", m["rule_of_thumb"]); print("rule, same count", m["rule_same_count"])
        print("bound", d["bound_maxflow_s"], "min cut", d["min_cut"], "| cost of panic", d["cost_of_panic"])
