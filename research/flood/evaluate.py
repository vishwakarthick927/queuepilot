"""12-storm evaluation of the whole twin (water -> people -> queues). Writes evac_results.json.
Three ways to run the city on the SAME 12 storms:
  today              leave when water is in the street, shortest road that is dry now, nearest shelter
  physics forecast   QueuePilot decisions, but forecast with physics only (drains assumed perfect)
  physics + AI       QueuePilot decisions with the physics-guided neural forecast (ours)
Run: .venv/Scripts/python -m research.flood.evaluate
"""
import json
from pathlib import Path

import numpy as np
import torch

from research.flood import twin as T
from research.flood import water as W

OUT = Path(__file__).parent


def forecasts(frames, rain, eff):
    rt = torch.tensor(rain, dtype=torch.float32)
    out = []
    for t in range(T.STEPS):
        if t % 3:
            out.append(None); continue
        h0 = torch.tensor(frames[t - 1] if t > 0 else np.zeros((W.NY, W.NX)), dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            hs = W.run(h0, rt[t:t + 36].unsqueeze(0), eff.unsqueeze(0))[0].numpy()
        when = np.full((W.NY, W.NX), 999.0)
        for k in range(len(hs) - 1, -1, -1):
            when[hs[k] >= W.FLOOD_M] = k
        out.append(when)
    return out


def main():
    ai = torch.tensor(np.load(OUT / "eff_learned.npy"), dtype=torch.float32)
    setups = {"Today (react when water arrives)": ("today", None),
              "Physics forecast only": ("queuepilot", torch.ones(W.NY, W.NX)),
              "Physics + AI forecast (ours)": ("queuepilot", ai)}
    totals = {k: {} for k in setups}
    for seed in range(100, 112):
        rain = W.storm(seed, T.STEPS)
        frames = W.truth_run(rain).numpy()
        zones, shelters = T.pick_zones_and_shelters(frames)
        for name, (policy, eff) in setups.items():
            fcs = forecasts(frames, rain, eff) if eff is not None else [None] * T.STEPS
            _, m = T.evacuate(policy, frames, fcs, zones, shelters)
            for k, v in m.items():
                if v is not None:
                    totals[name].setdefault(k, []).append(v)
    summary = {name: {"people_in_flooding_areas": int(sum(m["people_in_flooding_areas"])),
                      "people_trapped": int(sum(m["people_trapped"])),
                      "needless_evacuations": int(sum(m["needless_evacuations"])),
                      "worst_shelter_wait_min": round(float(np.mean(m["max_shelter_wait_min"])), 1),
                      "first_departure_after_min": round(float(np.mean(m.get("first_departure_min", [0]))), 0)}
               for name, m in totals.items()}
    summary["setup"] = {"storms": 12, "assumption": "rain for the next 3 hours is known (weather-radar nowcast)"}
    (OUT / "evac_results.json").write_text(json.dumps(summary, indent=2))
    for k, v in summary.items():
        print(k, v)


if __name__ == "__main__":
    main()
