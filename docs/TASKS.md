# TASKS — claim before you start (Owner + status), push the claim immediately

| ID | Task | Owner | Status |
|---|---|---|---|
| E1 | Allocation simulation, FCFS vs QueuePilot | MAIN | Done |
| E2 | Physics-guided hybrid forecaster (engine/physics.py) | MAIN | Done |
| E3 | /simulate and /forecast endpoints | MAIN | Done |
| E4 | Forecast-guided staffing vs fixed staffing (same staff-hours) | MAIN | Done |
| E5 | Scenario endpoint: counter closes at minute X, show recovery | MAIN | Done |
| F1 | React + Vite dashboard skeleton, 3 panels | WIN | Done |
| F2 | Panel "Allocation": bar chart avg/max wait FCFS vs QueuePilot + utilisation | WIN | Done |
| F3 | Panel "Forecast": line chart actual vs physics vs data vs hybrid, plus error numbers | WIN | Done |
| F4 | Panel "Staffing plan": servers per 30-min block from /forecast | WIN | Done |
| E6 | Priority users (priority_share), served first by QueuePilot | MAIN | Done |
| E7 | tests/test_engine.py sanity checks (run after every change) | MAIN | Done |
| E8 | Late binding: one pooled virtual queue, score = aging + priority − skill mismatch (WIN proposal 1) | MAIN | Done |
| E9 | Fairness metrics p95 + Jain index (WIN proposal 4) | MAIN | Done |
| E10 | trace timeline for animation (WIN proposal 5) | MAIN | Done |
| F5 | Route panel v2: 3 strategies (labels), p95 + Jain, priority slider + callout | WIN | Done |
| F6 | Plan panel v2: staffing_comparison (same staff-minutes, peak 25→18), drop 57% claim | WIN | Done |
| F7 | Live replay: side-by-side animation from trace timeline, shortest line vs pooled | WIN | Done |
| R1 | research/: physics-guided DEEP model (PyTorch) + sector embedding, few-shot new sector, MC uncertainty, stability bound = our research-gap contribution (standalone MVP) | WIN | In progress |
| E11 | Fix residual: features [q, q²/10], clip [−q, 0]; no-abandon test (REVIEW #2) | MAIN | Done |
| E12 | Stable baseline (gap 2.5, n 300) + stress preset; mean ± 95% CI, win rate, per-service waits (REVIEW #1,#4,#5) | MAIN | Done |
| E13 | EV charging hub: battery-physics queue, water-filling + dynamic cap (judges asked for a complex physics use case) | MAIN | Done |
| F8 | EV panel: charge curve, 4-policy ablation bars, temp slider (calls GET /ev) | WIN | Todo |
| E14 | Multi-sector perishable engine + /sectors + docs/SECTORS.md | MAIN | Done |
| F9 | Sectors panel: card per sector (physics law, ₹ lost FCFS vs QP, rejected loads), temperature slider, one 'All sectors' summary | WIN | Todo |
| E15 | Real-data validation pipeline (Anonymous Bank), self-test | MAIN | Done |
| D1 | DOWNLOAD Anonymous Bank → data/anonymous_bank/, run python -m engine.realdata, commit output as data/anonymous_bank_results.json | WIN | Todo, URGENT |
| D2 | DOWNLOAD Open-Meteo hourly Bengaluru temps → data/weather/bengaluru_hourly.csv | WIN | Todo |
| D3 | Find + download a public EV charging sessions dataset → data/ev_sessions/ (note source + licence) | WIN | Todo |
| W-FLOOD | Flood disaster twin: physics-guided CNN flood forecast + evacuation + shelter queues (research/flood/, frontend/src/flood/) | WIN | In progress |
| P1 | PPT for judges | MAIN | Todo (after constraints) |
| C* | Constraints from organisers: log in docs/CONSTRAINTS.md, add a task row each | whoever is free | — |
