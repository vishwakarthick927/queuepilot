"""
QueuePilot-PGDL: a physics-guided deep model for queues in ANY sector.

Research basis: Yu & Wang, "Learning dynamical systems from data: An introduction to
physics-guided deep learning", PNAS 2024. Their Section 4 lists open challenges; this
script targets four of them in one small model:

  Gap 1 (Sec 4A, generalisation): "most DL models can only generalize within the
        interpolated range of parameters, but cannot extrapolate beyond" it.
        -> test on staffing levels never seen in training, and on a sector never seen.
  Gap 2 (Sec 4B, stability): "very little guarantee exists to certify the stability of
        the learned model".
        -> the learned terms are bounded by physics (see below), so every forecast is
           physically admissible by construction; we check it and count violations of the
           black-box models.
  Gap 3 (Sec 4C, uncertainty): "DL models ... tend to produce overconfident predictions".
        -> deep ensemble + Monte Carlo simulation of the learned model gives a band;
           we measure its calibration (coverage).
  Gap 4 (Sec 3A, interpretability): residual models are a "black box".
        -> the network outputs two physical quantities (server busy-fraction, chance a
           waiting person gives up), which we can read off and compare with the truth.

One model for every sector: each sector gets a learned vector z ("sector fingerprint",
3 numbers). A NEW sector is learned by fitting only its z from ONE day of data,
with the network frozen (few-shot transfer).

The model, one minute at a time:
    physics:  q_next = max(0, q + arrivals - mu * servers)               (conservation of people)
    learned:  u, p   = sigmoid(NeuralNet(state, z))                      (two numbers in [0, 1])
              u = fraction of capacity actually used (servers idle when work arrives unevenly)
              p = chance a waiting person gives up this minute
    hybrid:   q_next = max(0, q + arrivals - mu * servers * u - q * p)
The learned terms can only SLOW service (never faster than capacity) and only let WAITING
people leave (never more than are there). So every prediction is physically admissible:
    max(0, arrivals - capacity) <= q_next <= q + arrivals   (no one is created or destroyed)

Data is SIMULATED (we know the truth, so we can score every claim). Run:
    python -m research.pgdl            (about 1-2 minutes on a laptop CPU)
"""
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

torch.set_num_threads(4)
OUT = Path(__file__).parent
H_TRAIN, H_TEST, DAY = 30, 60, 480   # training rollout, forecast horizon, minutes per day


# ---------------------------------------------------------------------------
# 1. The "real world" for five sectors (unknown to the models)
# ---------------------------------------------------------------------------
def bump(t, centre, width):
    return np.exp(-((t - centre) / width) ** 2)

# mu = service rate per server per minute, patience = minutes people tolerate,
# servers = staffing range seen in training, lam = arrivals per minute over the day.
SECTORS = {
    "office":   dict(mu=0.25, patience=15, servers=(4, 6),
                     lam=lambda t: 0.6 + 0.9 * bump(t, 90, 40) + 0.7 * bump(t, 330, 50)),
    "hospital": dict(mu=0.10, patience=60, servers=(9, 12),
                     lam=lambda t: 0.5 + 0.8 * bump(t, 60, 60) + 0.3 * bump(t, 300, 60)),
    "bank":     dict(mu=0.20, patience=20, servers=(5, 7),
                     lam=lambda t: 0.7 + 0.8 * bump(t, 240, 40)),
    # held out: never seen in training, learned few-shot
    "ev_charging": dict(mu=1 / 30, patience=25, servers=(18, 22),
                        lam=lambda t: 0.4 + 0.5 * bump(t, 390, 60)),
}
TRAIN_SECTORS = ["office", "hospital", "bank"]
NEW_SECTOR = "ev_charging"


def true_hazard(q, mu, s, patience):
    """Per-minute chance that a waiting person gives up. Grows with expected wait."""
    wait = q / (mu * s)
    return np.minimum(0.3, 0.05 * (wait / patience) ** 2)


def staffing(lo, hi, rng):
    """Random staffing, changing every hour, between lo and hi servers."""
    return np.repeat(rng.integers(lo, hi + 1, size=8), 60).astype(float)


def real_day(name, servers, seed, surge=1.0):
    """One stochastic day. Returns arrival-rate curve, servers, queue length per minute.
    surge scales demand (1.5 = 50% more people than any training day)."""
    sec, rng = SECTORS[name], np.random.default_rng(seed)
    lam = surge * sec["lam"](np.arange(DAY))
    q, left = np.zeros(DAY + 1), np.zeros(DAY)
    for t in range(DAY):
        arrivals = rng.poisson(lam[t])
        served = min(q[t] + arrivals, rng.poisson(sec["mu"] * servers[t]))
        leavers = rng.binomial(int(q[t]), true_hazard(q[t], sec["mu"], servers[t], sec["patience"]))
        q[t + 1] = max(0, q[t] + arrivals - served - leavers)
        left[t] = leavers   # logged by many real systems: call-centre hang-ups, "left without being seen"
    return dict(sector=name, lam=lam, mus=sec["mu"] * servers, q=q, left=left)


# ---------------------------------------------------------------------------
# 2. Models: physics only, pure deep learning, unconstrained hybrid, ours
# ---------------------------------------------------------------------------
def features(q, lam, mus):
    """What the network sees: queue, arrivals, capacity, load, expected wait (scaled)."""
    return torch.stack([q / 50, lam, mus, lam / mus, (q / mus) / 60], dim=-1)


class QueueModel(nn.Module):
    """mode = 'physics' | 'dl' (no physics) | 'free' (physics + any residual) | 'ours'."""

    def __init__(self, mode, n_sectors=len(TRAIN_SECTORS), zdim=3, hidden=32):
        super().__init__()
        self.mode = mode
        self.z = nn.Embedding(n_sectors, zdim)           # one learned vector per sector
        nn.init.normal_(self.z.weight, std=0.1)
        self.net = nn.Sequential(nn.Linear(5 + zdim, hidden), nn.Tanh(),
                                 nn.Linear(hidden, hidden), nn.Tanh(), nn.Linear(hidden, 2))
        if mode == "ours":   # start near "servers fully used, nobody leaves"
            nn.init.constant_(self.net[-1].bias, 0.0)
            with torch.no_grad():
                self.net[-1].bias[0], self.net[-1].bias[1] = 3.0, -4.0

    def step(self, q, lam, mus, z):
        phys = torch.relu(q + lam - mus)
        if self.mode == "physics":
            return phys
        out = self.net(torch.cat([features(q, lam, mus), z], dim=-1))[..., 0]
        if self.mode == "dl":       # black box: learns the whole change in queue
            return torch.relu(q + 5 * out)
        if self.mode == "free":     # hybrid, but the learned part may add OR remove people
            return torch.relu(phys + 5 * out)
        u, p = self.terms(q, lam, mus, z)
        return torch.relu(q + lam - mus * u - q * p)

    def terms(self, q, lam, mus, z):
        """Interpretable outputs of 'ours': (busy fraction u, leave probability p), both in [0, 1]."""
        out = torch.sigmoid(self.net(torch.cat([features(q, lam, mus), z], dim=-1)))
        return out[..., 0], out[..., 1]

    def leave_prob(self, q, lam, mus, z):
        return self.terms(q, lam, mus, z)[1]

    def rollout(self, q0, lam, mus, z, return_left=False):
        """Forecast len(lam[0]) minutes ahead from q0, feeding predictions back in.
        With return_left, also returns how many people the model says gave up each minute."""
        qs, left, q = [], [], q0
        for k in range(lam.shape[1]):
            if return_left:
                left.append(q * self.leave_prob(q, lam[:, k], mus[:, k], z))
            q = self.step(q, lam[:, k], mus[:, k], z)
            qs.append(q)
        qs = torch.stack(qs, dim=1)
        return (qs, torch.stack(left, dim=1)) if return_left else qs


# ---------------------------------------------------------------------------
# 3. Training data: many short windows cut from each day
# ---------------------------------------------------------------------------
def windows(days, horizon, every):
    q0, lam, mus, target, sid, left = [], [], [], [], [], []
    for d in days:
        for t in range(0, DAY - horizon + 1, every):
            q0.append(d["q"][t]); lam.append(d["lam"][t:t + horizon]); mus.append(d["mus"][t:t + horizon])
            target.append(d["q"][t + 1:t + horizon + 1]); sid.append(d.get("sid", 0))
            left.append(d["left"][t:t + horizon])
    f = lambda x: torch.tensor(np.array(x), dtype=torch.float32)
    return dict(q0=f(q0), lam=f(lam), mus=f(mus), target=f(target), sid=torch.tensor(sid), left=f(left))


def fit(model, data, steps, params=None, z_fixed=None, lr=3e-3, use_left=True):
    """Train by rolling the model forward and matching the real queue (multi-step loss).
    For 'ours', use_left also matches the logged number of people who gave up each minute:
    queue length alone cannot tell "people left" apart from "servers were slower"."""
    opt = torch.optim.Adam(params if params is not None else model.parameters(), lr=lr)
    for _ in range(steps):
        z = z_fixed.expand(len(data["q0"]), -1) if z_fixed is not None else model.z(data["sid"])
        if model.mode == "ours" and use_left:
            pred, left = model.rollout(data["q0"], data["lam"], data["mus"], z, return_left=True)
            loss = ((pred - data["target"]) ** 2).mean() + 5 * ((left - data["left"]) ** 2).mean()
        else:
            loss = ((model.rollout(data["q0"], data["lam"], data["mus"], z) - data["target"]) ** 2).mean()
        opt.zero_grad(); loss.backward(); opt.step()
    return loss.item()


def few_shot_z(model, data, steps=300, use_left=True):
    """New sector: freeze the network, learn ONLY its 3-number fingerprint z."""
    z = model.z.weight.detach().mean(0, keepdim=True).clone().requires_grad_(True)
    for p in model.parameters():
        p.requires_grad_(False)
    fit(model, data, steps, params=[z], z_fixed=z, lr=0.05, use_left=use_left)
    for p in model.parameters():
        p.requires_grad_(True)
    return z.detach()


@torch.no_grad()
def mae(model, data, z):
    pred = model.rollout(data["q0"], data["lam"], data["mus"], z.expand(len(data["q0"]), -1))
    return (pred - data["target"]).abs().mean().item(), pred


# ---------------------------------------------------------------------------
# 4. Uncertainty: simulate the learned model many times (deep ensemble x Monte Carlo)
# ---------------------------------------------------------------------------
@torch.no_grad()
def mc_band(models_z, data, paths=200, physics_only=False, seed=0):
    """5%-95% band of the queue over the horizon. Each path picks an ensemble member,
    then draws random arrivals, services and (learned) departures minute by minute."""
    g = torch.Generator().manual_seed(seed)
    n, h = data["lam"].shape
    q = data["q0"].repeat(paths)                       # shape: paths * n
    lam, mus = data["lam"].repeat(paths, 1), data["mus"].repeat(paths, 1)
    member = torch.randint(max(1, len(models_z)), (paths,), generator=g).repeat_interleave(n)
    out = []
    for k in range(h):
        arrivals = torch.poisson(lam[:, k], generator=g)
        served = torch.minimum(q + arrivals, torch.poisson(mus[:, k], generator=g))
        leave = torch.zeros_like(q)
        if not physics_only:
            # the random draw of services already produces idle time, so only p is needed here
            p = torch.zeros_like(q)
            for i, (m, z) in enumerate(models_z):
                idx = member == i
                if idx.any():
                    p[idx] = m.leave_prob(q[idx], lam[idx, k], mus[idx, k], z.expand(int(idx.sum()), -1))
            leave = torch.distributions.Binomial(q.round(), p.clamp(0, 1)).sample()
        q = torch.relu(q + arrivals - served - leave)
        out.append(q)
    sims = torch.stack(out, 1).view(paths, n, h)
    return sims.quantile(0.05, 0), sims.quantile(0.95, 0)


def coverage(lo, hi, target):
    return ((target >= lo) & (target <= hi)).float().mean().item()


# ---------------------------------------------------------------------------
# 5. The experiment
# ---------------------------------------------------------------------------
def main():
    torch.manual_seed(0)
    rng = np.random.default_rng(0)
    train_days, test_in, test_out, test_surge, test_day = [], [], [], [], []
    for sid, name in enumerate(TRAIN_SECTORS):
        lo, hi = SECTORS[name]["servers"]
        for k in range(12):
            train_days.append({**real_day(name, staffing(lo, hi, rng), seed=1000 * sid + k), "sid": sid})
        for k in range(3):
            test_in.append({**real_day(name, staffing(lo, hi, rng), seed=1000 * sid + 100 + k), "sid": sid})
            # understaffed: fewer servers than ANY training day (extrapolation, Gap 1)
            test_out.append({**real_day(name, np.full(DAY, lo - 1.0), seed=1000 * sid + 200 + k), "sid": sid})
            # demand surge: 50% more arrivals than any training day (extrapolation, Gap 1)
            test_surge.append({**real_day(name, staffing(lo, hi, rng), seed=1000 * sid + 300 + k, surge=1.5), "sid": sid})
            # whole day from 09:00, 480 minutes ahead (error accumulation, Gap 2)
            test_day.append({**real_day(name, staffing(lo, hi, rng), seed=1000 * sid + 400 + k), "sid": sid})

    lo, hi = SECTORS[NEW_SECTOR]["servers"]
    ev_fit = [real_day(NEW_SECTOR, staffing(lo, hi, rng), seed=9000)]                  # ONE day
    ev_test = [real_day(NEW_SECTOR, staffing(lo - 3, hi, rng), seed=9100 + k) for k in range(4)]

    train = windows(train_days, H_TRAIN, every=5)
    tests = {"Seen sectors, seen staffing": windows(test_in, H_TEST, 15),
             "Seen sectors, UNDERSTAFFED (never seen)": windows(test_out, H_TEST, 15),
             "DEMAND SURGE x1.5 (never seen)": windows(test_surge, H_TEST, 15),
             "WHOLE DAY, 480 min ahead": windows(test_day, DAY, DAY)}
    ev_train, ev_eval = windows(ev_fit, H_TRAIN, 5), windows(ev_test, H_TEST, 15)

    names = {"physics": "Physics only", "dl": "Pure deep learning", "free": "Hybrid, unconstrained",
             "ours_q": "Ours, queue data only", "ours": "QueuePilot-PGDL (ours)"}
    ensemble, table, preds, first = [], {}, {}, {}
    for mode in names:
        members = 5 if mode == "ours" else 1
        for seed in range(members):
            torch.manual_seed(seed)
            m = QueueModel("ours" if mode == "ours_q" else mode)
            if mode != "physics":
                fit(m, train, steps=400, use_left=(mode == "ours"))
            first.setdefault(mode, m)
            row = table.setdefault(names[mode], {})
            for label, d in tests.items():
                err, pred = mae(m, d, m.z(d["sid"]).detach() if mode != "physics" else torch.zeros(1, 3))
                row.setdefault(label, []).append(err)
                if seed == 0:
                    preds[(mode, label)] = pred
            z_new = few_shot_z(m, ev_train, use_left=(mode == "ours")) if mode != "physics" else torch.zeros(1, 3)
            first.setdefault(mode + "_z", z_new)
            err, pred = mae(m, ev_eval, z_new)
            row.setdefault("NEW sector: EV charging (fit on 1 day)", []).append(err)
            if seed == 0:
                preds[(mode, "ev")] = pred
            if mode == "ours":
                ensemble.append((m, z_new))

    # mean over ensemble members for 'ours'; others have one entry
    table = {k: {t: round(float(np.mean(v)), 2) for t, v in row.items()} for k, row in table.items()}

    # Gap 2: physical admissibility. Every one-minute step must satisfy
    #   max(0, arrivals - capacity) <= q_next <= q + arrivals
    # i.e. never serve faster than capacity, never remove more people than exist, never create people.
    with torch.no_grad():
        checks = {}
        d = tests["DEMAND SURGE x1.5 (never seen)"]
        for mode in ["dl", "free", "ours"]:
            m = first[mode]
            z = m.z(d["sid"])
            q_prev = torch.cat([d["q0"][:, None], m.rollout(d["q0"], d["lam"], d["mus"], z)[:, :-1]], 1)
            q_next = m.rollout(d["q0"], d["lam"], d["mus"], z)
            low, high = torch.relu(d["lam"] - d["mus"]), q_prev + d["lam"]
            bad = (q_next < low - 1e-4) | (q_next > high + 1e-4)
            checks[names[mode]] = {"impossible_steps": int(bad.sum()), "steps_checked": bad.numel()}

    # Gap 3: calibrated uncertainty on the NEW sector
    lo_o, hi_o = mc_band(ensemble, ev_eval)
    lo_p, hi_p = mc_band([], ev_eval, physics_only=True)
    cov = {"QueuePilot-PGDL (ours)": {"coverage": round(coverage(lo_o, hi_o, ev_eval["target"]), 3),
                                      "avg_band_width_people": round((hi_o - lo_o).mean().item(), 1)},
           "Physics-only simulation": {"coverage": round(coverage(lo_p, hi_p, ev_eval["target"]), 3),
                                       "avg_band_width_people": round((hi_p - lo_p).mean().item(), 1)}}

    # Gap 4: interpretability. Does the network's "chance of leaving" match the truth across the
    # whole range of waits (0 to 2x patience)? Average absolute gap, per sector.
    interp = {}
    w = np.linspace(0.1, 2, 40)
    for name in TRAIN_SECTORS + [NEW_SECTOR]:
        sec = SECTORS[name]
        s = float(np.mean(sec["servers"]))
        q = torch.tensor(w * sec["patience"] * sec["mu"] * s, dtype=torch.float32)
        lam = torch.full_like(q, sec["mu"] * s); mus = lam.clone()
        truth = true_hazard(q.numpy(), sec["mu"], s, sec["patience"])
        row = {}
        for label, pairs in [("ours", ensemble), ("ours_queue_only", [(first["ours_q"], first["ours_q_z"])])]:
            gaps = []
            for m, z_new in pairs:
                z = z_new if name == NEW_SECTOR else m.z(torch.tensor([TRAIN_SECTORS.index(name)]))
                with torch.no_grad():
                    gaps.append(np.abs(m.leave_prob(q, lam, mus, z.expand(len(q), -1)).numpy() - truth).mean())
            row[label] = round(float(np.mean(gaps)), 4)
        row["truth_avg"] = round(float(truth.mean()), 4)
        interp[name] = row

    results = {"forecast_mae_people": table, "stability_check": checks,
               "coverage_90pct_band_new_sector": cov, "leave_prob_curve_gap": interp,
               "setup": {"train_sectors": TRAIN_SECTORS, "new_sector": NEW_SECTOR, "train_days_per_sector": 12,
                         "new_sector_days": 1, "horizon_min": H_TEST, "ensemble": len(ensemble)}}
    # Sample efficiency (the paper's core promise for physics): train on fewer days, test on the surge.
    sweep = {}
    surge = tests["DEMAND SURGE x1.5 (never seen)"]
    for n_days in [1, 3, 12]:
        few = windows([d for i, d in enumerate(train_days) if i % 12 < n_days], H_TRAIN, 5)  # first n days of each sector
        for mode in ["dl", "free", "ours"]:
            torch.manual_seed(0)
            m = QueueModel(mode)
            fit(m, few, steps=400)
            sweep.setdefault(names[mode], {})[f"{n_days} day(s)/sector"] = round(mae(m, surge, m.z(surge["sid"]).detach())[0], 2)
    results["sample_efficiency_surge_mae"] = sweep

    (OUT / "results.json").write_text(json.dumps(results, indent=2))
    report(results)
    plot(preds, tests, ev_eval, lo_o, hi_o, interp, ensemble)


def report(r):
    cols = list(next(iter(r["forecast_mae_people"].values())).keys())
    print("\n60-minute forecast error (avg people off, lower is better)")
    print(f"{'':26}" + "".join(f"{c[:24]:>26}" for c in cols))
    for name, row in r["forecast_mae_people"].items():
        print(f"{name:26}" + "".join(f"{row[c]:>26.2f}" for c in cols))
    print("\nPhysically impossible steps (surge test):", json.dumps(r["stability_check"]))
    print("\nSurge-test error vs training days per sector:")
    for name, row in r["sample_efficiency_surge_mae"].items():
        print(f"  {name:26}", row)
    print("Coverage of 90% band, new sector:", r["coverage_90pct_band_new_sector"])
    print("Avg gap, learned vs true chance of leaving per minute (lower is better):", r["leave_prob_curve_gap"])


def plot(preds, tests, ev_eval, lo, hi, interp, ensemble):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {"physics": "#f2a541", "dl": "#f06a6a", "free": "#5aa9ff", "ours": "#3ddc84"}
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.6))
    label = "Seen sectors, UNDERSTAFFED (never seen)"
    i = int(tests[label]["target"][:, -1].argmax())               # the hardest window
    ax[0].plot(tests[label]["target"][i], "k", lw=1.5, label="Actual")
    for mode, c in colors.items():
        ax[0].plot(preds[(mode, label)][i], color=c, lw=2 if mode == "ours" else 1.2, label=mode)
    ax[0].set(title="Understaffed day (never seen in training)", xlabel="minutes ahead", ylabel="people waiting")
    ax[0].legend(frameon=False)
    j = int(ev_eval["target"][:, -1].argmax())
    ax[1].fill_between(range(H_TEST), lo[j], hi[j], color="#3ddc84", alpha=0.25, label="90% band (ours)")
    ax[1].plot(ev_eval["target"][j], "k", lw=1.5, label="Actual")
    ax[1].plot(preds[("ours", "ev")][j], color="#3ddc84", lw=2, label="ours")
    ax[1].plot(preds[("physics", "ev")][j], color="#f2a541", lw=1.2, label="physics")
    ax[1].set(title="NEW sector: EV charging, learned from 1 day", xlabel="minutes ahead")
    ax[1].legend(frameon=False)
    w = np.linspace(0, 2, 50)
    for name, c in zip(interp, ["#3ddc84", "#5aa9ff", "#f2a541", "#f06a6a"]):
        sec = SECTORS[name]; s = float(np.mean(sec["servers"])); m, z_new = ensemble[0]
        q = torch.tensor(w * sec["patience"] * sec["mu"] * s, dtype=torch.float32)
        lam = torch.full_like(q, sec["mu"] * s); mus = lam.clone()
        z = z_new if name == NEW_SECTOR else m.z(torch.tensor([TRAIN_SECTORS.index(name)]))
        with torch.no_grad():
            ax[2].plot(w, m.leave_prob(q, lam, mus, z.expand(len(q), -1)), color=c, lw=2, label=f"{name} learned")
        ax[2].plot(w, true_hazard(q.numpy(), sec["mu"], s, sec["patience"]), color=c, ls=":", lw=1.2)
    ax[2].set(title="What the network learned: chance of leaving / min\n(solid = learned, dotted = truth)",
              xlabel="expected wait / patience")
    ax[2].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "results.png", dpi=130)


if __name__ == "__main__":
    main()
