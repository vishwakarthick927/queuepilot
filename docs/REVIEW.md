# Judge-style red-team of the engine (WIN, 14 Nov 18:45)
Read-only review: ran tests (7/7 pass) and scratch scripts against the venv. Nothing in engine/ was edited. MAIN owns all fixes.

## Must-fix before mentors see it
1. **Demo scenario is unstable.** In simulation.py, gap 1.6 → λ≈0.625/min. Certificate load = 0.625×0.2×20 = 2.5 Erlangs on C1+C2, i.e. **125% loaded**, so waits grow without bound and every number depends on n_people. Pooled vs shortest-line: n=150 −1.9 min (wins 94% of seeds); n=600 −0.24±0.63 (not significant). At a STABLE load (gap 2.5, n=300) the gain is real: 7.1→5.0 min, wins 100% of seeds. → Re-baseline the demo to a stable load; show overload as a separate "stress" scenario.
2. **Hybrid wins partly by artefact.** physics.py `features` includes s, but s is constant (6) in training, so its weight is just an intercept split by ridge. Without s: hybrid 4.09 vs physics 4.32. With abandon=0: hybrid 8.97 vs physics 3.80 (learned part HURTS when there is nothing to learn). **Tested fix:** residual features [q, q²/10] only and clip residual to [−q, 0] (people can only leave). Result 1.80 vs 4.32, and 4.34 vs 3.80 with no abandonment. That is the paper's "physics constraints on the learned part" done properly, and a great slide.
3. **The staffing gain is not from the forecast.** A no-model plan ceil(0.8·λ̄/μ) with the same 58 server-blocks gets avg queue 5.4 / peak 19.4 vs hybrid 5.3 / 18.3. The −27% comes from time-varying staffing. The hybrid also staffs *less* than physics (58 vs 68) because people abandon: we under-staff because customers give up. Also q/(μs) is drain time, not Little's law (W = L/λ_eff). Models are given the true λ(t), so this is conditional forecasting.
4. **Metrics.** "fcfs" is JSQ, and only "queuepilot" gets priority (`use_priority=(key=="queuepilot")`); check whether pooled should too. Jain on waits+1 depends on the arbitrary +1 and mostly measures class mix → report per-class mean wait or slowdown (wait/service time). Route-on-arrival `free_at_est` never re-syncs with actual completions.
5. **Claims.** "~10–17%" in CLAUDE.md: 100-run numbers are 9% (QP) and 11.5% (pooled); 18% is seed 42 only. Tests assert inequalities on fixed seeds without CIs.

## Ranked engine additions (~1h each)
1. Fix the residual (#2) + tests for no-abandonment and a seed sweep with 95% CI.
2. Stability via max-flow on the SKILL bipartite graph: source→service (cap = Erlangs) →counter (∞ if capable) →sink (cap 1). Shows the certificate overload and gives cross-training advice ("let C3 do certificates → load fits"). This is the correct graph-theory use; min-cut on a tandem hospital line is trivial.
3. Erlang-C chance-constrained staffing: P(W>t) = C(c,a)·e^(−(cμ−λ)t), pick the smallest c with P(W>10)<5%. Exact, explainable, and an uncertainty guarantee a proportional rule can't give. Compare honestly vs naive and flat plans.
4. Re-baseline to stable load; publish mean ± CI, win rate, per-class waits.
5. MPC re-plan every 15 min from the observed queue + a 3-parameter few-shot fit (λ scale, μ, patience θ) for a "new site" preset.

## Mentor questions → answers
1. Stable? "Max-flow on the skill graph checks it; the first mix was 125% loaded on certificates, so we re-baselined and show overload separately."
2. Ridge = deep learning? "No: a physics-constrained residual. A small MLP changes nothing structurally; with this little data ridge is the honest choice."
3. Hybrid hurts when physics is right? "Tested: with a sign-constrained, abandonment-shaped residual it stays within 0.5 of physics."
4. Staffing gain = just time-varying staffing? "Mostly yes; the model adds the Erlang-C guarantee."
5. Why pool? "One queue for c servers beats c separate lines (Erlang-C vs M/M/1); late binding removes wrong-line regret."
6. Seed luck? "Mean ± 95% CI over 100 crowds + per-seed win rate."
7. Where does λ(t) come from? "Historical profile scaled by today's first arrivals (few-shot), corrected every 15 min."
8. Fairness? "Per-class wait and slowdown; the aging knob trades avg vs p95, we show the frontier."

## Likely surprise constraints → one-line change
Balking: drop if wait > θ, count lost · speeds: duration / speed · breaks: closures (done) · appointments: priority from slot lateness · max-wait SLA: score += big·(wait>limit) · staff budget: Σplan ≤ B, greedy by marginal Erlang-C gain · group arrivals: batch size from rng.choices · surge: λ×k in a window + MPC re-plan · multi-stage visit: end time → next stage arrival.
