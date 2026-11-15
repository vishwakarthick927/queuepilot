"""
A static picture of the design result, drawn straight from data/design/demo_plan.json and design.json
(no numbers typed by hand). For a quick look without running the web page.

Run from repo root:  python -m engine.preview      (writes data/design/preview.png)
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyBboxPatch, Rectangle

OUT = Path(__file__).parent.parent / "data" / "design"
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e6e5e0"
OURS, RULE, CRITICAL = "#2a78d6", "#eb6834", "#d03b3b"
DENSITY = LinearSegmentedColormap.from_list("people", ["#eef4fc", "#cde2fb", "#86b6ef", "#3987e5", "#184f95", "#0d366b"])
SNAP_S = 120


def draw_plan(ax, plan, frame, title, colour):
    step = min(int(SNAP_S / plan["dt_s"]) - 1, len(frame["people"]) - 1)
    people = frame["people"][step] if frame["people"] else [0] * len(plan["nodes"])
    built, lost = set(frame["exits"]), frame["lost_exit"]
    exit_of = {c["node"]: c for c in plan["candidates"]}
    for e in plan["edges"]:                                         # doors and passages
        a, b = plan["nodes"][e["a"]], plan["nodes"][e["b"]]
        if e["candidate"] is None or e["candidate"] in built:
            ax.plot([a["x"], b["x"]], [a["y"], b["y"]], color=GRID, lw=3, zorder=1, solid_capstyle="round")
    for n in plan["nodes"]:
        s = n["w_m"]
        if n["kind"] == "exit":
            c = exit_of[n["id"]]
            if c["id"] in built:
                blocked = c["id"] == lost
                ax.add_patch(Rectangle((n["x"] - 1.6, n["y"] - 1.6), 3.2, 3.2, fc=SURFACE, ec=CRITICAL if blocked else INK, lw=2, zorder=3))
                ax.text(n["x"], n["y"], "x" if blocked else n["name"][-1], ha="center", va="center", fontsize=9,
                        color=CRITICAL if blocked else INK, fontweight="bold", zorder=4)
            else:
                ax.add_patch(Rectangle((n["x"] - 0.9, n["y"] - 0.9), 1.8, 1.8, fc=SURFACE, ec=MUTED, lw=0.8, ls=(0, (2, 2)), zorder=3))
            continue
        full = people[n["id"]] / (n["area_m2"] * plan["max_density"])  # share of the space's capacity in use
        if n["kind"] == "room":
            full = people[n["id"]] / max(n["people0"], 1)              # rooms: share of their people still inside
        ax.add_patch(FancyBboxPatch((n["x"] - s / 2, n["y"] - s / 2), s, s, boxstyle="round,pad=0,rounding_size=0.5",
                                    fc=DENSITY(min(1.0, full)), ec=SURFACE, lw=1.5, zorder=2))
        if people[n["id"]] >= 5:
            ax.text(n["x"], n["y"], f"{people[n['id']]:.0f}", ha="center", va="center", fontsize=7.5,
                    color=SURFACE if full > 0.45 else INK2, zorder=4)
    inside = sum(people)
    cleared = f"cleared in {frame['clearance_s']:.0f} s" if frame["clearance_s"] else "not cleared in 600 s"
    ax.set_title(title, loc="left", fontsize=12, color=INK, fontweight="bold", pad=22)
    ax.text(0, 1.02, f"{inside:.0f} people still inside at {SNAP_S // 60}:00   |   {cleared}", transform=ax.transAxes,
            fontsize=10, color=colour, fontweight="bold")
    ax.set_aspect("equal"); ax.autoscale_view(); ax.margins(0.04); ax.invert_yaxis(); ax.axis("off")


def style(ax, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9.5); ax.set_ylabel(ylabel, color=INK2, fontsize=9.5)


def main():
    plan = json.loads((OUT / "demo_plan.json").read_text())
    d = json.loads((OUT / "design.json").read_text())
    ours, rule = d["frames"]["chosen"], d["frames"]["rule_of_thumb"]
    main_case = d["by_panic"][str(d["design_panic"])]
    total = sum(n["people0"] for n in plan["nodes"])
    limit = d["safe_limit_s"]

    fig = plt.figure(figsize=(14, 9.2), facecolor=SURFACE)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.25, 1], hspace=0.38, wspace=0.16, left=0.05, right=0.97, top=0.86, bottom=0.07)
    fig.text(0.05, 0.95, f"Same floor, same {len(ours['exits'])} exits to spend: where they go decides who gets out",
             fontsize=16, color=INK, fontweight="bold")
    fig.text(0.05, 0.915, f"{plan['name']}, {total} people. Scenario: {ours['scenario']} (the front door), panic {ours['panic']}. "
             f"Simulated. Tiles show people still in each space; x = blocked exit; dashed squares = exit positions not built.",
             fontsize=9.5, color=INK2)
    draw_plan(fig.add_subplot(gs[0, 0]), plan, rule, "Exits spread evenly (rule of thumb)", RULE)
    draw_plan(fig.add_subplot(gs[0, 1]), plan, ours, "Exits placed by QueuePilot", OURS)

    ax = fig.add_subplot(gs[1, 0]); style(ax, "seconds after the alarm", "people still inside")
    for fr, colour, name in ((rule, RULE, "Rule of thumb"), (ours, OURS, "QueuePilot")):
        t = [(i + 1) * plan["dt_s"] for i in range(len(fr["evacuated"]))]
        left = [total - x for x in fr["evacuated"]]
        ax.plot(t, left, color=colour, lw=2, label=name)
        ax.text(t[-1] + 3, left[-1] + 6, name, color=INK2, fontsize=9, va="bottom")
    ax.axvline(limit, color=MUTED, lw=1, ls=(0, (4, 3))); ax.text(limit - 3, total * 0.93, f"safe limit {limit:.0f} s", color=INK2, fontsize=9, ha="right")
    ax.set_xlim(0, max(len(rule["evacuated"]), len(ours["evacuated"])) * plan["dt_s"] + 30); ax.set_ylim(0, total * 1.02)
    ax.set_title("People still inside over time", loc="left", fontsize=11, color=INK, fontweight="bold")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper right")

    ax = fig.add_subplot(gs[1, 1]); style(ax, "number of exits built", "worst-case clearance (s)")
    curve = [c for c in main_case["curve"] if c["ours_s"] and c["rule_s"]]
    k = [c["n_exits"] for c in curve]
    ax.plot(k, [c["rule_s"] for c in curve], color=RULE, lw=2, marker="o", ms=7, mec=SURFACE, mew=2, label="Rule of thumb")
    ax.plot(k, [c["ours_s"] for c in curve], color=OURS, lw=2, marker="o", ms=7, mec=SURFACE, mew=2, label="QueuePilot (best layout)")
    ax.axhline(limit, color=MUTED, lw=1, ls=(0, (4, 3))); ax.text(k[-1], limit + 3, f"safe limit {limit:.0f} s", color=INK2, fontsize=9, ha="right")
    ax.set_xticks(k)
    ax.set_title(f"Worst case over every fire scenario: passes with {main_case['chosen_n_exits']} exits, "
                 f"rule of thumb needs {main_case['rule_n_exits']}", loc="left", fontsize=11, color=INK, fontweight="bold")
    ax.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper right")
    fig.savefig(OUT / "preview.png", dpi=130, facecolor=SURFACE)
    print("wrote", OUT / "preview.png")


if __name__ == "__main__":
    main()
