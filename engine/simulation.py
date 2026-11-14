"""
QueuePilot - core simulation (plain Python, no libraries needed)

Idea: same crowd of people goes through two systems.
  1. "Shortest line" - person joins the counter with the FEWEST PEOPLE (what humans do)
  2. "QueuePilot"   - person goes to the counter that will be FREE SOONEST,
                       based on total service time already queued there
Then we compare waiting times.
"""
import random

# ---------- 1. SETUP: services and counters ----------
# service name -> average time in minutes
SERVICES = {
    "id_card":     1,
    "fee_query":   6,
    "certificate": 20,
}

# each counter: which services it can handle
COUNTERS = [
    {"name": "C1", "can_do": ["id_card", "fee_query", "certificate"]},
    {"name": "C2", "can_do": ["id_card", "fee_query", "certificate"]},
    {"name": "C3", "can_do": ["id_card", "fee_query"]},
    {"name": "C4", "can_do": ["id_card"]},
]


# ---------- 2. GENERATE FAKE PEOPLE ----------
def make_people(n=150, avg_gap=1.6, seed=42, priority_share=0.0):
    """Random arrivals. avg_gap = average minutes between two people arriving.
    priority_share = fraction of people who are priority (elderly, emergency)."""
    prio_rng = random.Random(seed + 10_000)  # separate stream: same crowd with or without priority
    rng = random.Random(seed)
    people, t = [], 0.0
    for i in range(n):
        t += rng.expovariate(1 / avg_gap)          # random gap between arrivals
        service = rng.choices(list(SERVICES), weights=[5, 3, 2])[0]
        duration = rng.uniform(0.5, 1.5) * SERVICES[service]   # actual time varies
        people.append({"id": i, "arrive": t, "service": service, "duration": duration,
                       "priority": prio_rng.random() < priority_share})
    return people


# ---------- 3. THE TWO STRATEGIES ----------
def people_in_line(counter, t):
    """How many people are still waiting/being served at this counter at time t."""
    return sum(1 for end in counter["ends"] if end > t)

def pick_shortest_line(capable, person):
    # Normal human behaviour: fewest heads.
    return min(capable, key=lambda c: people_in_line(c, person["arrive"]))

def pick_queuepilot(capable, person):
    # Smart, two ideas:
    #  (a) look at TIME, not heads: when will this counter actually be free?
    #  (b) don't waste flexible counters: a quick ID-card job should go to the
    #      ID-only counter if possible, saving C1/C2 for long certificate jobs.
    #      So each extra skill a counter has adds a small "cost" of using it.
    SKILL_COST = 3  # minutes; tune this and watch the results change
    return min(capable, key=lambda c: c["free_at_est"] + SKILL_COST * (len(c["can_do"]) - 1))


# ---------- 4. RUN ONE SIMULATION ----------
def _skip_closed(t, name, closures):
    """If time t falls inside a closure window of this counter, jump to its reopening."""
    for a, b in closures.get(name, []):
        if a <= t < b:
            return b
    return t


def _schedule_from(c, i, closures):
    """Re-time jobs i.. of a counter back-to-back after a priority insertion."""
    prev_end = c["jobs"][i - 1]["end"] if i > 0 else 0.0
    for j in c["jobs"][i:]:
        j["start"] = _skip_closed(max(j["p"]["arrive"], prev_end), c["name"], closures)
        j["end"] = prev_end = j["start"] + j["p"]["duration"]


def simulate(people, strategy, closures=None, use_priority=False):
    """closures: {"C2": [(60, 120)]} -> C2 is closed from minute 60 to 120.
    People already in its line must wait; QueuePilot knows and routes around it,
    people choosing by line length do not.
    use_priority: priority people go to the front of their counter's line
    (after the person currently being served)."""
    closures = closures or {}
    counters = [{**c, "free_at_est": 0.0, "jobs": [], "busy": 0.0} for c in COUNTERS]
    for p in people:
        capable = [c for c in counters if p["service"] in c["can_do"]]
        for x in capable:  # estimates include known closures
            x["free_at_est"] = _skip_closed(max(p["arrive"], x["free_at_est"]), x["name"], closures)
            x["ends"] = [j["end"] for j in x["jobs"]]  # for line-length counting
        c = strategy(capable, p)

        jobs = c["jobs"]
        if use_priority and p.get("priority"):
            # front of the line: before everyone who hasn't started yet
            i = next((k for k, j in enumerate(jobs) if j["start"] > p["arrive"]), len(jobs))
        else:
            i = len(jobs)
        jobs.insert(i, {"p": p, "start": 0.0, "end": 0.0})
        _schedule_from(c, i, closures)

        # system only KNOWS the average time, not the real one
        c["free_at_est"] = c["free_at_est"] + SERVICES[p["service"]]
        c["busy"] += p["duration"]

    all_jobs = [j for c in counters for j in c["jobs"]]
    waits = [j["start"] - j["p"]["arrive"] for j in all_jobs]
    prio = [w for w, j in zip(waits, all_jobs) if j["p"].get("priority")]
    norm = [w for w, j in zip(waits, all_jobs) if not j["p"].get("priority")]
    total_time = max(j["end"] for j in all_jobs)
    out = {
        "avg_wait": sum(waits) / len(waits),
        "max_wait": max(waits),
        "utilisation": {c["name"]: round(100 * c["busy"] / total_time) for c in counters},
    }
    if prio:
        out["avg_wait_priority"] = sum(prio) / len(prio)
        out["avg_wait_normal"] = sum(norm) / len(norm)
    return out


# ---------- 5. COMPARE ----------
if __name__ == "__main__":
    people = make_people()
    for name, strat in [("Shortest line", pick_shortest_line), ("QueuePilot", pick_queuepilot)]:
        r = simulate(people, strat)
        print(f"{name:14} avg wait {r['avg_wait']:5.1f} min | "
              f"max wait {r['max_wait']:5.1f} min | utilisation % {r['utilisation']}")
