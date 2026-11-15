"""
Which physics should a crowd model use? A fair test of Hamiltonian / Lagrangian mechanics against ours.

All models predict the same 320 evacuations (16 floor plans never used for fitting, from data/design/train.npz)
and are compared with the detailed simulator (engine/evac.py). Each model's free constants are FITTED on
100 training runs first, so every model gets its best shot.

  A. Hamiltonian (frictionless)   people as a fluid that keeps its energy.
       H = sum_e p_e^2 / (2 L_e)  +  sum_i ( g * phi_i * N_i  +  k * N_i^2 / (2 area_i) )
       dN_i/dt = -dH/dp (net flux),   dp_e/dt = -(mu_b - mu_a) / L_e,   mu_i = dH/dN_i = g*phi_i + k*N_i/area_i
       phi_i = walking distance to the nearest open exit (the "height" people roll down). Solved with symplectic Euler,
       the standard energy-preserving integrator. Lagrangian mechanics (Euler-Lagrange equations) gives the SAME
       equations of motion, so this one model covers both.
  B. Hamiltonian + friction       the same, plus a drag term -gamma * p_e (energy is now lost).
  C. Least action (Lagrangian)    every person takes the path of least travel time to the nearest exit
                                  (Fermat / least-action principle = the eikonal equation), with our door and
                                  room limits. This is the "physics only" textbook model.
  D. PG-GNN (ours)                read from research/design/results.json (trained on WIN's machine, same 320 runs).

Design layer: Lagrange multipliers for the exit search
  minimise  J = (number of exits) + lambda * (seconds over the safe limit) / 10
  by local search (add / remove / swap one exit) for a rising lambda, compared with trying every layout.

Run from repo root:  python -m engine.mechanics     (writes data/design/mechanics.json and mechanics.png)
"""
import json
import time
from pathlib import Path

import numpy as np

from engine import design, evac

OUT = Path(__file__).parent.parent / "data" / "design"
ROOT = Path(__file__).parent.parent


# ------------------------------------------------------------------ A / B: Hamiltonian crowd on the graph
def hamiltonian_run(plan, exits, fire, lost, g, k, gamma=0.0, steps=300):
    """Returns inside[step], min_people (most negative node), backflow share, energy drift (frictionless only)."""
    nodes, edges = plan["nodes"], plan["edges"]
    N_, E_, dt = len(nodes), len(edges), plan["dt_s"]
    a = np.array([e["a"] for e in edges]); b = np.array([e["b"] for e in edges])
    L = np.array([e["length_m"] for e in edges])
    area = np.array([max(1.0, n["area_m2"]) for n in nodes])
    is_exit = np.array([n["kind"] == "exit" for n in nodes])
    built = set(exits) - {lost}
    is_open = np.array([e["candidate"] is None or e["candidate"] in built for e in edges])
    close_at = {c["edge"]: c["step"] for c in (fire["close"] if fire else [])}
    exit_nodes = [c["node"] for c in plan["candidates"] if c["id"] in built]

    def heights():
        dist, _ = evac.shortest_paths(N_, edges, is_open, exit_nodes)
        phi = dist.min(1) if dist.shape[1] else np.full(N_, np.inf)
        return np.where(np.isfinite(phi), phi, 300.0)

    phi = heights()
    N = np.array([float(n["people0"]) for n in nodes])
    p = np.zeros(E_)
    inside, uphill, total_flux, energy = [], 0.0, 0.0, []
    for t in range(steps):
        closing = [e for e, s in close_at.items() if s == t and is_open[e]]
        if closing:
            is_open[closing] = False
            phi = heights()
        mu = g * phi + k * N / area
        mu[is_exit] = 0.0
        p = (p + dt * ((mu[a] - mu[b]) / L - gamma * p)) * is_open          # momentum update (symplectic Euler)
        flux = dt * p
        np.add.at(N, a, -flux); np.add.at(N, b, flux)                      # people move with the momentum
        downhill = np.sign(phi[a] - phi[b])                                 # +1 if a -> b goes toward an exit
        uphill += np.abs(flux[(np.sign(flux) * downhill) < 0]).sum()
        total_flux += np.abs(flux).sum()
        N[is_exit] = 0.0                                                     # people who reach an exit are out
        inside.append(N[~is_exit].sum())
        if gamma == 0.0:
            energy.append((p ** 2 * L / 2).sum() + (g * phi * N + k * N ** 2 / (2 * area))[~is_exit].sum())
        if not np.isfinite(N).all() or np.abs(N).max() > 1e6:
            inside += [np.nan] * (steps - t - 1)
            break
    return dict(inside=np.array(inside), min_people=float(np.nanmin(N)) if np.isfinite(N).any() else -1e9,
                backflow=float(uphill / max(total_flux, 1e-9)))


# ------------------------------------------------------------------ C: least action (textbook) via the simulator
def least_action_run(plan, exits, fire, lost, steps=300):
    """The detailed simulator with all human behaviour switched off: nearest exit only, no panic choice, no jam."""
    keep_w, keep_jam = evac.weights, evac.JAM
    evac.weights = lambda panic: dict(dist=60.0, wait=0.0, known=0.0, herd=0.0, rethink=1.0)
    evac.JAM = 0.0
    try:
        r = evac.simulate(plan, exits, fire=fire, lost_exit=lost, panic=0.0, max_steps=steps)
    finally:
        evac.weights, evac.JAM = keep_w, keep_jam
    total = r["total"]
    return dict(inside=total - r["evacuated"], min_people=float(r["people"].min()) if len(r["people"]) else 0.0, backflow=0.0)


# ------------------------------------------------------------------ data + scoring
def load_runs():
    d = np.load(OUT / "train.npz")
    plans_ = json.loads((OUT / "train_plans.json").read_text())
    runs = []
    for i in range(len(d["plan_index"])):
        plan = plans_[d["plan_index"][i]]
        exits = [int(c) for c in np.nonzero(d["exits"][i])[0]]
        fire = plan["fires"][d["fire"][i]] if d["fire"][i] >= 0 else None
        lost = int(d["lost_exit"][i]) if d["lost_exit"][i] >= 0 else None
        total = sum(n["people0"] for n in plan["nodes"])
        steps = int(d["steps"][i])
        truth = total - d["evacuated"][i, :steps]
        clear = int(d["clearance_step"][i])
        runs.append(dict(plan=plan, exits=exits, fire=fire, lost=lost, truth=truth, total=total,
                         clear_s=None if clear < 0 else clear * plan["dt_s"], test=bool(d["is_test"][i])))
    return runs


def clearance_s(inside, dt):
    hit = np.nonzero(np.nan_to_num(inside, nan=1e9) < 1.0)[0]
    return None if len(hit) == 0 else (int(hit[0]) + 1) * dt


def score_runs(runs, model, horizon=300):
    """Clearance error (s), inside-curve error (people), share cleared, most negative people, backflow."""
    errs, curve, cleared, neg, back = [], [], 0, [], []
    for r in runs:
        out = model(r)
        pred = out["inside"][:horizon]
        c = clearance_s(pred, r["plan"]["dt_s"])
        cleared += c is not None
        truth_c = r["clear_s"] if r["clear_s"] is not None else horizon * r["plan"]["dt_s"]
        errs.append(abs((c if c is not None else horizon * r["plan"]["dt_s"]) - truth_c))
        n = min(len(pred), len(r["truth"]))
        curve.append(np.nanmean(np.abs(np.nan_to_num(pred[:n], nan=1e4) - r["truth"][:n])))
        neg.append(out["min_people"]); back.append(out["backflow"])
    e = np.array(errs)
    return dict(clearance_err_s=round(float(e.mean()), 1), ci95=round(float(1.96 * e.std() / np.sqrt(len(e))), 1),
                curve_err_people=round(float(np.mean(curve)), 1), cleared_pct=round(100 * cleared / len(runs), 1),
                most_negative_people=round(float(min(neg)), 1), backflow_pct=round(100 * float(np.mean(back)), 1), runs=len(runs))


def fit(runs, make, grid):
    """Pick the constants with the smallest inside-curve error on training runs (each model gets its best shot)."""
    best = None
    for params in grid:
        s = score_runs(runs, make(*params))
        key = s["curve_err_people"] if np.isfinite(s["curve_err_people"]) else 1e9
        if best is None or key < best[0]:
            best = (key, params)
    return best[1]


# ------------------------------------------------------------------ design layer: Lagrange multipliers
def lagrangian_search(plan, lambdas=(0.5, 1, 2, 4, 8, 16)):
    """Local search on J = exits + lambda * max(0, worst - limit) / 10, lambda rising. Counts simulator calls."""
    cache = {}
    limit, main = plan["safe_limit_s"], plan["main_entrance"]
    ids = [c["id"] for c in plan["candidates"]]

    def worst(layout):
        key = tuple(sorted(layout))
        if key not in cache:
            s = design.score(plan, list(key))
            cache[key] = s["worst_case_s"] if s["worst_case_s"] is not None and s["code_ok"] else float("inf")
        return cache[key]

    def J(layout, lam):
        w = worst(layout)
        return len(layout) + lam * (max(0.0, w - limit) / 10 if np.isfinite(w) else 1e3)

    current = {main, max(ids, key=lambda c: 0 if c == main else 1)}         # start: front door + one more
    for lam in lambdas:
        while True:
            neigh = [current | {c} for c in ids if c not in current]
            neigh += [current - {c} for c in current if c != main and len(current) > 2]
            neigh += [(current - {x}) | {y} for x in current if x != main for y in ids if y not in current]
            best = min(neigh, key=lambda l: J(l, lam))
            if J(best, lam) < J(current, lam) - 1e-9:
                current = best
            else:
                break
    feasible = [(len(l), cache[l], list(l)) for l in cache if cache[l] <= limit]
    pick = min(feasible) if feasible else None
    return dict(exits=pick[2] if pick else None, n_exits=pick[0] if pick else None,
                worst_case_s=pick[1] if pick else None, simulator_calls=len(cache))


def design_comparison():
    """Exhaustive search vs Lagrange-multiplier search, on every building in the switcher."""
    rows = []
    for b in json.loads((OUT / "buildings.json").read_text()):
        plan = json.loads((OUT / b["plan"]).read_text())
        d = json.loads((OUT / b["design"]).read_text())
        m = d["by_panic"][str(design.DESIGN_PANIC)]
        t = time.time()
        lag = lagrangian_search(plan)
        rows.append(dict(building=b["name"], exhaustive_exits=m["chosen_n_exits"], exhaustive_calls=len(m["layouts"]),
                         exhaustive_worst_s=m["chosen"]["worst_case_s"] if m["chosen"] else None,
                         lagrange_exits=lag["n_exits"], lagrange_calls=lag["simulator_calls"], lagrange_worst_s=lag["worst_case_s"],
                         same_answer=lag["n_exits"] == m["chosen_n_exits"], seconds=round(time.time() - t, 1)))
        print(rows[-1], flush=True)
    return rows


# ------------------------------------------------------------------ main
def main():
    runs = load_runs()
    train = [r for r in runs if not r["test"]][::13][:100]
    test = [r for r in runs if r["test"]]
    print(f"fitting on {len(train)} training runs, testing on {len(test)} runs from {len({r['plan']['id'] for r in test})} unseen plans", flush=True)

    ham = lambda g, k: (lambda r: hamiltonian_run(r["plan"], r["exits"], r["fire"], r["lost"], g, k))
    damp = lambda g, k, gm: (lambda r: hamiltonian_run(r["plan"], r["exits"], r["fire"], r["lost"], g, k, gm))
    gs, ks, gms = [0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01], [0.0, 0.2, 1.0, 3.0, 10.0], [0.005, 0.01, 0.02, 0.05, 0.1, 0.2]
    p_ham = fit(train, ham, [(g, k) for g in gs for k in ks])
    print("Hamiltonian fitted", p_ham, flush=True)
    p_damp = fit(train, damp, [(g, k, gm) for g in gs for k in ks for gm in gms])
    print("damped fitted", p_damp, flush=True)

    results = {
        "hamiltonian": dict(label="Hamiltonian / Lagrangian dynamics (energy conserved)", params=dict(zip(["g", "k"], p_ham)),
                            **score_runs(test, ham(*p_ham))),
        "damped": dict(label="Hamiltonian + friction", params=dict(zip(["g", "k", "gamma"], p_damp)),
                       **score_runs(test, damp(*p_damp))),
        "least_action": dict(label="Least action: everyone takes the fastest path (physics only)", **score_runs(test, lambda r: least_action_run(r["plan"], r["exits"], r["fire"], r["lost"]))),
    }
    ours = json.loads((ROOT / "research" / "design" / "results.json").read_text())["models"]
    results["pggnn"] = dict(label="PG-GNN (ours): conservation of people + learned behaviour",
                            clearance_err_s=ours["pggnn"]["clearance_err_s"], ci95=ours["pggnn"]["ci95"], runs=ours["pggnn"]["runs"],
                            source="research/design/results.json (WIN)")
    results["gnn_only"] = dict(label="GNN only (no physics)", clearance_err_s=ours["gnn"]["clearance_err_s"], ci95=ours["gnn"]["ci95"],
                               people_created_or_lost=ours["gnn"]["people_error"], source="research/design/results.json (WIN)")
    for k_, v in results.items():
        print(k_, {x: v[x] for x in v if x not in ("label",)}, flush=True)

    # one example run for the picture: the first test run with a fire
    ex = next(r for r in test if r["fire"] is not None and r["clear_s"])
    example = dict(plan=ex["plan"]["id"], exits=ex["exits"], truth=ex["truth"].round(1).tolist(),
                   hamiltonian=np.nan_to_num(ham(*p_ham)(ex)["inside"], nan=-1).round(1).tolist(),
                   damped=damp(*p_damp)(ex)["inside"].round(1).tolist(),
                   least_action=least_action_run(ex["plan"], ex["exits"], ex["fire"], ex["lost"])["inside"].round(1).tolist())

    print("design layer: exhaustive vs Lagrange multipliers", flush=True)
    rows = design_comparison()
    out = dict(simulated=True, test_runs=len(test), fit_runs=len(train), models=results, example=example, design=rows)
    (OUT / "mechanics.json").write_text(json.dumps(out))
    print("wrote data/design/mechanics.json")


if __name__ == "__main__":
    main()


def picture():
    """data/design/mechanics.png: one example evacuation + the error of every model. Drawn from mechanics.json."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    d = json.loads((OUT / "mechanics.json").read_text())
    SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e6e5e0"
    BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(14, 5.6), facecolor=SURFACE, gridspec_kw=dict(width_ratios=[1.15, 1], wspace=0.22))
    fig.subplots_adjust(left=0.06, right=0.97, top=0.80, bottom=0.12)
    fig.text(0.06, 0.93, "A crowd conserves people, not energy", fontsize=16, color=INK, fontweight="bold")
    fig.text(0.06, 0.875, f"Every model predicts the same {d['test_runs']} evacuations on 16 floor plans it never saw. Simulated crowd. "
             "Each model's constants were fitted first.", fontsize=9.5, color=INK2)
    for a in (ax, bx):
        a.set_facecolor(SURFACE)
        for side in ("top", "right"):
            a.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            a.spines[side].set_color(GRID)
        a.tick_params(colors=MUTED, labelsize=9, length=0)
    e = d["example"]
    t = lambda y: [2 * (i + 1) for i in range(len(y))]
    ax.axhline(0, color=MUTED, lw=1)
    for key, colour, name in (("hamiltonian", ORANGE, "Hamiltonian (energy conserved)"), ("damped", YELLOW, "Hamiltonian + friction"),
                              ("least_action", AQUA, "Least action (physics only)")):
        y = e[key][:150]
        ax.plot(t(y), y, color=colour, lw=2, label=name)
    y = e["truth"]
    ax.plot(t(y), y, color=INK, lw=2.4, label="What the crowd really does (detailed simulation)")
    ax.set_xlim(0, 300); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.set_xlabel("seconds after the alarm", color=INK2, fontsize=9.5); ax.set_ylabel("people still inside", color=INK2, fontsize=9.5)
    ax.set_title("One evacuation: the energy-conserving crowd overshoots below zero people", loc="left", fontsize=11, color=INK, fontweight="bold")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper right")

    m = d["models"]
    rows = [("Hamiltonian + friction", m["damped"]), ("Hamiltonian / Lagrangian\n(energy conserved)", m["hamiltonian"]),
            ("GNN only (no physics)", m["gnn_only"]), ("Least action\n(physics only)", m["least_action"]), ("PG-GNN (ours)", m["pggnn"])]
    names = [r[0] for r in rows]; vals = [r[1]["clearance_err_s"] for r in rows]
    ypos = range(len(rows))
    bx.barh(list(ypos), vals, height=0.56, color=[MUTED] * (len(rows) - 1) + [BLUE])
    for i, v in zip(ypos, vals):
        bx.text(v + 1.5, i, f"{v:.1f} s", va="center", fontsize=10, color=INK, fontweight="bold" if i == len(rows) - 1 else "normal")
    bx.set_yticks(list(ypos)); bx.set_yticklabels(names, fontsize=9.5, color=INK2); bx.invert_yaxis()
    bx.set_xlim(0, max(vals) * 1.18); bx.grid(axis="x", color=GRID, lw=0.8); bx.set_axisbelow(True)
    bx.set_xlabel("average error in the time to get everyone out (seconds, lower is better)", color=INK2, fontsize=9.5)
    bx.set_title("Error on unseen floor plans", loc="left", fontsize=11, color=INK, fontweight="bold")
    fig.savefig(OUT / "mechanics.png", dpi=130, facecolor=SURFACE)
    print("wrote data/design/mechanics.png")
