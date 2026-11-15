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
| D1 | DOWNLOAD Anonymous Bank → data/anonymous_bank/, run python -m engine.realdata, commit output as data/anonymous_bank_results.json | WIN | Done |
| D2 | DOWNLOAD Open-Meteo hourly Bengaluru temps → data/weather/bengaluru_hourly.csv | WIN | Todo |
| D3 | Find + download a public EV charging sessions dataset → data/ev_sessions/ (note source + licence) | WIN | Todo |
| W-FLOOD | Flood disaster twin: physics-guided CNN flood forecast + evacuation + shelter queues (research/flood/, frontend/src/flood/) | WIN | Done |
| E16 | docs/PAPER.md: paper explained + how we use it + real results | MAIN | Done |
| P1 | PPT for judges | MAIN | Todo (after constraints) |
| C* | Constraints from organisers: log in docs/CONSTRAINTS.md, add a task row each | whoever is free | — |
| — | **CROWD TWIN sprint (docs/CROWD.md is the plan of record, 15 Nov)** | — | — |
| C1 | data/crowd/venue.json: single source of truth for the venue (grid, gates, zones, graph, 3 scenarios, hidden blocked gate). Push first. | MAIN | Todo (waiting for user go) |
| C2 | engine/crowd.py: max-flow / min-cut choke-point finder on the venue graph | MAIN | Todo |
| C3 | Action ranking with effect preview (open gate / hold arrivals / slot entry via pooled queue) | MAIN | Todo |
| C4 | Incident log + GET /crowd/* + tests + export data/crowd/plan.json (page works with no backend) | MAIN | Todo |
| W-C1 | research/crowd/: port flood water.py to crowd density on venue.json; physics / AI only / ours; export weights + twin JSON | WIN | Claimed 15 Nov 09:30 |
| W-C2 | research/crowd/evaluate.py: results JSON with every number in CROWD.md "Numbers we show" | WIN | Claimed 15 Nov 09:30 |
| W-C3 | frontend/src/crowd/: control-room page per CROWD.md layout, new default route (flood → /?view=flood) | WIN | Claimed 15 Nov 09:30 |
| W-C4 | Broadcast (speech, 3 languages, recorded fallback) + incident log view | WIN | Claimed 15 Nov 09:30 |
| V1 | docs/FACTS.md: verify every fact in CROWD.md "Why it matters" with source links | Member 3 | Todo |
| C5 | CONSTRAINT 1 (docs/CONSTRAINTS.md): exit-design optimiser in engine/crowd.py. Input: floor graph + candidate exit positions + fire scenarios. Output: fewest exits whose clearance time ≤ safe limit in every scenario incl. loss of any one exit; min-cut says "widen this door" vs "add an exit". Export data/crowd/design.json | MAIN | Todo (waiting for user go) |
| W-C5 | CONSTRAINT 1 view: "Design" tab: floor plan, candidate exits, slider "number of exits" vs clearance time curve, chosen layout vs rule-of-thumb layout, space freed | WIN | In progress (claimed 10:35) |
| C6 | Panic + exit familiarity model (softmax exit choice, herding, compliance, density-dependent door throughput); design search (C5) scored under panic, not ideal behaviour; export exit_share | MAIN | Todo (waiting for user go) |
| — | **QueuePilot Design sprint (docs/BUILD.md is the plan of record, 15 Nov 10:20). C1–C6 and W-C1–W-C5 above are SUPERSEDED.** | — | — |
| M1 | engine/plans.py: floor-plan generator → graph; data/design/demo_plan.json. Push first, post keys. | MAIN | Todo |
| M2 | engine/evac.py: detailed evacuation simulator (panic, familiarity, herding, door jam, fire closes edges) + tests | MAIN | Todo |
| M3 | python -m engine.design_data → train.npz (gitignored) + sample.npz + plans.json | MAIN | Todo |
| M4 | engine/design.py: truth ranking of layouts, rule-of-thumb layout, max-flow bound, min-cut, code-minimum check → data/design/design.json (+ animation frames) | MAIN | Todo |
| M5 | verify entry point: re-check given layouts in the detailed simulator | MAIN | Todo |
| W1 | research/design/pggnn.py: physics / GNN only / PG-GNN, train, test on unseen plans → results.json | WIN | In progress (claimed 10:35) |
| W2 | research/design/recommend.py: screen all layouts with PG-GNN, candidate value scores, verify top 5 via M5 → recommend.json | WIN | In progress (claimed 10:35) |
| W3 | frontend/src/design/: Design Studio page (new default route) | WIN | In progress (claimed 10:35) |
| W4 | Side-by-side evacuation animation, model drawer, polish | WIN | In progress (claimed 10:35) |

