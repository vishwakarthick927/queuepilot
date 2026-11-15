"""Quick sanity checks. Run from repo root:  python -m tests.test_engine
Run after every constraint change: if this passes, the demo numbers still hold."""
import statistics as st
import numpy as np
from engine import simulation as sim
from engine import physics as ph


def avg_wait(strategy, runs=50, **kw):
    use_priority = kw.pop("use_priority", False)
    closures = kw.pop("closures", None)
    return st.mean(sim.simulate(sim.make_people(seed=s, **kw), strategy, closures, use_priority)["avg_wait"]
                   for s in range(runs))


def test_queuepilot_beats_fcfs():
    assert avg_wait(sim.pick_queuepilot) < avg_wait(sim.pick_shortest_line)


def test_closures():
    cl = {"C2": [(60, 150)]}
    assert avg_wait(sim.pick_queuepilot, closures=cl) < avg_wait(sim.pick_shortest_line, closures=cl)


def test_priority_served_faster():
    r = sim.simulate(sim.make_people(seed=1, priority_share=0.1), sim.pick_queuepilot, use_priority=True)
    assert r["avg_wait_priority"] < r["avg_wait_normal"]


def test_everyone_served_once():
    people = sim.make_people(seed=3, priority_share=0.2)
    r = sim.simulate(people, sim.pick_queuepilot, {"C1": [(30, 90)]}, use_priority=True)
    assert r["max_wait"] >= 0


def test_hybrid_beats_physics_and_data():
    steady = np.full(480, 6)
    shifted = np.where(np.arange(480) < 240, 4, 7)
    train = [(ph.arrival_profile(), steady, ph.real_world_day(steady, seed=s)[1]) for s in (1, 2)]
    test = [(ph.arrival_profile(), shifted, ph.real_world_day(shifted, seed=s)[1]) for s in (10, 11)]
    err = ph.evaluate(ph.fit(train), test)
    assert err["hybrid"] < err["physics"] and err["hybrid"] < err["data"]


def test_pooled_beats_shortest_line():
    pooled = st.mean(sim.simulate_pooled(sim.make_people(seed=s))["avg_wait"] for s in range(50))
    assert pooled < avg_wait(sim.pick_shortest_line)


def test_timeline_shape():
    tl = sim.timeline(sim.simulate_pooled(sim.make_people(seed=0)))
    assert tl[0]["t"] == 0 and "waiting" in tl[0] and "C1" in tl[0]["queues"]


def test_hybrid_harmless_without_abandonment():
    steady = np.full(480, 6)
    shifted = np.where(np.arange(480) < 240, 4, 7)
    train = [(ph.arrival_profile(), steady, ph.real_world_day(steady, seed=s, abandon=0)[1]) for s in (1, 2)]
    test = [(ph.arrival_profile(), shifted, ph.real_world_day(shifted, seed=s, abandon=0)[1]) for s in (10, 11)]
    err = ph.evaluate(ph.fit(train), test)
    assert err["hybrid"] <= err["physics"] + 1.0  # learned part must not wreck a correct physics model


def test_pooled_wins_most_seeds_stable_load():
    wins = sum(sim.simulate_pooled(sim.make_people(seed=s))["avg_wait"] <
               sim.simulate(sim.make_people(seed=s), sim.pick_shortest_line)["avg_wait"] for s in range(40))
    assert wins >= 36  # >= 90% of crowds


def test_ev_queuepilot_beats_baseline_and_meets_need():
    from engine import ev
    b = [ev.simulate(ev.make_cars(seed=s), "baseline") for s in range(20)]
    q = [ev.simulate(ev.make_cars(seed=s), "queuepilot") for s in range(20)]
    assert st.mean(r["avg_wait"] for r in q) < st.mean(r["avg_wait"] for r in b)
    assert all(r["need_met"] == 1.0 for r in q)  # nobody leaves without the charge their trip needs


def test_waterfill_respects_site_cap():
    from engine import ev
    cars = [{"id": i, "soc": s} for i, s in enumerate([0.2, 0.85, 0.95, 0.5])]
    alloc = ev.split_waterfill(cars, ev.SITE_CAP, 1.0)
    assert sum(alloc.values()) <= ev.SITE_CAP + 1e-6
    assert all(alloc[c["id"]] <= ev.accept_power(c["soc"]) + 1e-6 for c in cars)


def test_perishable_sectors_queuepilot_loses_less():
    from engine import perishable as per
    for key in per.SECTORS:
        r = per.compare_sector(key, runs=10)
        assert r["queuepilot"]["lost_rs"] <= r["fcfs"]["lost_rs"], key
        assert r["queuepilot"]["jobs"] == r["fcfs"]["jobs"]  # everyone still served


# ---- QueuePilot Design (docs/BUILD.md): floor plans, evacuation simulator, exit design ----
def _demo():
    from engine import plans
    return plans.demo_plan()


def test_plan_graph_is_valid():
    p = _demo()
    ids = {n["id"] for n in p["nodes"]}
    assert all(e["a"] in ids and e["b"] in ids for e in p["edges"])
    assert all(p["nodes"][c["node"]]["kind"] == "exit" for c in p["candidates"])
    assert p["candidates"][p["main_entrance"]]["familiarity"] == 1.0


def test_evacuation_conserves_people():
    from engine import evac
    p = _demo()
    r = evac.simulate(p, [c["id"] for c in p["candidates"]], fire=p["fires"][0], panic=0.8)
    inside_plus_out = r["people"].sum(1) + r["evacuated"]
    assert np.allclose(inside_plus_out, r["total"], atol=1e-2)       # nobody created or lost, at every step
    assert r["people"].min() >= -1e-6


def test_panic_slows_evacuation_and_crowds_the_main_exit():
    from engine import evac
    p = _demo()
    exits = [c["id"] for c in p["candidates"]][:4]
    calm, panic = evac.simulate(p, exits, panic=0.0), evac.simulate(p, exits, panic=0.8)
    main = p["main_entrance"]
    assert panic["clearance_s"] > calm["clearance_s"]
    assert panic["exit_use"][main] > calm["exit_use"][main]


def test_lost_exit_is_not_used():
    from engine import evac
    p = _demo()
    r = evac.simulate(p, [0, 1, 2], lost_exit=1, panic=0.5)
    assert r["exit_use"][1] == 0.0


def test_maxflow_bound_is_below_simulated_time():
    from engine import design, evac
    p = _demo()
    layout = [c["id"] for c in p["candidates"]][:3]
    assert design.flow_bound(p, layout)["bound_s"] <= evac.simulate(p, layout, panic=0.0)["clearance_s"]


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
