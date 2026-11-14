# The research paper, in plain words, and exactly how QueuePilot uses it

Yu & Wang, "Learning dynamical systems from data: An introduction to physics-guided deep learning", PNAS 2024 (doi:10.1073/pnas.2311808121). Read this before explaining the research to judges or mentors.

## Big idea
- Physics models: explainable, need little data, but rely on strong assumptions and can be slow.
- Deep learning: fast and flexible, but needs lots of data, can predict physically impossible things, hard to interpret.
- Physics-guided DL: use physics for what we know, learn only what we don't. Like a student who knows the formula AND learns from practice problems.

## Section by section
**1. Why learn dynamical systems** (anything that changes over time by rules: weather, fluids, queues)
- 1A Background: learning = finding the rule F that says how the system changes.
- 1B Faster simulation: DL replaces slow solvers (fluids, weather, molecules); PINNs.
- 1C Filling unknown physics: when part of the physics is unknown, DL fills the missing terms in a hybrid model. **QueuePilot is built on this.**
- 1D Discovering equations: find the actual formula from data (symbolic / sparse regression).
- 1E Generalising: a good model must work on conditions it never saw.

**2. The learning pipeline**
- 2A Data: time data isn't independent samples, so use rolling windows.
- 2B Models: LSTM, Transformer, CNN, etc. No standard "foundation model" for dynamics yet.
- 2C Objectives: solving equations (penalise breaking the equation, PINNs); forecasting (step by step, errors accumulate); discovering equations (building blocks + keep only a few).

**3. Four ways to mix physics and DL** (most physics → most data)
- 3A **Residual model**: true dynamics = known physics + learned leftover. Constraints (e.g. non-negativity, stability) may be needed. **What we use.**
- 3B Trainable operators: neural networks replace parts of a solver (Fourier Neural Operators).
- 3C Equivariant learning: build symmetries in so conservation laws are respected (Noether).
- 3D Disentangled representations: split hidden variables into physical factors (weaker physics bias).

**4. Open problems**
- 4A Distribution shift: models fail when conditions change.
- 4B Stability: long forecasts drift or blow up.
- 4C Uncertainty: DL is overconfident.
- 4D Curved spaces (oceans on a sphere). Not relevant to us.
- 4E Explainability and causality: physical laws are causal; models should be too.
- 4F Theory is still limited.

**5. Conclusion**: building domain knowledge into data-driven models is essential for trustworthy AI.

## How QueuePilot uses it
| Paper idea | QueuePilot |
|---|---|
| 1C + 3A physics + learned residual | Physics: people waiting next minute = waiting now + arrivals − served (conservation). Learned part: only what physics misses, people giving up (hang-ups). Flood twin: water conservation + learned drain efficiency. ER radar: physics + learned relief/arrivals. |
| 3A constraints | Learned part bounded: can only remove people actually waiting ([−q, 0]); drain efficiency bounded 0..1. |
| 3C conservation | Conservation hard-coded in the formula (simpler cousin of equivariant networks; we don't claim equivariant nets). |
| 2C multi-step forecasting | 30–60 min (flood: 3 h) rollouts, error measured over the whole horizon. |
| 4A distribution shift | Tested on unseen staffing, later real days, a hospital never seen in training. |
| 4B stability | Pure-data model blew up (error 69) in one test; physics anchor keeps the hybrid sane. |
| 4E explainability | Learned term has physical meaning (hang-up rate per minute), checked against real logs. |
| 4C uncertainty | WIN's R1: MC uncertainty. Erlang-C waiting guarantee planned. |
| Fluids are the paper's core example | Flood twin applies the method to real water flow, then couples it to human queues (evacuation, shelters, hospitals). |

## Real-data proof (Technion SEE "Anonymous Bank" call centre, 183 train days → 123 test days, 3,906 busy starts)
- **Interpretability, the headline:** learned hang-up rate 0.143–0.153 per waiting caller per minute vs **0.156 measured directly from the logs**. The learned residual recovered real human patience without being told it.
- Queue length 60 min ahead (MAE): physics 6.19, hybrid 3.09, naive persistence 3.17, pure data 2.73. Hybrid halves physics' error; pure data is best on this metric (say so).
- Hang-ups in the next hour (abs error): physics 27.1 (can't predict any), hybrid 21.6, naive "same as last hour" 14.0. Naive wins here (say so).
- Honest framing: the hybrid's value is a forecaster that obeys conservation, stays stable, and whose learned part means something real and checkable. It is not the most accurate black box on every metric.

## Honest points for Q&A
- The office/call-centre residual is ridge regression, not deep learning; WIN's ER radar and flood forecasts are real neural networks (PyTorch) with bounded learned terms.
- We use Section 3A directly. We don't claim 3B–3D.
- Simulated sectors (EV, concrete, milk, asphalt, ER, flood) use stated assumptions; the bank result is real data.

## 10-second version
"Physics models are reliable but rigid; AI is flexible but breaks rules. We use physics for what we know, like conservation of people or water, and let AI learn only what physics misses, like customers giving up. On a year of real bank calls, what it learned matched the real hang-up rate: 0.15 per minute, learned vs measured."
