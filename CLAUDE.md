# QueuePilot — shared context for every Claude session

READ THIS FIRST. This file is the single source of truth shared between two machines.
Before starting any task: `git pull`. After finishing any working feature: update the STATUS section below, commit, `git pull --rebase`, `git push`.

## Event
ZeroHour hackathon, Shunya, PES University, 14–15 Nov 2026. Team "Counter Intelligence". Track 3: Optimization, Graph Theory & Intelligent Systems.
Rounds: Day 1 development + mentor reviews (cut), Day 2 final coding + evaluation. Constraints are revealed progressively during the event.
Rule: all work must be the team's original work — members must understand and be able to explain/modify every line live.
Judged on: technical implementation, feasibility, creativity, efficiency & optimization, problem-solving, presentation.

## The idea (one sentence)
We send each person to the counter where they'll be served fastest, not the one that looks shortest, and prove it with a simulation.

## How it works
- Services have average durations (id_card ~1 min, fee_query ~6, certificate ~20); actual time varies ±50%.
- Counters have capabilities (C1, C2 do all; C3 id+fee; C4 id only).
- Baseline "FCFS / shortest line": join counter with fewest people.
- QueuePilot: among capable counters, pick lowest (estimated free time + SKILL_COST × extra skills). Uses only ESTIMATED durations.
- Simulation: start = max(arrival, counter free_at); wait = start − arrival. Compare avg wait, max wait, utilisation, averaged over many seeds.
- Result so far: QueuePilot ~10–17% lower average wait.

## Repo layout & ownership
| Path | Owner | Notes |
|---|---|---|
| engine/ | Main machine (Viswajit, Linux/Claude cloud) | Pure Python logic. No web code. |
| api/ | Main machine | FastAPI. `uvicorn api.main:app --reload` from repo root |
| frontend/ | Windows machine (teammate) | React dashboard |
| docs/CONSTRAINTS.md | Teammate 3 / anyone | Log every constraint verbatim |
Only edit folders you own. Need a change elsewhere? Write it under REQUESTS below and push.

## JSON contract (do not change field names without updating this file)
POST /simulate  body: {"n_people": 150, "runs": 100}
Response:
{"fcfs": {"avg_wait": 12.9, "max_wait": 123, "utilisation": {"C1": 94, "C2": 93, "C3": 47, "C4": 10}},
 "queuepilot": {"avg_wait": 10.7, "max_wait": 113, "utilisation": {"C1": 87, "C2": 91, "C3": 55, "C4": 17}}}
Times in minutes, utilisation in %.

## Constraint cheat sheet
- New service/counter → SERVICES / COUNTERS in engine/simulation.py
- Priority users → add priority to people, subtract bonus in pick_queuepilot
- Counter closes/break → skip it in `capable` during time window
- Different counter speeds → duration / speed
- People leave if wait too long → count as lost
- Fairness cap → boost anyone near the max-wait limit
- Real-time → new API endpoint, one person per request
For each constraint: what changed? which part? simplest fix? how do we show it works? Keep FCFS vs QueuePilot comparison working always.

## STATUS (update this — newest first, one line each)
- 14 Nov 13:15 — Repo created: engine simulation + /simulate API scaffold. Frontend not started.

## REQUESTS (cross-machine asks)
- (none)

## Session rules for Claude
- Fresh chat per task; start by reading this file. Keep answers short.
- Don't rewrite files outside your folder. Don't change the JSON contract silently.
- Explain any non-trivial code so the team can defend it to judges.
