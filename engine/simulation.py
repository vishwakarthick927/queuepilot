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
PRESETS = {
    # stable: offered load fits capacity (certificates ~80% of C1+C2), so waits settle
    "normal": {"n": 300, "avg_gap": 2.5},
    # stress: 125% load on certificates, the system is overloaded and waits keep growing
    "stress": {"n": 150, "avg_gap": 1.6},
}


def make_people(n=300, avg_gap=2.5, seed=42, priority_share=0.0):
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

    records = [{**j, "counter": c["name"]} for c in counters for j in c["jobs"]]
    return _metrics(records, counters)


# ---------- 4b. LATE BINDING: one pooled virtual queue ----------
AGING = 1.0           # each minute waited adds 1 point
SKILL_COST = 3       # minutes; same penalty QueuePilot uses for flexible counters
PRIORITY_BONUS = 30   # a priority person counts as if they had waited 30 min more


def simulate_pooled(people, closures=None, use_priority=False):
    """Everyone joins ONE virtual queue (digital token). Nobody is bound to a counter.
    When a counter frees up it asks "who next for me?" and takes the waiting person with
    the highest score:  wait_so_far*AGING + priority bonus - skill mismatch.
    Pooling is a classic queueing result: one shared queue for c servers beats c
    separate queues (M/M/c vs c x M/M/1), and no one is stuck in "the wrong line"."""
    closures = closures or {}
    counters = [{**c, "free_at": 0.0, "busy": 0.0} for c in COUNTERS]
    min_skills = {sv: min(len(c["can_do"]) for c in COUNTERS if sv in c["can_do"]) for sv in SERVICES}
    waiting, i, records = [], 0, []
    while i < len(people) or waiting:
        for c in counters:
            c["free_at"] = _skip_closed(c["free_at"], c["name"], closures)
        # specialists choose first on ties, so quick jobs don't clog flexible counters
        c = min(counters, key=lambda c: (c["free_at"], len(c["can_do"])))
        t = c["free_at"]
        while i < len(people) and people[i]["arrive"] <= t:
            waiting.append(people[i]); i += 1
        cand = [p for p in waiting if p["service"] in c["can_do"]]
        if not cand:  # idle until the next arrival
            c["free_at"] = people[i]["arrive"] if i < len(people) else float("inf")
            if all(x["free_at"] == float("inf") for x in counters):
                break
            continue

        def score(p):
            mismatch = SKILL_COST * (len(c["can_do"]) - min_skills[p["service"]])
            bonus = PRIORITY_BONUS if use_priority and p.get("priority") else 0
            return (t - p["arrive"]) * AGING + bonus - mismatch
        p = max(cand, key=score)
        waiting.remove(p)
        c["free_at"] = t + p["duration"]
        c["busy"] += p["duration"]
        records.append({"p": p, "start": t, "end": t + p["duration"], "counter": c["name"]})
    return _metrics(records, counters)


# ---------- 4c. METRICS (shared) ----------
def _metrics(records, counters):
    waits = [r["start"] - r["p"]["arrive"] for r in records]
    total_time = max(r["end"] for r in records)
    sw = sorted(waits)
    out = {
        "avg_wait": sum(waits) / len(waits),
        "max_wait": max(waits),
        "p95_wait": sw[int(0.95 * (len(sw) - 1))],
        # Jain's fairness index on waits (+1 min so zero waits don't divide by zero):
        # 1.0 = everyone waited equally, lower = some people wait much longer than others
        "jain_fairness": (sum(w + 1 for w in waits) ** 2) / (len(waits) * sum((w + 1) ** 2 for w in waits)),
        "utilisation": {c["name"]: round(100 * c["busy"] / total_time) for c in counters},
        "wait_by_service": {sv: (sum(w for w, r in zip(waits, records) if r["p"]["service"] == sv) /
                                 max(1, sum(1 for r in records if r["p"]["service"] == sv)))
                            for sv in SERVICES},
        "_records": records,
    }
    prio = [w for w, r in zip(waits, records) if r["p"].get("priority")]
    if prio:
        norm = [w for w, r in zip(waits, records) if not r["p"].get("priority")]
        out["avg_wait_priority"] = sum(prio) / len(prio)
        out["avg_wait_normal"] = sum(norm) / len(norm)
    return out


def timeline(result, step=5):
    """People waiting (arrived, not yet started) every `step` minutes, total and per counter."""
    recs = result["_records"]
    end = max(r["end"] for r in recs)
    names = [c["name"] for c in COUNTERS]
    out = []
    for t in range(0, int(end) + step, step):
        w = [r for r in recs if r["p"]["arrive"] <= t < r["start"]]
        serving = {n: any(r["counter"] == n and r["start"] <= t < r["end"] for r in recs) for n in names}
        out.append({"t": t, "waiting": len(w),
                    "queues": {n: sum(1 for r in w if r["counter"] == n) for n in names},
                    "serving": serving})
    return out


# ---------- 5. COMPARE ----------
if __name__ == "__main__":
    people = make_people()
    for name, strat in [("Shortest line", pick_shortest_line), ("QueuePilot", pick_queuepilot)]:
        r = simulate(people, strat)
        print(f"{name:14} avg wait {r['avg_wait']:5.1f} min | "
              f"max wait {r['max_wait']:5.1f} min | utilisation % {r['utilisation']}")
