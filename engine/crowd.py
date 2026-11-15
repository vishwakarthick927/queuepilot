"""
STAMPEDE PREVENTION (QueuePilot Live). Four venues, one engine.

A venue is a graph: zones (roads, plazas, halls, platforms) joined by passages, with gates that let people through.
People ARRIVE over time and head for a gate. The same crowd physics as engine/evac.py moves them:
conservation of people, door limits, room limits, slower walking when dense, and the HIDDEN behaviour
(everyone runs to the gate they know; pushed gates jam; one gate is secretly half shut).

For every venue we run three things:
  TODAY          nobody intervenes. When does a zone pass the danger density?
  FORECAST       the control room's twin. It knows the layout and the expected arrivals (tickets, train timings),
                 NOT the hidden gate problem. Every 30 s it re-learns each gate's real throughput from the counts
                 so far (physics + a learned correction: the paper's residual idea) and rolls the crowd forward.
                 The ALARM is the first moment it predicts danger. Warning = danger time - alarm time.
                 The TEXTBOOK twin (no learning) is run too, for comparison.
  WITH QUEUEPILOT at the alarm, try every combination of the venue's actions (open a gate, announce other gates,
                 hold arrivals) and apply the one with the lowest peak density.

Run from repo root:  python -m engine.crowd       (writes data/crowd/index.json and data/crowd/<venue>.json)
All numbers are SIMULATED. Venues are schematic layouts inspired by real incidents, not reconstructions of them.
"""
import itertools
import json
from pathlib import Path

import numpy as np

from engine import evac

OUT = Path(__file__).parent.parent / "data" / "crowd"
DT = 5.0                 # seconds per step
STEPS = 480              # 40 minutes
DANGER = 4.0             # people per m2: above this, people can no longer move freely (parameter, cite before quoting)
MAX_DENSITY = 6.0        # people per m2 a space can physically hold
PANIC = 0.8
FRAME = 6                # save one frame every 30 s


def venue(vid, name, place, inspired_by, zones, links, gates, arrivals, actions, note):
    """Build a venue in the same graph format as the floor plans.
    zones  [(name, area_m2, x, y, w, h, is_source)]      links [(zone a, zone b, width_m, length_m)]
    gates  [(name, zone it opens from, width_m, familiarity, hidden efficiency, open at start?)]
    arrivals [(source zone, total people, start_min, end_min)]   people arrive on a smooth bell curve
    actions [(id, label, kind, params)]"""
    nodes, edges, cands = [], [], []
    idx = {}
    for (zn, area, x, y, w, h, src) in zones:
        idx[zn] = len(nodes)
        nodes.append(dict(id=len(nodes), kind="room", name=zn, x=x, y=y, w_m=w, h_m=h, area_m2=area, people0=0, source=bool(src)))
    for (a, b, width, length) in links:
        edges.append(dict(a=idx[a], b=idx[b], width_m=width, length_m=length, candidate=None))
    for i, (gn, zn, width, fam, eff, is_open) in enumerate(gates):
        z = nodes[idx[zn]]
        nodes.append(dict(id=len(nodes), kind="exit", name=gn, x=z["x"], y=z["y"] - z["h_m"] / 2 - 14, w_m=18, h_m=10, area_m2=0.0, people0=0, source=False))
        edges.append(dict(a=idx[zn], b=len(nodes) - 1, width_m=width, length_m=10.0, candidate=i))
        cands.append(dict(id=i, node=len(nodes) - 1, attach_to=idx[zn], width_m=width, familiarity=fam, name=gn, hidden_eff=eff, open=bool(is_open)))
    sched = {}
    for (zn, total, t0, t1) in arrivals:                      # bell-shaped arrivals between t0 and t1 minutes
        s0, s1 = int(t0 * 60 / DT), int(t1 * 60 / DT)
        wts = np.sin(np.linspace(0, np.pi, s1 - s0)) ** 2
        for s, wgt in zip(range(s0, s1), wts / wts.sum()):
            sched.setdefault(s, []).append((idx[zn], float(total * wgt)))
    plan = dict(id=vid, name=name, place=place, inspired_by=inspired_by, note=note, dt_s=DT, max_density=MAX_DENSITY,
                danger_density=DANGER, flow_per_m_s=1.3, walk_speed_m_s=1.3, nodes=nodes, edges=edges, candidates=cands,
                main_entrance=max(range(len(cands)), key=lambda c: cands[c]["familiarity"]), fires=[],
                actions=[dict(id=a, label=l, kind=k, params=p) for a, l, k, p in actions])
    return plan, sched


def run(plan, sched, gate_eff, open_now, extra=None, jam=None):
    """One simulation. extra = dict(open_at, guide, arrivals) from applied actions."""
    extra = extra or {}
    exits = [c["id"] for c in plan["candidates"] if c["open"] or c["id"] in extra.get("open_at", {})]
    open_at = {c: s for c, s in extra.get("open_at", {}).items()}
    return evac.simulate(plan, exits, panic=PANIC, max_steps=STEPS, arrivals=extra.get("arrivals", sched),
                         gate_eff=gate_eff, open_at=open_at, guide=extra.get("guide"), jam=jam)


def density(plan, r):
    """people per m2 in every zone at every step (gates excluded), padded to STEPS."""
    area = np.array([n["area_m2"] if n["kind"] != "exit" else np.inf for n in plan["nodes"]])
    d = r["people"] / area
    if len(d) < STEPS:
        d = np.vstack([d, np.zeros((STEPS - len(d), d.shape[1]))])
    return d


def watched(plan):
    """Zones where a crush can happen: everything except the open-air sources and the gates."""
    return [n["id"] for n in plan["nodes"] if n["kind"] != "exit" and not n["source"]]


def first_danger(plan, d):
    hit = np.nonzero((d[:, watched(plan)] >= DANGER).any(1))[0]
    return None if len(hit) == 0 else int(hit[0])


def learned_gate_eff(plan, sched, truth, t, grid=(1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2)):
    """What the twin learns from the gate counters up to step t. It asks one question about the gate everyone
    uses: "what share of its design throughput makes my simulation match the people counted through it so far?"
    One number, fitted to data, inside the physics (the paper's residual idea). 1.0 = working as designed."""
    c = plan["candidates"][plan["main_entrance"]]
    e = next(i for i, ed in enumerate(plan["edges"]) if ed["candidate"] == c["id"])
    seen = np.abs(truth["flow"][:t, e]).sum()                  # people counted through the gate so far
    best, best_gap = 1.0, None
    for eff in grid:
        r = run(plan, sched, {} if eff == 1.0 else {c["id"]: eff}, None)
        gap = abs(np.abs(r["flow"][:t, e]).sum() - seen)
        if best_gap is None or gap < best_gap - max(2.0, 0.02 * seen):   # prefer "as designed" unless clearly worse
            best, best_gap = eff, gap
    return {c["id"]: best}


def apply_actions(plan, sched, chosen, at):
    """Turn a set of actions into simulator inputs, all starting at step `at`."""
    extra = dict(open_at={}, guide={}, arrivals=sched)
    for a in chosen:
        p = a["params"]
        if a["kind"] == "open_gate":
            extra["open_at"][p["gate"]] = at
        elif a["kind"] == "announce":                         # loudspeakers + boards: a share of people learn the other gates
            fam = {int(g): f for g, f in p["familiarity"].items()}
            for g in extra["open_at"]:
                fam.setdefault(g, 0.9)
            extra["guide"] = {s: (p["share"], fam) for s in range(at, at + 36, 6)}
        elif a["kind"] == "hold":                             # hold arrivals upstream: release them over a longer time
            new = {}
            for s, lst in sched.items():
                s2 = s if s < at else at + int((s - at) * p["stretch"]) + int(p.get("pause_min", 0) * 60 / DT)
                for item in lst:
                    new.setdefault(min(s2, STEPS - 60), []).append(item)
            extra["arrivals"] = new
    return extra


def analyse(plan, sched):
    hidden = {c["id"]: c["hidden_eff"] for c in plan["candidates"] if c["hidden_eff"] < 1}
    truth = run(plan, sched, hidden, None)
    d_today = density(plan, truth)
    t_danger = first_danger(plan, d_today)

    # the textbook twin: design throughput at every gate, no learning, no jam
    d_book = density(plan, run(plan, sched, {}, None))
    book_danger = first_danger(plan, d_book)

    # the learning twin: re-estimate the gates every 30 s, alarm at the first forecast of danger
    alarm, learned_at_alarm, forecast_danger = None, None, None
    for t in range(12, STEPS, FRAME):
        if t_danger is not None and t >= t_danger:
            break
        est = learned_gate_eff(plan, sched, truth, t)
        fd = first_danger(plan, density(plan, run(plan, sched, {c: e for c, e in est.items() if e < 0.95}, None)))
        if fd is not None:
            alarm, learned_at_alarm, forecast_danger = t, est, fd
            break
    if alarm is None:
        alarm = t_danger if t_danger is not None else 24
        learned_at_alarm = learned_gate_eff(plan, sched, truth, alarm)

    # try every combination of actions at the alarm; keep the one with the lowest peak density
    w = watched(plan)
    options = []
    for k in range(0, len(plan["actions"]) + 1):
        for combo in itertools.combinations(plan["actions"], k):
            r = run(plan, sched, hidden, None, apply_actions(plan, sched, combo, alarm))
            d = density(plan, r)
            options.append(dict(actions=[a["id"] for a in combo], peak=float(d[:, w].max()),
                                danger_person_min=float((r["people"][:, w] * (d[:len(r["people"]), w] >= DANGER)).sum() * DT / 60),
                                through=float(r["evacuated"][-1]), d=d, r=r))
    today = options[0]
    best = min(options, key=lambda o: (round(o["peak"], 2), len(o["actions"])))
    single = [o for o in options if len(o["actions"]) == 1]

    def frames(d, r):
        people = r["people"]
        if len(people) < STEPS:
            people = np.vstack([people, np.zeros((STEPS - len(people), people.shape[1]))])
        out = np.concatenate([r["evacuated"], np.full(STEPS - len(r["evacuated"]), r["evacuated"][-1])])
        return dict(density=np.round(d[::FRAME], 2).tolist(), people=np.round(people[::FRAME]).astype(int).tolist(),
                    through=np.round(out[::FRAME]).astype(int).tolist(),
                    worst=np.round(d[::FRAME][:, w].max(1), 2).tolist())

    mins = lambda s: None if s is None else round(s * DT / 60, 1)
    hidden_gate = next((c for c in plan["candidates"] if c["hidden_eff"] < 1), None)
    return dict(
        simulated=True, announcement=ANNOUNCE.get(plan["id"]), id=plan["id"], name=plan["name"], place=plan["place"], inspired_by=plan["inspired_by"], note=plan["note"],
        danger_density=DANGER, max_density=MAX_DENSITY, dt_s=DT, frame_s=FRAME * DT, minutes=STEPS * DT / 60,
        total_people=round(truth["total"]),
        zones=[dict(id=n["id"], name=n["name"], kind="gate" if n["kind"] == "exit" else ("source" if n["source"] else "zone"),
                    x=n["x"], y=n["y"], w=n["w_m"], h=n["h_m"], area_m2=n["area_m2"]) for n in plan["nodes"]],
        links=[dict(a=e["a"], b=e["b"], width_m=e["width_m"], gate=e["candidate"]) for e in plan["edges"]],
        gates=[dict(id=c["id"], name=c["name"], zone=c["node"], open_at_start=c["open"], known_to_crowd=c["familiarity"]) for c in plan["candidates"]],
        today=dict(danger_at_min=mins(t_danger), peak_density=round(today["peak"], 2), danger_person_min=round(today["danger_person_min"]),
                   worst_zone=plan["nodes"][w[int(np.argmax(today["d"][:, w].max(0)))]]["name"], **frames(today["d"], today["r"])),
        forecast=dict(alarm_at_min=mins(alarm), predicted_danger_at_min=mins(forecast_danger),
                      warning_min=None if t_danger is None else round((t_danger - alarm) * DT / 60, 1),
                      textbook_predicts_danger_at_min=mins(book_danger),
                      textbook_warning=("none: the textbook plan never predicts danger" if book_danger is None else
                                        f"predicts danger at {mins(book_danger)} min"),
                      hidden_problem=None if hidden_gate is None else dict(
                          gate=hidden_gate["name"], true_share_of_design_flow=hidden_gate["hidden_eff"],
                          learned_share=round(learned_at_alarm[hidden_gate["id"]], 2))),
        with_queuepilot=dict(actions=best["actions"], peak_density=round(best["peak"], 2), danger_person_min=round(best["danger_person_min"]),
                             stays_below_danger=bool(best["peak"] < DANGER), **frames(best["d"], best["r"])),
        actions=[dict(id=a["id"], label=a["label"], kind=a["kind"],
                      alone_peak_density=round(next(o["peak"] for o in single if o["actions"] == [a["id"]]), 2),
                      chosen=a["id"] in best["actions"]) for a in plan["actions"]])


# What the loudspeakers say when the control room approves the plan (English + Hindi).
ANNOUNCE = dict(
    stadium=dict(en="Gate 7 is now open. Gates 5 and 7 have no queue. Please do not wait at Gate 3.",
                 hi="गेट 7 अब खुला है। गेट 5 और 7 पर कोई कतार नहीं है। कृपया गेट 3 पर प्रतीक्षा न करें।"),
    temple=dict(en="Token counters 5 to 8 are now open in the side yard. Tokens are available for everyone. Please walk, do not run.",
                hi="साइड यार्ड में टोकन काउंटर 5 से 8 अब खुले हैं। टोकन सभी को मिलेंगे। कृपया चलें, दौड़ें नहीं।"),
    station=dict(en="A special train will leave from Platform 16. Passengers, please use the stairs to Platform 16.",
                 hi="एक विशेष ट्रेन प्लेटफ़ॉर्म 16 से रवाना होगी। यात्री कृपया प्लेटफ़ॉर्म 16 की सीढ़ियों का उपयोग करें।"),
    ghat=dict(en="The north and far bathing points are open and have space. Please follow the signs to the north ghat.",
              hi="उत्तरी और दूर के स्नान घाट खुले हैं और वहाँ जगह है। कृपया उत्तरी घाट के संकेतों का पालन करें।"))


# ------------------------------------------------------------------ the four venues (schematic, metres)
def venues():
    v = []
    v.append(venue(
        "stadium", "Stadium victory celebration", "City cricket stadium, free-entry celebration",
        dict(event="Bengaluru, M. Chinnaswamy Stadium", date="4 June 2025", toll="11 dead, 33 injured",
             what="Fans gathered at the gates for a victory celebration; the crush was at a gate."),
        zones=[("Metro exit", 900, 60, 300, 90, 70, 1), ("Main road", 700, 200, 300, 130, 60, 0), ("East road", 600, 370, 300, 130, 60, 0),
               ("Gate 3 plaza", 260, 200, 180, 90, 70, 0), ("Gate 5 plaza", 300, 370, 180, 90, 70, 0), ("Gate 7 plaza", 300, 520, 180, 90, 70, 0)],
        links=[("Metro exit", "Main road", 8, 40), ("Main road", "East road", 6, 50), ("Main road", "Gate 3 plaza", 8, 30),
               ("East road", "Gate 5 plaza", 6, 30), ("East road", "Gate 7 plaza", 6, 60), ("Gate 3 plaza", "Gate 5 plaza", 3, 50)],
        gates=[("Gate 3", "Gate 3 plaza", 5.0, 1.0, 0.4, 1), ("Gate 5", "Gate 5 plaza", 3.0, 0.2, 1.0, 1), ("Gate 7", "Gate 7 plaza", 3.0, 0.1, 1.0, 0)],
        arrivals=[("Metro exit", 5000, 0, 25)],
        actions=[("open", "Open Gate 7", "open_gate", dict(gate=2)),
                 ("announce", "Announce Gates 5 and 7 (loudspeakers, boards)", "announce", dict(share=0.5, familiarity={"1": 0.9})),
                 ("hold", "Hold metro arrivals: release over twice the time", "hold", dict(stretch=2.0))],
        note="Hidden problem: Gate 3, the gate everyone knows, is half shut."))
    v.append(venue(
        "temple", "Temple token counters", "Darshan token distribution centre",
        dict(event="Tirupati, token centres for Vaikunta Dwara Darshanam", date="8 January 2025", toll="6 dead",
             what="Devotees waiting for darshan tokens surged when a gate was opened."),
        zones=[("Waiting park", 1200, 70, 300, 110, 80, 1), ("Entry lane", 120, 220, 300, 110, 30, 0), ("Token hall", 220, 370, 300, 110, 80, 0),
               ("Side yard", 260, 370, 430, 110, 60, 0)],
        links=[("Waiting park", "Entry lane", 3, 30), ("Entry lane", "Token hall", 3, 30), ("Entry lane", "Side yard", 2.5, 40)],
        gates=[("Counters 1-4", "Token hall", 2.0, 1.0, 0.5, 1), ("Counters 5-8", "Side yard", 2.0, 0.15, 1.0, 0)],
        arrivals=[("Waiting park", 2500, 2, 12)],
        actions=[("open", "Open counters 5-8 in the side yard", "open_gate", dict(gate=1)),
                 ("announce", "Announce the side-yard counters", "announce", dict(share=0.5, familiarity={})),
                 ("hold", "Release the park in batches (three times slower)", "hold", dict(stretch=3.0))],
        note="Hidden problem: counters 1-4 hand out tokens at half the planned speed."))
    v.append(venue(
        "station", "Railway station, festival rush", "Major terminus, special-train night",
        dict(event="New Delhi Railway Station", date="15 February 2025", toll="18 dead",
             what="Crowds heading for festival trains surged on the stairs and platforms."),
        zones=[("Concourse", 1200, 70, 300, 110, 80, 1), ("Foot overbridge", 200, 230, 300, 120, 30, 0), ("Stairs 14", 70, 360, 230, 40, 50, 0),
               ("Platform 14", 420, 480, 230, 130, 50, 0), ("Stairs 16", 70, 360, 370, 40, 50, 0), ("Platform 16", 420, 480, 370, 130, 50, 0)],
        links=[("Concourse", "Foot overbridge", 5, 40), ("Foot overbridge", "Stairs 14", 4, 20), ("Stairs 14", "Platform 14", 4, 20),
               ("Foot overbridge", "Stairs 16", 4, 30), ("Stairs 16", "Platform 16", 4, 20)],
        gates=[("Train at 14", "Platform 14", 5.0, 1.0, 0.35, 1), ("Special at 16", "Platform 16", 5.0, 0.1, 1.0, 0)],
        arrivals=[("Concourse", 3200, 0, 20)],
        actions=[("open", "Run the special train from Platform 16", "open_gate", dict(gate=1)),
                 ("announce", "Announce Platform 16 before people reach the stairs", "announce", dict(share=0.5, familiarity={})),
                 ("hold", "Hold passengers in the concourse (release twice as slowly)", "hold", dict(stretch=2.0))],
        note="Hidden problem: boarding at Platform 14 is far slower than planned (train late, doors crowded)."))
    v.append(venue(
        "ghat", "Riverbank bathing day", "Festival ghats on the main bathing day",
        dict(event="Prayagraj, Maha Kumbh, Mauni Amavasya", date="29 January 2025", toll="at least 30 dead, about 60 injured",
             what="A pre-dawn surge toward the main bathing point broke through barricades."),
        zones=[("Approach road", 2500, 70, 300, 110, 90, 1), ("Barricade lane", 600, 230, 300, 120, 40, 0), ("Main ghat", 400, 390, 220, 110, 70, 0),
               ("North ghat", 600, 390, 380, 110, 70, 0), ("Far ghat", 700, 540, 380, 110, 70, 0)],
        links=[("Approach road", "Barricade lane", 12, 50), ("Barricade lane", "Main ghat", 10, 40), ("Barricade lane", "North ghat", 6, 120),
               ("North ghat", "Far ghat", 5, 60)],
        gates=[("Main bathing point", "Main ghat", 8.0, 1.0, 0.35, 1), ("North bathing point", "North ghat", 6.0, 0.05, 1.0, 1), ("Far bathing point", "Far ghat", 6.0, 0.05, 1.0, 0)],
        arrivals=[("Approach road", 9000, 0, 30)],
        actions=[("open", "Open the far bathing point", "open_gate", dict(gate=2)),
                 ("announce", "Announce the north and far ghats", "announce", dict(share=0.5, familiarity={"1": 0.9})),
                 ("hold", "Hold pilgrims on the approach road (release twice as slowly)", "hold", dict(stretch=2.0))],
        note="Hidden problem: people leave the main bathing point far slower than planned (they stay longer)."))
    return v


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for plan, sched in venues():
        a = analyse(plan, sched)
        (OUT / f"{plan['id']}.json").write_text(json.dumps(a))
        index.append(dict(id=a["id"], name=a["name"], place=a["place"], inspired_by=a["inspired_by"], file=f"{a['id']}.json",
                          total_people=a["total_people"], warning_min=a["forecast"]["warning_min"],
                          peak_today=a["today"]["peak_density"], peak_with=a["with_queuepilot"]["peak_density"]))
        f = a["forecast"]
        print(f"{a['id']:8s} people {a['total_people']:6d} | today: danger at {a['today']['danger_at_min']} min, peak {a['today']['peak_density']} /m2 in {a['today']['worst_zone']}, "
              f"{a['today']['danger_person_min']} person-min | alarm {f['alarm_at_min']} min -> warning {f['warning_min']} min | textbook: {f['textbook_warning']} | "
              f"learned {f['hidden_problem']} | QP {a['with_queuepilot']['actions']} peak {a['with_queuepilot']['peak_density']} safe={a['with_queuepilot']['stays_below_danger']} | "
              f"alone: {[(x['id'], x['alone_peak_density']) for x in a['actions']]}", flush=True)
    (OUT / "index.json").write_text(json.dumps(index, indent=1))


if __name__ == "__main__":
    main()


def picture():
    """data/crowd/preview.png: the worst zone's density over time, today vs with QueuePilot, for all four venues."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    SURFACE, INK, INK2, MUTED, GRID, BLUE, ORANGE, RED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e6e5e0", "#2a78d6", "#eb6834", "#d03b3b"
    idx = json.loads((OUT / "index.json").read_text())
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.6), facecolor=SURFACE, sharey=True)
    fig.subplots_adjust(left=0.05, right=0.985, top=0.74, bottom=0.14, wspace=0.08)
    fig.text(0.05, 0.93, "The alarm comes minutes before the crush, and the plan keeps the crowd below the danger line", fontsize=15, color=INK, fontweight="bold")
    fig.text(0.05, 0.865, "Density in the most crowded zone of each venue. Simulated crowds on schematic layouts inspired by real incidents.", fontsize=9.5, color=INK2)
    for ax, v in zip(axes, idx):
        a = json.loads((OUT / v["file"]).read_text())
        t = [i * a["frame_s"] / 60 for i in range(len(a["today"]["worst"]))]
        ax.set_facecolor(SURFACE)
        ax.axhspan(a["danger_density"], a["max_density"], color=RED, alpha=0.08, lw=0)
        ax.axhline(a["danger_density"], color=RED, lw=1)
        ax.plot(t, a["today"]["worst"], color=ORANGE, lw=2, label="No intervention")
        ax.plot(t, a["with_queuepilot"]["worst"], color=BLUE, lw=2, label="With QueuePilot")
        al = a["forecast"]["alarm_at_min"]
        ax.axvline(al, color=INK, lw=1, ls=(0, (3, 3)))
        ax.text(al + 0.5, 5.55, f"alarm\n{a['forecast']['warning_min']:.0f} min early", fontsize=8.5, color=INK, va="top")
        ax.set_title(a["name"], loc="left", fontsize=10.5, color=INK, fontweight="bold")
        ax.set_xlim(0, 40); ax.set_ylim(0, 6.2); ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(GRID)
        ax.tick_params(colors=MUTED, labelsize=9, length=0); ax.set_xlabel("minutes", color=INK2, fontsize=9.5)
    axes[0].set_ylabel("people per m²", color=INK2, fontsize=9.5)
    axes[0].text(39.5, 4.08, "danger", color=RED, fontsize=8.5, ha="right")
    axes[0].legend(frameon=False, fontsize=9, labelcolor=INK2, loc="lower right")
    fig.savefig(OUT / "preview.png", dpi=120, facecolor=SURFACE)
    print("wrote data/crowd/preview.png")

