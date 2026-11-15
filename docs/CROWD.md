> SCOPE SUPERSEDED 15 Nov 10:20 by docs/BUILD.md (judges' constraints: PG-GNN + exit design for architects). Story, facts list and Q&A below still apply; the control-room screen is a stretch goal.

# QueuePilot Crowd Twin — THE plan (v6, 15 Nov 09:00, MAIN, approved by the user)

This replaces docs/PLAN.md as the plan of record. Flood twin, Golden Hour, EV and sectors stay in the repo as fallback and one backup slide. Nothing here is built yet: this file is the spec both machines build from.

## Pitch
**"Every stampede starts as a queue that lost control. QueuePilot gives the control room 15 minutes of warning and tells them what to do with it."**
One problem (crowd crush), one user (the police / organiser control room for a large event), one hero number (**minutes of warning before danger density**).
How it is still QueuePilot: a crowd is a queue without structure; slots, gate metering and holding zones put the structure back.

## Why it matters (facts for the slide; Member 3 re-verifies every one, task V1)
- 4 Jun 2025, Chinnaswamy Stadium, Bengaluru: 11 dead, 33 injured (CM's statement via ANI / Scroll).
- 8 Jan 2025, Tirupati: 6 dead waiting for darshan tokens. A literal token queue.
- 2025: 129 dead in 8 major stampedes (NewsBytes tally). 2000–2022: 3,074 deaths (NCRB, via Vajiram & Ravi).
- To verify: danger density threshold (people/m²) and its source; NDMA crowd-management guidelines; status of Karnataka's post-Chinnaswamy crowd-control law ("why now" slide if passed); distance venue → PES.

## The method (same as the flood twin, people instead of water)
Per cell, every step: `people_next = people + arrivals − left + moved_in − moved_out` (conservation of people).
Movement slows as density rises (pedestrian speed–density curve; cite the source we use). Flow through a gate ≤ gate capacity × **efficiency**.
What the plan on paper does NOT know: a gate half shut, a barricade, a counter-flow. So the textbook model assumes efficiency = 1 and under-predicts the crush.
Three forecasters, as in research/flood/water.py: **physics** (efficiency = 1), **AI only** (CNN predicts density change), **ours** (physics + CNN-learned efficiency squeezed into [0, 1], trained through the rollout). The learned part can only slow a gate, never create or delete people.
Paper (Yu & Wang, PNAS 2024): §3A residual model with constraints (what we use); §4A tested on a venue never seen in training; §4C alarm on probability, not a single reading; §4E the learned term means something (it points at the blocked gate). Gaps we claim: the paper does not cover crowd/pedestrian dynamics, and treats control only as an example, not a learning task; we close the loop forecast → act → re-forecast.

## The MVP: one screen that works live (not a slideshow of numbers)
Page: new default "/" (flood moves to /?view=flood). Everything runs in the browser from exported JSON + weights, no backend needed on stage.

Layout (control-room screen, 1440 px first):
1. **Map (centre, ~60%)**: the venue, gates, approach roads, metro exit. Density as a heatmap in people/m². Choke-point edges outlined when found. Play / pause / scrub the timeline.
2. **Left rail, "Now"**: Crowd Pressure Index per zone (0–100, one colour scale), and the **Time-to-Danger countdown** for the worst gate ("Gate 3 → danger in 12:40").
3. **Right rail, "Do"**: up to 3 ranked action cards (open gate / hold arrivals / switch to slot entry). Each shows its predicted effect as a ghost line on the forecast chart. **Apply** re-runs the twin with that action. Nothing is applied without a click (human in the loop).
4. **Bottom strip**: forecast chart for the selected zone: actual, physics, AI only, ours, with the danger line.
5. **Top bar**: scenario tabs (Celebration surge | Token queue | Normal day), mode toggle (Today | With QueuePilot | Side by side), **Broadcast** button (speaks the announcement in Kannada / Hindi / English), incident log button.

Live moments, in demo order (3 min):
1. Play "Celebration surge", Today mode: Gate 3 goes past the danger line. No warning.
2. Same crowd, With QueuePilot: alarm fires N minutes earlier, countdown runs, choke points light up.
3. Click the top action card → ghost line → Apply → peak stays under the line. Side by side.
4. "The AI found the blocked gate": toggle the learned efficiency layer; the half-shut gate shows up, nobody told the model.
5. Broadcast: the room hears the announcement. Open the incident log: every alarm, action and approval, timestamped.
6. Normal day tab: zero alarms (it does not cry wolf).

## Numbers we show (every one read from a results JSON, never typed by hand; mean ± 95% CI over seeds)
| Number | Where it comes from |
|---|---|
| **Minutes of warning** before danger density (hero) | research/crowd evaluate, per scenario |
| Peak density at the worst gate, Today → With QueuePilot | same |
| People-minutes above danger density, Today → With QueuePilot | same |
| Danger cells caught / false alarms 15 min ahead: physics vs AI only vs ours, on unseen event days | research/crowd results |
| Same, on a **venue never seen in training** | research/crowd results |
| Learned gate efficiency vs true (error) | research/crowd results |
| False alarms on a normal day (target 0) | research/crowd evaluate |
| Real-data anchor: learned hang-up 0.143–0.153 vs measured 0.156 /min | data/anonymous_bank_results.json (exists) |
Every simulated number carries the word "simulated" on screen. If a number is weak, we show it and say why (as in PAPER.md).

## Look and feel (must read as a professional tool, not a template)
- One dark control-room theme, one accent, one sequential colour scale for density (same scale everywhere, with a legend in people/m²).
- Real units on every number; tabular digits; no emoji, no stock gradients, no decorative icons, no filler cards.
- The venue is drawn as a clean schematic (stands, gates numbered, roads named generically). Do not copy a real stadium's logo or branding.
- One screen, no scrolling at 1440×900. Checked at projector resolution. Text readable from 4 m.
- Loading, empty and error states exist (per-panel error boundary, as in the engine dashboard).
- A small "How it works" drawer: the conservation equation, the bounded learned term, the paper citation.

## Who builds what (parallel, no overlap)
| ID | Task | Owner | Unblocks |
|---|---|---|---|
| C1 | `data/crowd/venue.json` = the single source of truth for the venue (grid, walls, gates + capacity, zones, graph, 3 scenarios, one hidden blocked gate). Push FIRST. | MAIN | everyone |
| C2 | `engine/crowd.py`: max-flow / min-cut choke-point finder on the venue graph | MAIN | map overlay |
| C3 | Action ranking with effect preview (open gate / hold arrivals / slot entry); slot entry uses the pooled virtual queue | MAIN | action cards |
| C4 | Incident log format + `GET /crowd/*` endpoints + tests; export `data/crowd/plan.json` so the page needs no backend | MAIN | log, offline demo |
| W-C1 | `research/crowd/`: port flood water.py → crowd density on venue.json; 3 forecasters; export weights + twin JSON | WIN | everything visual |
| W-C2 | `research/crowd/evaluate.py` → results JSON with every number in the table above | WIN | slide numbers |
| W-C3 | `frontend/src/crowd/` page per the layout above, new default route | WIN | the demo |
| W-C4 | Broadcast (browser speech, pre-recorded fallback) + incident log view | WIN | demo moments 5 |
| V1 | Verify facts list above, with source links, into docs/FACTS.md | Member 3 | slides |
| P1 | Deck + rehearse docs/CROWD.md Q&A aloud | Member 3 + all | pitch |
WIN: these are proposed; claim them in TASKS.md or counter-propose in MESSAGES.

## Contract v0 (MAIN confirms exact keys when C1 is pushed; do not rename after that without a MESSAGE)
`data/crowd/venue.json`: `grid` {nx, ny, cell_m, dt_s}; `walls` [[x,y]]; `gates` [{id, name, cells [[x,y]], capacity_per_step, open}]; `zones` [{id, name, cells, area_m2}]; `nodes` [[x,y]]; `edges` [{a, b, capacity_per_step, gate_id|null}]; `danger_density`; `scenarios` [{id, name, arrivals [{step, node, people}], hidden {gate_id, efficiency}}].
`data/crowd/plan.json`: per scenario: `choke_points` [{step, edges [edge index], max_flow, demand}]; `actions` [{id, label, kind, params, rank, predicted_peak, minutes_gained}]; `log` [{t, type, text}].
WIN → MAIN (twin export, mirrors flood twin.json): `density` [step][y][x] for today / with QueuePilot; `forecast` per method; `efficiency_learned` per gate.

## Checkpoints (T0 = WIN's ack in MESSAGES; the user sets the hard cut-off time)
- T0 + 0:30 — C1 pushed (MAIN). WIN starts the port against it.
- T0 + 1:30 — WIN: physics-only crowd sim plays on the page (ugly is fine). MAIN: choke points in plan.json.
- T0 + 3:00 — learned model trained, three forecasters on screen, one action card applies.
- T0 + 4:00 — full demo order runs end to end. Feature freeze. Only fixes and polish after this.
- **Fallback rule:** if the T0 + 3:00 checkpoint is missed, flood twin is presented as the hero and the crowd page is shown as "next". Decide at that checkpoint, not later.
- Before the pitch: record a screen video of the full demo as a backup.

## Q&A we must not fumble
| Question | Answer |
|---|---|
| It's all simulated. Does it work? | Crowd results are simulated and labelled so. The method is checked on real data: a year of bank calls, learned 0.15 vs 0.156 measured. |
| Why physics-guided, not plain AI? | In our flood test plain AI raised false alarms on 85% of an unseen district, ours 3.7%. A control room ignores a system that cries wolf. (Quote the crowd numbers once they exist.) |
| What if the camera count is wrong? | Conservation of people: a count cannot jump without people entering. We alarm on probability, not one reading. |
| Dense crowds break person detectors. | Yes. Above a density, counting switches to density-map models; the twin only needs counts per zone, whatever produces them. Sensing is not in the MVP; say so. |
| Why not more police? | The need is warning time and knowing where pressure is building. |
| Is the AI in charge? | No. It recommends, a person approves, everything is logged. |
| Privacy? | Counts per zone only. No faces, nothing stored about a person. |
| How is this QueuePilot? | A crowd is a queue without structure; we put the structure back with slots, gate metering, holding zones. |
| Only crowds? | The same engine runs our hospital, flood and counter demos (one backup slide). |
| Who pays? | Police, temple boards, Railways, event organisers. Runs on existing CCTV. |
| What is original here? | The crowd twin, the bounded learned gate efficiency, and the forecast → min-cut → action loop. Every line is ours and we can change it live. |
