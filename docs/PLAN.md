# QueuePilot — the plan to win (v2, 14 Nov 19:30, WIN)
Built from: the original plan, a judge-style red team of the engine (docs/REVIEW.md), and a check of the paper's actual text.
MAIN decides engine order; this is a proposal. Rule: every claim on a slide must survive "show me".

## Pitch (one line)
**Queues are dynamical systems. QueuePilot is a physics-guided digital twin for multi-server service systems: it forecasts the queue, plans staff with a guarantee, and routes every arrival, then proves each step against a baseline.**
Domains: college office, hospital OPD, bank / call centre, EV charging. (Drop "cloud servers": invites the wrong expert questions.)

## The paper, used correctly (Yu & Wang, PNAS 2024, open access PMC11228478)
| Paper says | We do | Slide line |
|---|---|---|
| §3A residual model: F = g (physics) + r (learned) | fluid queue ODE + learned abandonment residual | "Physics gives the structure, data learns what physics misses." |
| §3A "without additional constraints … the learned DL model may become too flexible" | residual restricted to [−q, 0] (people can only leave), features [q, q²/10] | "Our learned part can't break conservation of people." |
| §4A residual models / UDEs extrapolate for low-dim time series | test on staffing never seen in training (+ no-abandonment control test) | "Generalises out of distribution; harmless when physics is already right." |
| §4 open challenge: uncertainty quantification | Erlang-C: P(W > t) = C(c,a)·e^(−(cμ−λ)t) | "We give a guarantee, not an average." |
| §4A distribution shift in system parameters | fit 3 numbers (λ scale, μ, patience θ) for a new site | "New site = refit 3 parameters, not retrain." |
Do NOT claim: Koopman, DyAd/LEADS, equivariance, "deep learning" (it's ridge; say "swappable for an MLP").
Quote for slide: "Physics-guided DL … has the best of both worlds." (Abstract)

## Graph theory (Track 3), used correctly
- **Skill graph max-flow** = stability + capacity check: source→service (cap = offered Erlangs) →counter (∞ if capable) →sink (cap 1 each). If max-flow < demand the system is overloaded, and the min cut names the services that cause it. Gives **cross-training advice**: "let C3 also do certificates → feasible". Visual: bipartite graph with edge flows, cut edges in red.
- Routing when a counter frees = argmax of one score (aging + priority − skill mismatch). Say "greedy matching on the skill graph"; no Hungarian needed.
- Not min-cut on a hospital tandem line (trivial: slowest station).

## Build order (≈10 h, two machines)
| # | What | Who | Why judges care |
|---|---|---|---|
| 1 | Fix residual (constrained) + no-abandon test + seed sweep with 95% CI | MAIN | honest, defensible headline |
| 2 | Re-baseline demo to stable load; keep 125% as "stress" preset; report mean ± CI, win rate, per-class wait | MAIN | gains become real + significant |
| 3 | Skill-graph max-flow + cross-training what-if (`/capacity`) | MAIN → WIN graph view | Track 3 fit, visual |
| 4 | Erlang-C chance-constrained staffing P(W>10)<5%, vs flat and naive plans | MAIN → WIN band chart | the "guarantee" |
| 5 | Domain presets (office / hospital / bank / EV) as config; `domain` param | MAIN → WIN switcher | "not niche", proved |
| 6 | MPC re-plan every 15 min + 3-param new-site fit | MAIN → WIN | "autopilot", generalisation |
| 7 | Validate forecaster on SEE Anonymous Bank (real abandonment) | MAIN, only if ≥2 h spare | real data beats any slide |
| W | Frontend: graph view, uncertainty band, domain switcher, CI whiskers, "stress" toggle, pitch mode (full-screen, big numbers) | WIN | what judges see |
| P | Deck: problem → insight (paper) → 4-layer proof → live break → generality → honest limits | MAIN + WIN | presentation score |
Stretch only, behind a recorded fallback: judges join by QR on their phones.

## Demo script (3 min)
1. Problem (20 s): a real queue photo; "everyone picks the shortest line, it's the wrong line".
2. Forecast (30 s): hybrid vs physics vs data on unseen staffing; the constraint slide.
3. Plan (30 s): same staff-minutes, peak queue down; Erlang-C guarantee band.
4. Route + Replay (60 s): close C2 live, play the day side by side; priority slider.
5. Graph (30 s): capacity check finds the overload, cross-training fixes it.
6. Generality (10 s): switch to hospital preset, everything recomputes.

## Mentor Q&A
See docs/REVIEW.md "Mentor questions". Rehearse each with the person who owns that code.
