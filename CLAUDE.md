# QueuePilot — shared context for every Claude session

READ THIS FIRST. This file is the single source of truth shared between two machines.
Then read docs/BRIDGE.md (protocol + MESSAGES between machines) and docs/TASKS.md (who is doing what).
Before starting any task: `git pull`. After finishing any working feature: update the STATUS section below, commit, `git pull --rebase`, `git push`.

## Event
ZeroHour hackathon, Shunya, PES University, 14–15 Nov 2026. Team "Counter Intelligence". Track 3: Optimization, Graph Theory & Intelligent Systems.
Rounds: Day 1 development + mentor reviews (cut), Day 2 final coding + evaluation. Constraints are revealed progressively during the event.
Rule: all work must be the team's original work — members must understand and be able to explain/modify every line live.
Judged on: technical implementation, feasibility, creativity, efficiency & optimization, problem-solving, presentation.

## The idea (one sentence)
QueuePilot is a physics-guided brain for any service system: it forecasts how queues will grow, decides how many servers to open, and sends each arrival to the server where they'll be served fastest.

General, not niche: works for admin counters, hospital OPDs, bank branches, EV chargers, call centres, even cloud servers. Anything with arrivals, servers and waiting.

## Research basis
Yu & Wang, "Learning dynamical systems from data: An introduction to physics-guided deep learning", PNAS 2024 (doi:10.1073/pnas.2311808121).
Their point: physics-only models are rigid; pure deep learning needs lots of data and breaks physical laws. Hybrid = physics structure + learned residual.
Our use (engine/physics.py):
- Physics: conservation law of the queue, dq/dt = arrivals − μ·servers, q ≥ 0 (fluid queue ODE).
- Learned residual: what physics misses (people abandoning long lines). Ridge regression now; swappable for a small neural net.
- Physics constraint on the learned part: the residual can never remove more people than are waiting.
- Tested under distribution shift (staffing never seen in training): 60-min forecast error, physics 4.3, pure data 10.6, hybrid 3.0 people.
- Decision layer: staffing plan per 30-min block via Little's law (W = queue / throughput) to keep wait ≤ 5 min.
- Same staff-hours, spent by the forecast instead of evenly: avg queue 6.2 → 5.3 (−15%), peak queue 25 → 18 (−27%).

Three layers, one story: FORECAST (hybrid) → PLAN (staffing) → ROUTE (allocation).

## How it works
- Services have average durations (id_card ~1 min, fee_query ~6, certificate ~20); actual time varies ±50%.
- Counters have capabilities (C1, C2 do all; C3 id+fee; C4 id only).
- Baseline "FCFS / shortest line": join counter with fewest people.
- QueuePilot route-on-arrival: among capable counters, pick lowest (estimated free time + SKILL_COST × extra skills). Uses only ESTIMATED durations.
- QueuePilot pooled (best): one virtual queue; when a counter frees it takes the waiting person with max score = wait·AGING + priority bonus − skill mismatch. Pooling beats separate lines (M/M/c vs c×M/M/1).
- Simulation: start = max(arrival, counter free_at); wait = start − arrival. Compare avg wait, max wait, utilisation, averaged over many seeds.
- Result so far: QueuePilot ~10–17% lower average wait.

## Repo layout & ownership
| Path | Owner | Notes |
|---|---|---|
| engine/ | Main machine (Viswajit, Linux/Claude cloud) | Pure Python logic. No web code. |
| api/ | Main machine | FastAPI. `uvicorn api.main:app --reload` from repo root |
| frontend/ | Windows machine (teammate) | React dashboard |
| docs/CONSTRAINTS.md | Teammate 3 / anyone | Log every constraint verbatim |
| docs/BRIDGE.md, docs/TASKS.md | Shared | Append only; protocol in BRIDGE.md |
Only edit folders you own. Need a change elsewhere? Write it under REQUESTS below and push.

## JSON contract (do not change field names without updating this file)
POST /simulate  body: {"n_people": 150, "runs": 100, "closures": {"C2": [[60, 150]]}, "priority_share": 0.1}   # closures, priority_share optional
Optional "trace": true → each strategy also gets "timeline": [{"t":0,"waiting":3,"queues":{"C1":1,...},"serving":{"C1":true,...}}, ...] every 5 min, one crowd (seed 0).
Response: three strategies + labels. With priority_share > 0 each also has "avg_wait_priority", "avg_wait_normal".
{"fcfs":       {"avg_wait": 16.5, "max_wait": 119.9, "p95_wait": 84.2, "jain_fairness": 0.27, "utilisation": {...}},
 "queuepilot": {"avg_wait": 15.0, "max_wait": 103.0, "p95_wait": 68.5, "jain_fairness": 0.31, "utilisation": {...}},
 "pooled":     {"avg_wait": 14.6, "max_wait": 92.7,  "p95_wait": 66.7, "jain_fairness": 0.32, "utilisation": {...}},
 "labels": {"fcfs": "Shortest line (what people do today)", "queuepilot": "QueuePilot route-on-arrival", "pooled": "QueuePilot pooled virtual queue (late binding)"}}
Times in minutes, utilisation in %. (100-run averages, n_people 150.)
For pooled the per-counter "queues" in timeline are 0 (nobody is bound to a counter); use "waiting".

GET /forecast → {"forecast_error": {"physics": 4.32, "data": 10.59, "hybrid": 3.01},
 "example": {"minutes": [...60], "actual": [...], "physics": [...], "data": [...], "hybrid": [...]},
 "staffing_plan": [2,4,7,7,4,2,2,2,3,4,5,5,4,3,2,2],   # servers per 30-min block, 8-hour day
 "staffing_comparison": {"fixed": {"avg_queue": 6.2, "peak_queue": 25.0, "avg_wait_min": 6.3, "staff_minutes": 1740},
                         "planned": {"avg_queue": 5.3, "peak_queue": 18.3, "avg_wait_min": 5.4, "staff_minutes": 1740}}}

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
- 14 Nov 19:15 [WIN] — F5–F7 done: 3 strategies + p95 + Jain, priority slider + callout, staffing_comparison, 04 Replay (side-by-side animation + scrubber from timeline), URL scenarios (?close=C2&priority=10&t=22), per-panel error boundary. Build + lint clean, checked at 1440 and 500 px.
- 14 Nov 18:25 [MAIN] — E8–E10 done (WIN proposals 1,4,5): pooled late-binding strategy, p95 + Jain fairness, trace timeline. Pooled vs shortest line: avg 16.5→14.6, max 120→93, p95 84→67.
- 14 Nov 17:30 [WIN] — F1–F4 done: frontend/ React+Vite+TS+Tailwind dashboard (Forecast, Plan, Route with live closure toggles + sliders). Run: cd frontend && npm i && npm run dev. Falls back to saved real API responses if backend is down.
- 14 Nov 17:30 [MAIN] — Added tests: `python -m tests.test_engine` (5 checks, all pass). Run after every constraint change.
- 14 Nov 17:20 [MAIN] — Priority users: /simulate priority_share. 10% priority, 100 runs: priority wait 17.9 → 3.2 min, normal people unchanged (16.4).
- 14 Nov 17:05 [MAIN] — E4 done: /forecast adds staffing_comparison. Same staff-hours, forecast-planned vs even: peak queue −27%, avg −15%.
- 14 Nov 16:55 [MAIN] — E5 done: /simulate accepts `closures`. 100-run avg wait: normal FCFS 16.5 vs QP 15.0; C2 closed 60–150 min: FCFS 23.5 vs QP 21.6.
- 14 Nov 16:45 [MAIN] — Added physics-guided hybrid forecaster + /forecast, BRIDGE.md and TASKS.md. WIN: start F1–F4.
- 14 Nov 13:15 — Repo created: engine simulation + /simulate API scaffold. Frontend not started.

## REQUESTS (cross-machine asks)
- (none)

## Session rules for Claude
- Fresh chat per task; start by reading this file. Keep answers short.
- Don't rewrite files outside your folder. Don't change the JSON contract silently.
- Explain any non-trivial code so the team can defend it to judges.
