"""
Overflow Radar: predict how many people will be waiting in each ER 30 minutes from now.

Three forecasters, trained and tested on the same data (research/golden/radar_data.json):
  physics  = conservation of patients: waiting + on the way - what the doctors can clear in 30 min
  AI only  = a neural network that sees the same numbers, no physics
  ours     = physics + a neural network that adds ONLY the two things physics cannot know:
               new_arrivals >= 0   patients not yet called in who will be waiting (surges)
               relief in [0, 1]    share of the physics backlog that clears faster than average
             forecast = physics - relief * physics + new_arrivals   (never negative, by design)
This is the residual model of Yu & Wang (PNAS 2024, Sec 3A) with physical constraints on the
learned part, which the paper says is needed (Sec 3A) but leaves open for guarantees (Sec 4B).

Tests: (1) new days never seen, (2) a HOSPITAL never seen in training (Sec 4A generalisation).
Run from repo root:  .venv/Scripts/python research/golden/train_radar.py
"""
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

HERE = Path(__file__).parent
WEIGHTS = HERE.parent.parent / "frontend" / "src" / "golden" / "radar_weights.json"
MINUTES, AHEAD, TREAT = 360, 30, 25
torch.manual_seed(0)

d = np.array(json.loads((HERE / "radar_data.json").read_text()), dtype=np.float32)
day, hosp, t, waiting, busy, inbound, doctors, arrived30, calls15, target = d.T


def physics(waiting, busy, inbound, doctors):
    """People who will still be waiting: everyone waiting or on the way, minus the free doctors
    now, minus what all doctors can start in the next 30 minutes."""
    return np.maximum(0, waiting + inbound - (doctors - busy) - doctors * AHEAD / TREAT)


# what the network sees (all things a control room knows right now), scaled to about 0..1
X = np.stack([waiting / 10, busy / 6, inbound / 10, doctors / 6, arrived30 / 10, calls15 / 10,
              np.sin(np.pi * t / MINUTES), np.cos(np.pi * t / MINUTES)], 1).astype(np.float32)
P = physics(waiting, busy, inbound, doctors).astype(np.float32)


class Net(nn.Module):
    def __init__(self, hybrid):
        super().__init__()
        self.hybrid = hybrid
        self.mlp = nn.Sequential(nn.Linear(8, 32), nn.Tanh(), nn.Linear(32, 32), nn.Tanh(), nn.Linear(32, 2))

    def forward(self, x, p):
        o = self.mlp(x)
        if not self.hybrid:                       # AI only: predicts the queue directly
            return nn.functional.softplus(o[:, 0]) * 10
        new_arrivals = nn.functional.softplus(o[:, 0]) * 5
        relief = torch.sigmoid(o[:, 1])
        return p - relief * p + new_arrivals


def train(mask, hybrid, epochs=25):
    net = Net(hybrid)
    x, p, y = map(torch.tensor, (X[mask], P[mask], target[mask]))
    opt = torch.optim.Adam(net.parameters(), lr=3e-3)
    for _ in range(epochs):
        for idx in torch.randperm(len(x)).split(2048):
            loss = ((net(x[idx], p[idx]) - y[idx]) ** 2).mean()
            opt.zero_grad(); loss.backward(); opt.step()
    return net


@torch.no_grad()
def scores(net, mask):
    y = target[mask]
    pred = P[mask] if net is None else net(torch.tensor(X[mask]), torch.tensor(P[mask])).numpy()
    busy_rows = y >= 8                                 # the moments that matter: an ER filling up
    return {"all": round(float(np.abs(pred - y).mean()), 2),
            "ER_filling_up": round(float(np.abs(pred - y)[busy_rows].mean()), 2),
            "negative_predictions": int((pred < -1e-6).sum())}


results = {}
tests = {
    "new days": (day < 900, day >= 1050),
    "hospital never seen (Ring Road)": ((day < 900) & (hosp != 5), (day >= 1050) & (hosp == 5)),
}
nets = {}
for name, (tr, te) in tests.items():
    row = {"Physics only": scores(None, te)}
    for label, hybrid in [("AI only", False), ("Physics + AI (ours)", True)]:
        net = train(tr, hybrid)
        nets[(name, label)] = net
        row[label] = scores(net, te)
    results[name] = row
    print(f"\n{name}: average error, people waiting 30 min ahead")
    for k, v in row.items():
        print(f"  {k:22} all {v['all']:5.2f}   ER filling up {v['ER_filling_up']:5.2f}   negative {v['negative_predictions']}")

results["setup"] = {"rows": int(len(d)), "train_days": 900, "test_days": 150, "ahead_min": AHEAD}
(HERE / "radar_results.json").write_text(json.dumps(results, indent=2))

# export ours (trained on new-days split) for the browser
net = nets[("new days", "Physics + AI (ours)")]
layers = [m for m in net.mlp if isinstance(m, nn.Linear)]
WEIGHTS.write_text(json.dumps({
    "layers": [{"W": l.weight.detach().numpy().round(5).tolist(), "b": l.bias.detach().numpy().round(5).tolist()} for l in layers],
    "results": results,
}))
print("\nweights ->", WEIGHTS)
