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
def make_people(n=150, avg_gap=1.6, seed=42):
    """Random arrivals. avg_gap = average minutes between two people arriving."""
    rng = random.Random(seed)
    people, t = [], 0.0
    for i in range(n):
        t += rng.expovariate(1 / avg_gap)          # random gap between arrivals
        service = rng.choices(list(SERVICES), weights=[5, 3, 2])[0]
        duration = rng.uniform(0.5, 1.5) * SERVICES[service]   # actual time varies
        people.append({"id": i, "arrive": t, "service": service, "duration": duration})
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
def simulate(people, strategy):
    counters = [{**c, "free_at": 0.0, "free_at_est": 0.0, "ends": [], "busy": 0.0}
                for c in COUNTERS]
    waits = []
    for p in people:
        capable = [c for c in counters if p["service"] in c["can_do"]]
        c = strategy(capable, p)

        start = max(p["arrive"], c["free_at"])   # wait until counter is free
        end = start + p["duration"]
        waits.append(start - p["arrive"])

        c["free_at"] = end
        # system only KNOWS the average time, not the real one
        c["free_at_est"] = max(p["arrive"], c["free_at_est"]) + SERVICES[p["service"]]
        c["ends"].append(end)
        c["busy"] += p["duration"]

    total_time = max(c["free_at"] for c in counters)
    return {
        "avg_wait": sum(waits) / len(waits),
        "max_wait": max(waits),
        "utilisation": {c["name"]: round(100 * c["busy"] / total_time) for c in counters},
    }


# ---------- 5. COMPARE ----------
if __name__ == "__main__":
    people = make_people()
    for name, strat in [("Shortest line", pick_shortest_line), ("QueuePilot", pick_queuepilot)]:
        r = simulate(people, strat)
        print(f"{name:14} avg wait {r['avg_wait']:5.1f} min | "
              f"max wait {r['max_wait']:5.1f} min | utilisation % {r['utilisation']}")
