"""
Physics-guided queue forecasting (hybrid model), inspired by
Yu & Wang, "Learning dynamical systems from data: An introduction to
physics-guided deep learning", PNAS 2024 (doi:10.1073/pnas.2311808121).

Core idea from the paper: neither a pure physics model nor a pure data model is
enough. Combine them: physics gives the structure, data learns what physics misses
("learning dynamics residuals", a hybrid physics-ML model).

Our dynamical system = any queue (office counters, hospital OPD, EV chargers, servers).
  Physics (conservation of people, a fluid-queue ODE):
      dq/dt = lambda(t) - mu * s(t)        q >= 0
      people waiting change = arrivals - people served
  What physics misses (learned from data): people who give up and leave when the
  line is long (abandonment), servers slowing down under pressure, etc.

  Hybrid step:  q[t+1] = max(0, q[t] + lambda[t] - mu*s[t]  +  residual(q, lambda, s))
  The residual is a small model fitted on data (ridge regression here, swappable for
  a neural net). Because the physics part is kept, the model stays sensible even under
  conditions it has never seen (e.g. different staffing), the paper's generalisation point.

Run:  python -m engine.physics
"""
import numpy as np

MU = 0.25  # service rate per server per minute (one person every 4 minutes)


# ---------- the "real world" (unknown to the models): has abandonment ----------
def arrival_profile(minutes=480):
    """Expected arrivals per minute over an 8-hour day: morning and afternoon rush."""
    t = np.arange(minutes)
    return 0.6 + 1.4 * np.exp(-((t - 90) / 40) ** 2) + 1.0 * np.exp(-((t - 330) / 50) ** 2)


def real_world_day(servers, seed, abandon=0.03):
    """Stochastic simulation of a real day. Returns queue length each minute."""
    rng = np.random.default_rng(seed)
    lam = arrival_profile(len(servers))
    q = np.zeros(len(servers) + 1)
    for t in range(len(servers)):
        arrivals = rng.poisson(lam[t])
        served = rng.poisson(MU * servers[t])
        leavers = rng.binomial(int(q[t]), min(1.0, abandon * q[t] / 10))  # hidden behaviour
        q[t + 1] = max(0, q[t] + arrivals - served - leavers)
    return lam, q


# ---------- three models ----------
def features(q, lam, s):
    return np.stack([q, q ** 2 / 10, lam, s, np.ones_like(q)], axis=1)


def physics_step(q, lam, s):
    return np.maximum(0, q + lam - MU * s)


def fit(train_days):
    """Fit the pure-data model and the hybrid residual on the same training data."""
    X, y_next, y_resid = [], [], []
    for lam, s, q in train_days:
        X.append(features(q[:-1], lam, s))
        y_next.append(q[1:])
        y_resid.append(q[1:] - (q[:-1] + lam - MU * s))  # what physics got wrong
    X, y_next, y_resid = np.vstack(X), np.concatenate(y_next), np.concatenate(y_resid)
    ridge = lambda X, y: np.linalg.solve(X.T @ X + 1e-2 * np.eye(X.shape[1]), X.T @ y)
    return {"data_w": ridge(X, y_next), "resid_w": ridge(X, y_resid)}


def rollout(kind, q0, lam, s, model=None, horizon=60):
    """Forecast queue length `horizon` minutes ahead from q0 (multi-step, like the paper)."""
    q, out = q0, []
    for t in range(horizon):
        f = features(np.array([q]), lam[t:t + 1], s[t:t + 1])
        if kind == "physics":
            q = physics_step(q, lam[t], s[t])
        elif kind == "data":
            q = min(500.0, max(0.0, float((f @ model["data_w"])[0])))  # capped so it cannot explode
        else:  # hybrid
            # physics constraint on the learned part: the residual can remove at most
            # the people already waiting (nobody leaves who isn't there)
            r = float(np.clip((f @ model["resid_w"])[0], -q, 1.0))
            q = max(0.0, q + lam[t] - MU * s[t] + r)
        out.append(q)
    return np.array(out)


def evaluate(model, test_days, horizon=60):
    """Mean absolute error of 60-minute forecasts started every 30 minutes."""
    err = {"physics": [], "data": [], "hybrid": []}
    for lam, s, q in test_days:
        for start in range(0, len(lam) - horizon, 30):
            truth = q[start + 1:start + 1 + horizon]
            for k in err:
                pred = rollout(k, q[start], lam[start:], s[start:], model, horizon)
                err[k].append(np.mean(np.abs(pred - truth)))
    return {k: round(float(np.mean(v)), 2) for k, v in err.items()}


# ---------- decision layer: physics-guided staffing ----------
def recommend_staffing(model, q0=0.0, target_wait=10, max_servers=8, block=30, minutes=480):
    """For each 30-min block, the fewest servers keeping forecast wait under target.
    Wait estimated with Little's law: W = queue / service throughput."""
    lam, plan, q = arrival_profile(minutes), [], q0
    for b in range(0, minutes, block):
        for s in range(1, max_servers + 1):
            sv = np.full(block, s)
            path = rollout("hybrid", q, lam[b:], sv, model, block)
            if np.max(path) / (MU * s) <= target_wait:
                break
        plan.append(s)
        q = path[-1]
    return plan


if __name__ == "__main__":
    # Train on 2 days with steady staffing, test on days with DIFFERENT staffing
    # (a distribution shift the models never saw), as in the paper's generalisation tests.
    steady = np.full(480, 6)
    shifted = np.where(np.arange(480) < 240, 4, 7)
    train = [(*real_world_day(steady, seed=s)[:1], steady, real_world_day(steady, seed=s)[1]) for s in (1, 2)]
    test = [(*real_world_day(shifted, seed=s)[:1], shifted, real_world_day(shifted, seed=s)[1]) for s in (10, 11, 12)]
    model = fit(train)
    print("60-min forecast error, people (lower is better):", evaluate(model, test))
    print("Recommended servers per 30-min block:", recommend_staffing(model))
