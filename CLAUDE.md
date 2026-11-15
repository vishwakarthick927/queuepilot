# QueuePilot — shared context for every Claude session

READ THIS FIRST. This file is the single source of truth shared between two machines.
To explain the research paper (plain words, section by section, how we use it, real-data proof): docs/PAPER.md.
Then read docs/BRIDGE.md (protocol + MESSAGES between machines) and docs/TASKS.md (who is doing what).
Before starting any task: `git pull`. After finishing any working feature: update the STATUS section below, commit, `git pull --rebase`, `git push`.

## CURRENT PLAN (15 Nov)
Hero = **QueuePilot Design**: an AI design service that tells architects where to put fire exits (fewer exits, same safety, panic included), built on a **PG-GNN** (physics-guided graph neural network). **Read docs/BUILD.md before any work: it is the plan of record** (model, data, screen, tasks M1–M5 / W1–W4, contract, checkpoints). Start prompts for both machines: docs/PROMPTS.md. Constraints: docs/CONSTRAINTS.md. docs/CROWD.md = story, facts, Q&A. Everything below is still true and stays as proof / fallback.

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
- Learned residual: what physics misses (people abandoning long lines). Features [q, q²/10] only (abandonment-shaped). Ridge regression; swappable for an MLP. Do NOT call it deep learning.
- Physics constraint on the learned part: residual clipped to [−q, 0], it can only remove people who are waiting (paper §3A: unconstrained residuals get too flexible).
- Tested under distribution shift (staffing never seen in training): 60-min forecast error, physics 4.3, pure data 10.6, hybrid 1.8 people.
- Control test, no abandonment at all: physics 3.8, hybrid 4.3 (learned part stays nearly harmless), pure data 69.
- Decision layer: staffing plan per 30-min block via Little's law (W = queue / throughput) to keep wait ≤ 5 min.
- Same staff-hours, time-varying plan vs even: avg queue 4.8 → 3.4, peak 23.6 → 15.9. HONEST: most of this gain is from time-varying staffing, not the forecast itself (REVIEW #3). Erlang-C guarantee is the planned fix (PLAN #4).

Three layers, one story: FORECAST (hybrid) → PLAN (staffing) → ROUTE (allocation).

## How it works
- Services have average durations (id_card ~1 min, fee_query ~6, certificate ~20); actual time varies ±50%.
- Counters have capabilities (C1, C2 do all; C3 id+fee; C4 id only).
- Baseline "FCFS / shortest line": join counter with fewest people.
- QueuePilot route-on-arrival: among capable counters, pick lowest (estimated free time + SKILL_COST × extra skills). Uses only ESTIMATED durations.
- QueuePilot pooled (best): one virtual queue; when a counter frees it takes the waiting person with max score = wait·AGING + priority bonus − skill mismatch. Pooling beats separate lines (M/M/c vs c×M/M/1).
- Simulation: start = max(arrival, counter free_at); wait = start − arrival. Compare avg wait, max wait, utilisation, averaged over many seeds.
- Presets: "normal" = stable load (n 300, gap 2.5 min), the demo default. "stress" = 125% certificate load (n 150, gap 1.6), shown separately as overload.
- Results, normal preset, 100 crowds, mean ± 95% CI: shortest line 7.1 ± 0.9, route-on-arrival 5.6 ± 0.8 (wins 97% of crowds), pooled 5.0 ± 0.8 (−30%, wins 100%). Per service, certificates 25.0 → 17.7 min.
- C2 closed 60–150: 10.0 → 7.4. 10% priority: priority people 7.3 → 2.3 min.
- Stress preset: 16.5 → 14.6 (pooled wins 94%). Do not quote stress numbers as the headline.

## Flagship use case: EV fast-charging hubs (docs/USE_CASE_EV.md, engine/ev.py)
Service time set by battery physics: dSOC/dt = P/E, CC-CV taper above 80% SOC, shared 150 kW site cap over 4×60 kW stalls.
QueuePilot-EV: water-filling power split + dynamic 80% cap while cars wait (never below trip need) + pooled queue.
80 busy days: avg wait 47.7 → 11.9 min (−75%), time at hub 113 → 66 min, trip need met 100%. Ablation: water-filling alone −37%.
GET /ev?runs=80&temp=1.0&avg_gap=18 → {"config": {...}, "charge_curve": [{"soc":0.0,"kw":60.0}, ...],
 "results": {"baseline"|"waterfill_only"|"cap_only"|"queuepilot": {"served","avg_wait","max_wait","avg_time_in_system","energy_kwh","need_met","avg_final_soc","avg_wait_ci95"}, "labels": {...}}}

## Multi-sector engine: perishable queues (docs/SECTORS.md, engine/perishable.py)
Pitch: one engine, any queue where the waiting item physically changes. Sector = physics module (state law, ₹ value, service time).
Policy: serve max (₹ lost if it waits one more slot) / service minutes = cμ rule with physics-computed loss rates; worthless jobs last.
40 days each, loss/day FCFS → QP: asphalt (15 °C) ₹14.5L → ₹3.7L (−74%), concrete ₹7.1L → ₹2.2L (−69%), milk (38 °C) ₹1.11L → ₹0.55L (−51%), sugarcane (38 °C) −11% (smooth decay; real lever is harvest scheduling).
GET /sectors?runs=40&temp=30 → {sugarcane|asphalt|milk|concrete: {"sector","unit","physics","money","servers","temp_c",
 "fcfs": {"jobs","value_rs","lost_rs","rejected","avg_wait"}, "queuepilot": {...}, "loss_cut_pct","saved_rs_per_day","win_rate"}}

## Real-data validation of the paper's method (engine/realdata.py, data/README.md)
Dataset: Technion SEE "Anonymous Bank" call centre (real arrivals, queue, service, HANG = abandonment). Physics = conservation of callers; learned residual = hang-ups, clipped [−q, 0]; vs pure data (ridge) and naive persistence.
Tests (busy periods, q ≥ 3, 60-min horizon, train early days → test later days): queue MAE; hang-ups in next hour; learned hang-up rate vs rate measured from logs (interpretability).
Self-test on synthetic data in the same format (python -m engine.realdata --selftest): hang-up error hybrid 9.4 vs naive 12.3 vs physics 17.8; learned rate 0.055–0.068 vs true 0.077. Queue MAE: data 2.7, hybrid 3.7, naive 4.6, physics 11.3 (pure data wins on queue length here; be honest).
REAL RESULTS (data/anonymous_bank_results.json, 183 train → 123 test days, 3,906 busy starts):
- HEADLINE: learned hang-up rate 0.143–0.153/min vs 0.156/min measured from logs (residual recovered real patience).
- Queue MAE 60 min: physics 6.19, hybrid 3.09, naive 3.17, data 2.73. Hang-ups next hour abs err: physics 27.1, hybrid 21.6, naive 14.0. Pure data/naive win those metrics; say so.

## Repo layout & ownership
| Path | Owner | Notes |
|---|---|---|
| engine/ | Main machine (Viswajit, Linux/Claude cloud) | Pure Python logic. No web code. |
| api/ | Main machine | FastAPI. `uvicorn api.main:app --reload` from repo root |
| frontend/ | Windows machine (teammate) | React dashboard |
| docs/CONSTRAINTS.md | Teammate 3 / anyone | Log every constraint verbatim |
| data/ | WIN downloads, MAIN analyses | Real datasets, see data/README.md. data/design/ = MAIN-owned plan graphs + design.json |
| research/ | Windows machine | PyTorch models (R1, flood, golden, design/ PG-GNN). research/design may call engine.design_data / engine.evac (read-only use). |
| docs/BRIDGE.md, docs/TASKS.md | Shared | Append only; protocol in BRIDGE.md |
Only edit folders you own. Need a change elsewhere? Write it under REQUESTS below and push.

## JSON contract (do not change field names without updating this file)
POST /simulate  body: {"preset": "normal", "runs": 100, "closures": {"C2": [[60, 150]]}, "priority_share": 0.1}   # all optional; preset "normal"|"stress"; n_people overrides preset
Optional "trace": true → each strategy also gets "timeline": [{"t":0,"waiting":3,"queues":{"C1":1,...},"serving":{"C1":true,...}}, ...] every 5 min, one crowd (seed 0).
Response: three strategies + labels. With priority_share > 0 each also has "avg_wait_priority", "avg_wait_normal".
{"fcfs":       {"avg_wait": 16.5, "max_wait": 119.9, "p95_wait": 84.2, "jain_fairness": 0.27, "utilisation": {...}},
 "queuepilot": {"avg_wait": 15.0, "max_wait": 103.0, "p95_wait": 68.5, "jain_fairness": 0.31, "utilisation": {...}},
 "pooled":     {"avg_wait": 14.6, "max_wait": 92.7,  "p95_wait": 66.7, "jain_fairness": 0.32, "utilisation": {...}},
 "labels": {"fcfs": "Shortest line (what people do today)", "queuepilot": "QueuePilot route-on-arrival", "pooled": "QueuePilot pooled virtual queue (late binding)"}}
Times in minutes, utilisation in %. NUMBERS ABOVE ARE OLD (stress load); see "How it works" for normal-preset results.
New per-strategy keys: "wait_by_service" {id_card, fee_query, certificate}, "avg_wait_ci95" (mean ± this), "win_rate_vs_fcfs" (share of crowds beaten). Top-level "preset": {name, n_people, avg_gap}.
For pooled the per-counter "queues" in timeline are 0 (nobody is bound to a counter); use "waiting".

GET /forecast → {"forecast_error": {"physics": 4.32, "data": 10.59, "hybrid": 3.01},
 "example": {"minutes": [...60], "actual": [...], "physics": [...], "data": [...], "hybrid": [...]},
 "staffing_plan": [3,4,7,7,5,3,3,3,3,4,6,6,4,4,3,3],   # servers per 30-min block, 8-hour day
 "staffing_comparison": {"fixed": {"avg_queue": 4.8, "peak_queue": 23.6, "avg_wait_min": 4.9, "staff_minutes": 2040},
                         "planned": {"avg_queue": 3.4, "peak_queue": 15.9, "avg_wait_min": 3.4, "staff_minutes": 2040}}}
 forecast_error is now {"physics": 4.32, "data": 10.59, "hybrid": 1.8}

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
- 15 Nov 10:35 [WIN] — ACK BUILD.md. Claimed W1–W4. research/crowd dropped. Starting W3 page skeleton (stub) + W1 pggnn.py scaffold.
- 15 Nov 10:20 [MAIN] — Judges' constraints 1+2 → new plan of record docs/BUILD.md: QueuePilot Design (exit placement for architects) on a PG-GNN. Tasks M1–M5 (MAIN: plan generator, detailed evacuation simulator, dataset, design search, verify) and W1–W4 (WIN: PG-GNN, recommend, Design Studio page). C1–C6 / W-C1–W-C5 superseded. Start prompts in docs/PROMPTS.md. Nothing built yet; waiting for the user to start both machines.
- 15 Nov 09:30 [WIN] — ACK Crowd Twin (MAIN = captain, its plan is final). Claimed W-C1..W-C4. Starting W-C1 (research/crowd/) against contract v0.
- 15 Nov 09:00 [MAIN] — FINAL PLAN per user: CROWD TWIN is the hero (docs/CROWD.md = plan of record: pitch, MVP screen, numbers, tasks C1–C4 / W-C1–W-C4, contract v0, checkpoints, Q&A). Planning only, nothing built yet. Flood / Golden Hour / sectors = fallback + backup slide. BRIDGE protocol rules 7–11 added.
- 14 Nov 22:50 [MAIN] — Synced: docs/PAPER.md (paper summary + mapping incl. Golden Hour and Flood + real bank results). realdata glob restricted to *.txt/*.csv/*.tsv (WIN request). Current hero per user: Flood disaster twin (WIN); Golden Hour + sectors = proof of generality.
- 14 Nov 21:50 [MAIN] — E15: real-data validation pipeline engine/realdata.py for Anonymous Bank (needs download, MAIN sandbox has no internet). Self-test passes.
- 14 Nov 21:20 [MAIN] — E14: multi-sector perishable engine (sugarcane, asphalt, milk, concrete), GET /sectors, docs/SECTORS.md with business case. Main pitch not chosen yet; all sectors are backups/proof of generality. 12 tests pass.
- 14 Nov 20:40 [MAIN] — E13: EV charging hub use case (battery-physics queue), engine/ev.py, GET /ev, docs/USE_CASE_EV.md. Wait −75%. 11 tests pass.
- 14 Nov 20:15 [MAIN] — E11+E12 (REVIEW #1,#2,#4,#5): constrained residual, hybrid 1.8 vs physics 4.3; stable "normal" preset default; pooled 7.1→5.0 min (−30%, wins 100% of crowds); CI, win rate, per-service waits in /simulate. 9 tests pass.
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
