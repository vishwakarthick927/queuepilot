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


if __name__ == "__main__":
    import warnings; warnings.filterwarnings("ignore")
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
