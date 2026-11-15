# QueuePilot Live — stampede prevention. BUILD SPEC (MAIN, 15 Nov). Self-contained: a fresh session can build from this file alone.

This is a SECOND product next to QueuePilot Design (the fire-exit page, which stays running and untouched).
User deadline: about one hour. Build in parts, show each part, stop for feedback.

## What it is (one sentence)
**A control-room screen that warns minutes before a crowd crush and shows exactly what to do.**
Pitch line: "Every stampede starts as a queue that lost control."

## Separate dev server
- New Vite app in a new folder `live/` (React + TypeScript, same tooling as `frontend/`). Do NOT touch `frontend/` and do NOT stop its server.
- Run it on its own port: `npm run dev -- --host --port 5174`. Tell the user the Local and Network links.
- It reads only `data/crowd/index.json` and `data/crowd/<venue>.json` (import them or copy at build; no backend).

## The data (all SIMULATED, made by `python -m engine.crowd`, numpy only)
`data/crowd/index.json`: `[{id, name, place, inspired_by {event, date, toll, what}, file, total_people, warning_min, peak_today, peak_with}]`
`data/crowd/<id>.json`:
- `name, place, note, inspired_by, total_people, danger_density (4), max_density (6), frame_s (30), minutes (40)`
- `zones [{id, name, kind: "source"|"zone"|"gate", x, y, w, h, area_m2}]` (x, y = centre in schematic units; draw as rounded rectangles)
- `links [{a, b, width_m, gate}]` (gate = gate id for the short link from a zone to its gate, else null)
- `gates [{id, name, zone, open_at_start, known_to_crowd 0..1}]`
- `today {danger_at_min, peak_density, danger_person_min, worst_zone, density[frame][zone], people[frame][zone], through[frame], worst[frame]}`
- `with_queuepilot {actions [ids], peak_density, danger_person_min, stays_below_danger, density, people, through, worst}` (same frames)
- `forecast {alarm_at_min, predicted_danger_at_min, warning_min, textbook_warning, hidden_problem {gate, true_share_of_design_flow, learned_share}}`
- `actions [{id, label, kind, alone_peak_density, chosen}]`
- `announcement {en, hi}` (what the loudspeakers say)
81 frames per run, one every 30 s. Density is people per m². Gates have density 0; draw them as doors.

## The four use cases (real incidents they are inspired by; layouts are schematic, NOT reconstructions)
| id | Venue | Inspired by (verified facts) | Hidden problem | Today | Alarm | With QueuePilot |
|---|---|---|---|---|---|---|
| stadium | Stadium victory celebration, 5,000 people | Bengaluru, Chinnaswamy Stadium, 4 Jun 2025: 11 dead, 33 injured | Gate 3, the gate everyone knows, is half shut | danger at 12.1 min, peak 5.2 /m² at Gate 3 plaza | 7.0 min (5.1 min early) | peak 2.35 /m² |
| temple | Temple token counters, 2,500 | Tirupati token centres, 8 Jan 2025: 6 dead | Counters 1-4 run at half speed | danger at 13.1 min, peak 6.0 in Token hall | 4.5 min (8.6 min early) | peak 0.82 |
| station | Railway station, festival rush, 3,200 | New Delhi Railway Station, 15 Feb 2025: 18 dead | Boarding at Platform 14 far slower than planned | danger at 14.6 min, peak 4.6 on Platform 14 | 7.0 min (7.6 min early) | peak 0.90 |
| ghat | Riverbank bathing day, 9,000 | Prayagraj, Maha Kumbh, 29 Jan 2025: at least 30 dead | People leave the main bathing point slower than planned | danger at 13.3 min, peak 5.5 at Main ghat | 8.5 min (4.8 min early) | peak 3.9 |
In all four the textbook plan (gates working as designed) never predicts danger. Read every number from the files, never type them.
Write "inspired by" next to the incident name. Never say the simulation reproduces the real event.

## How it works (this is the research-paper part; keep it honest)
Paper: Yu & Wang, "Learning dynamical systems from data: an introduction to physics-guided deep learning", PNAS 2024.
- **Physics (hard-coded):** people are conserved; a gate passes only so many per second; a space holds only so many; people walk slower when it is dense (the same continuity / cell-transmission physics as QueuePilot Design).
- **Learned from data (the paper's residual idea, §3A):** the twin does not know a gate is failing. Every 30 s it fits ONE number per main gate, "what share of its design throughput matches the people counted through it so far", and re-runs the forecast. In the files: `forecast.hidden_problem.learned_share` vs `true_share_of_design_flow` (0.4 vs 0.4, 0.5 vs 0.5, 0.4 vs 0.35, 0.4 vs 0.35).
- **Decide:** at the alarm it simulates every combination of the venue's actions and picks the lowest peak density.
- Do NOT call this forecaster a neural network: it is physics with a learned parameter. The trained deep models (PG-GNN for people, PG-CNN for smoke) are in QueuePilot Design; training the PG-GNN on venue runs is the stated next step. One small line on the page says exactly this.

## The screen (one screen, 1440×900, no scrolling). Visual first, very little text.
1. **Top bar:** product name "QueuePilot Live", four venue tabs (Stadium · Temple · Station · Riverbank), a mode switch **Today | With QueuePilot | Side by side**.
2. **The venue map (hero, ~60% of the screen):** zones as rounded rectangles laid out from x, y, w, h; links as bands whose thickness follows width_m; gates as doors. Zone colour = density on ONE single-hue light-to-dark ramp, switching to a distinct alarm colour at and above the danger density. Each zone shows its name and, when it matters, people per m². People flowing is shown by the fill changing over time; add moving dots along links only if it is quick and smooth.
3. **Timeline scrubber** along the bottom of the map: play / pause, 0–40 min, with two markers: ALARM and DANGER. The gap between them is labelled "N minutes of warning": this is the hero number.
4. **Left rail, "Now":** a big Crowd Pressure Index for the worst zone (0–100 = density / max_density × 100, "the AQI for crowds"), the zone's name, and a **countdown to danger** that runs while playing in Today mode (danger_at_min − current time; after the alarm in QueuePilot mode it reads "Danger avoided").
5. **Right rail, "Do":** appears at the alarm. Up to three action cards (the venue's `actions`), each with one line and a tiny before → after density bar (today peak → `alone_peak_density`). The chosen ones are ticked. One button **Approve plan** switches the map to the With-QueuePilot frames. Under it, **Broadcast**: speaks `announcement.en` then `.hi` with the browser's speech synthesis, and shows the text.
6. **One result sentence** built from data: "Alarm 8.6 minutes before the crush. Peak crowd 6.0 → 0.8 people per m²."
7. **"What the twin learned"** as one small visual: a gate icon with two bars, "planned 100%" vs "learned 50%", and the label "found from gate counts, nobody reported it".
8. A quiet **"Inspired by"** line: event, date, toll (from `inspired_by`).
9. A quiet footer: "Simulated crowd on a schematic layout. A person approves every action. Counts only, no faces."
Optional drawer "How it works": three short blocks (physics we know / what the twin learns / how it decides) + the incident log (alarm time, actions approved, peak before/after) built from the same fields.

## Demo path (must work with one click or key each)
Pick a venue → Play in Today mode (crowd builds, countdown runs, zone turns to the alarm colour, "DANGER" stamp) → switch to With QueuePilot → Play (alarm fires early, cards appear) → Approve plan → crowd stays below the line → Broadcast → Side by side.

## Design rules (user was explicit)
Use the UI/UX Pro Max skill. No purple or violet. No Inter font (pick a distinctive, legible pairing, e.g. a grotesk for UI and a mono for numbers). No gradients, glow, glassmorphism, emoji, stock icons, card-in-card or filler copy. A calm control-room look: dark neutral surface, one accent, one alarm colour used only for danger. Tabular digits, real units. Minimal text; no tables of raw numbers on the main screen. It must look different from QueuePilot Design but clearly the same family.

## Order of work (show each part, then continue)
1. App skeleton on port 5174 + venue map drawn from data + venue tabs. Screenshot → docs/brief/live_1_map.png. Tell the user the link.
2. Playback: density over time, scrubber with ALARM and DANGER markers, Today / With QueuePilot / Side by side. Screenshot live_2_play.png.
3. Left rail (pressure index, countdown) + right rail (action cards, Approve plan, Broadcast) + result sentence. Screenshot live_3_control.png.
4. Polish pass + "How it works" drawer. Screenshot live_4_final.png. STOP for feedback.
After each part: commit `[WIN]`, push, one line in docs/BRIDGE.md MESSAGES. If your context is cleared, re-read this file and BRIDGE.md and continue from the last screenshot.
