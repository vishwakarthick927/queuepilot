"""
Validate the physics-guided hybrid forecaster on REAL queue data.

Dataset: "Anonymous Bank" call centre, Technion SEE Center (Mandelbaum et al.), one year of
calls with VRU, queue and service timestamps and the outcome (AGENT = served, HANG = the
customer abandoned). Credit the SEE Center on any slide. Put the extracted monthly text files
in data/anonymous_bank/ (any of .txt / .csv / .tsv).

Expected columns (header names, case-insensitive; whitespace/tab/comma separated):
  vru+line, call_id, customer_id, priority, type, date, vru_entry, vru_exit, vru_time,
  q_start, q_exit, q_time, outcome, ser_start, ser_exit, ser_time, server

What we test (Yu & Wang, PNAS 2024, §3A residual models, §4A generalisation):
  physics:  q[t+1] = q[t] + A[t] - served[t]                 conservation of callers
            served[t] = min(q + A, mu * S)                   S = agents on duty
  missing:  abandonment (callers hang up). Unknown to physics, learned from data:
            residual = -(theta1 * q + theta2 * q^2/10), clipped to [-q, 0]
  hybrid:   physics + learned residual
  data:     ridge regression on [q, q^2, A, S, 1] (black box, no conservation)

Forecast 30 minutes ahead from many start times on held-out days (train on early days of the
month, test on later days: a distribution shift in time). Then the interpretability check:
the learned theta1 is a per-minute hang-up rate. Compare it with the hang-up rate measured
directly from the logs (HANG count / caller-minutes in queue). If they match, the learned part
recovered real customer patience, not a fudge factor.

Run:  python -m engine.realdata            (uses data/anonymous_bank/)
      python -m engine.realdata --selftest (synthetic file in the same format, no download)
"""
import glob
import os
import random
import sys

import numpy as np

COLS = ["vru+line", "call_id", "customer_id", "priority", "type", "date", "vru_entry", "vru_exit",
        "vru_time", "q_start", "q_exit", "q_time", "outcome", "ser_start", "ser_exit", "ser_time", "server"]
OPEN, CLOSE = 7 * 60, 23 * 60          # minutes of day analysed
HORIZON = 60
BUSY_Q = 3   # evaluate forecasts started when at least this many callers are waiting


def _sec(hms):
    try:
        h, m, s = (int(x) for x in hms.split(":"))
        return h * 3600 + m * 60 + s
    except Exception:
        return None


def load_calls(folder="data/anonymous_bank"):
    """Parse every file in the folder into a list of dicts (one per call)."""
    calls = []
    for path in sorted(glob.glob(os.path.join(folder, "*"))):
        if os.path.isdir(path):
            continue
        with open(path, errors="ignore") as f:
            header = None
            for line in f:
                parts = line.replace(",", " ").split()
                if not parts:
                    continue
                if header is None:
                    low = [p.lower() for p in parts]
                    header = low if "outcome" in low else COLS
                    if header is low:
                        continue
                if len(parts) < len(header):
                    continue
                calls.append(dict(zip(header, parts)))
    return calls


def daily_series(calls):
    """Per day, per minute: arrivals to queue A, entries to service B, hang-ups H, queue q, busy agents S."""
    days = {}
    for c in calls:
        out = c.get("outcome", "").upper()
        if out not in ("AGENT", "HANG"):
            continue
        qs, qe, ss, se = (_sec(c.get(k, "")) for k in ("q_start", "q_exit", "ser_start", "ser_exit"))
        qt = int(c.get("q_time", "0") or 0)
        arrive = qs if (qs and qt > 0) else ss
        if not arrive:
            continue
        days.setdefault(c.get("date"), []).append((out, arrive, qe if qt > 0 else arrive, ss, se))
    series = {}
    for d, rows in days.items():
        n = CLOSE - OPEN
        A, B, H, S = (np.zeros(n) for _ in range(4))
        q = np.zeros(n + 1)
        for out, arr, qexit, ss, se in rows:
            ia, ix = int(arr // 60) - OPEN, int(qexit // 60) - OPEN
            if 0 <= ia < n:
                A[ia] += 1
                q[ia + 1:max(ia + 1, min(ix, n)) + 1] += 1 if ix > ia else 0
            if out == "AGENT" and ss and se:
                i0, i1 = int(ss // 60) - OPEN, int(se // 60) - OPEN
                if 0 <= i0 < n:
                    B[i0] += 1
                S[max(0, i0):max(0, min(i1, n))] += 1  # busy during [start, end)
            elif out == "HANG" and 0 <= ix < n:
                H[ix] += 1
        if A.sum() > 200:  # skip near-empty days
            series[d] = {"A": A, "B": B, "H": H, "S": S, "q": q[:n + 1]}
    return series


def fit(train, profile, mu):
    R, y, X, yd = [], [], [], []
    for d in train.values():
        q, A, S = d["q"], d["A"], d["S"]
        phys = np.maximum(0, q[:-1] + A - np.minimum(q[:-1] + A, mu * np.maximum(S, 1)))
        R.append(np.stack([q[:-1], q[:-1] ** 2 / 10], 1)); y.append(q[1:] - phys)
        X.append(np.stack([q[:-1], q[:-1] ** 2 / 10, A, S, np.ones_like(A)], 1)); yd.append(q[1:])
    ridge = lambda X, y: np.linalg.solve(X.T @ X + 1e-2 * np.eye(X.shape[1]), X.T @ y)
    return {"resid_w": ridge(np.vstack(R), np.concatenate(y)), "data_w": ridge(np.vstack(X), np.concatenate(yd))}


def rollout(kind, q0, Ahat, S, mu, m, hangups=None):
    """Forecast queue length; if `hangups` is a list, also accumulate predicted hang-ups."""
    q, out = q0, []
    for t in range(len(Ahat)):
        a, s = Ahat[t], max(S[t], 1)
        if kind == "data":
            q = max(0.0, float(np.array([q, q * q / 10, a, s, 1.0]) @ m["data_w"]))
        else:
            q = q + a - min(q + a, mu * s)
            if kind == "hybrid":
                r = float(np.clip(float(np.array([q, q * q / 10]) @ m["resid_w"]), -q, 0.0))
                q = q + r
                if hangups is not None:
                    hangups.append(-r)
        out.append(q)
    return np.array(out)


def evaluate(series, train_frac=0.6):
    days = sorted(series)
    cut = max(1, int(len(days) * train_frac))
    train = {d: series[d] for d in days[:cut]}
    test = {d: series[d] for d in days[cut:]}
    profile = np.mean([d["A"] for d in train.values()], axis=0)   # forecast of arrivals by minute of day
    busy = sum(d["S"].sum() for d in train.values())
    served = sum(d["B"].sum() for d in train.values())
    mu = served / busy if busy else 0.2                            # calls per agent-minute
    m = fit(train, profile, mu)
    err = {"physics": [], "data": [], "hybrid": [], "naive_persistence": []}
    hang_err = {"physics (always 0)": [], "hybrid": [], "naive (last hour's rate)": []}
    for d in test.values():
        for t0 in range(60, len(d["A"]) - HORIZON, 5):
            if d["q"][t0] < BUSY_Q:
                continue
            truth = d["q"][t0 + 1:t0 + 1 + HORIZON]
            Ahat, S = profile[t0:t0 + HORIZON], d["S"][t0:t0 + HORIZON]
            for k in ("physics", "data", "hybrid"):
                err[k].append(np.mean(np.abs(rollout(k, d["q"][t0], Ahat, S, mu, m) - truth)))
            err["naive_persistence"].append(np.mean(np.abs(d["q"][t0] - truth)))
            hs = []
            rollout("hybrid", d["q"][t0], Ahat, S, mu, m, hs)
            true_h = d["H"][t0:t0 + HORIZON].sum()
            hang_err["hybrid"].append(abs(sum(hs) - true_h))
            hang_err["physics (always 0)"].append(true_h)
            hang_err["naive (last hour's rate)"].append(abs(d["H"][t0 - 60:t0].sum() - true_h))
    qmin = sum(d["q"].sum() for d in train.values())
    hangs = sum(d["H"].sum() for d in train.values())
    return {
        "days_train": len(train), "days_test": len(test),
        "mu_calls_per_agent_min": round(float(mu), 3),
        "busy_starts_tested": len(err["hybrid"]),
        "queue_forecast_mae_60min": {k: round(float(np.mean(v)), 2) for k, v in err.items()},
        "hangups_next_hour_abs_error": {k: round(float(np.mean(v)), 2) for k, v in hang_err.items()},
        # learned residual = -(w0*q + w1*q^2/10): hang-ups per waiting caller per minute = w0 + w1*q/10
        "learned_hangup_rate_per_min": {f"q={k}": round(float(-(m["resid_w"][0] + m["resid_w"][1] * k / 10)), 4)
                                        for k in (3, 6, 10)},
        "measured_hangup_rate_per_min": round(float(hangs / qmin), 4) if qmin else None,
    }


def _synthetic(folder, days=20, seed=0, patience_rate=0.08):
    """Write a fake file in the real format so the pipeline can be tested without the download."""
    rng = random.Random(seed)
    os.makedirs(folder, exist_ok=True)
    fmt = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"
    lines = [" ".join(COLS)]
    cid = 0
    for d in range(days):
        agents_free = [OPEN * 60] * 8
        t = OPEN * 60.0
        while t < CLOSE * 60 - 600:
            rate = 1.6 + 1.2 * np.exp(-((t / 60 - 660) / 90) ** 2)     # calls per minute, peak ~11:00
            t += rng.expovariate(rate) * 60
            k = min(range(8), key=lambda i: agents_free[i])
            start = max(t, agents_free[k])
            patience = rng.expovariate(patience_rate) * 60
            serv = rng.expovariate(1 / 3.5) * 60
            cid += 1
            if start - t > patience:
                row = ["AA0101", cid, 0, 1, "PS", f"9901{d + 1:02d}", fmt(t - 20), fmt(t), 20,
                       fmt(t), fmt(t + patience), int(patience), "HANG", "0:00:00", "0:00:00", 0, "NO_SERVER"]
            else:
                agents_free[k] = start + serv
                row = ["AA0101", cid, 0, 1, "PS", f"9901{d + 1:02d}", fmt(t - 20), fmt(t), 20,
                       fmt(t), fmt(start), int(start - t), "AGENT", fmt(start), fmt(start + serv), int(serv), f"A{k}"]
            lines.append(" ".join(str(x) for x in row))
    with open(os.path.join(folder, "synthetic.txt"), "w") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    import json
    folder = "data/anonymous_bank"
    if "--selftest" in sys.argv:
        folder = "/tmp/qp_selftest"
        _synthetic(folder)
    s = daily_series(load_calls(folder))
    if not s:
        sys.exit(f"No usable days in {folder}. Download and extract the dataset there first.")
    print(json.dumps(evaluate(s), indent=2))
