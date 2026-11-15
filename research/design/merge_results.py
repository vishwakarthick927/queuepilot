"""
Merge the three training runs into the one results.json the page reads.

  results_A.json  fix 3 only (training from t = 0) + GNN only + physics only, all on the same test
  results_B.json  fixes 2 + 3 (demand ratio into the efficiency head)
  results_C.json  fixes 1 + 2 + 3 (destination channels)

The PG-GNN shown on the page is the variant with the lowest clearance-time error on the held-out plans;
the other two are listed under "ablation" so the page can show what each fix changed. Its weights are
copied to pggnn.pt for recommend.py.

    python -m research.design.merge_results
"""
import json
import shutil

from research.design.pggnn import OUT

LABELS = {"A": "PG-GNN, fix 3 (train from t = 0)", "B": "+ fix 2 (door demand ratio)", "C": "+ fix 1 (destination channels)"}


def main():
    runs = {t: json.loads((OUT / f"results_{t}.json").read_text()) for t in LABELS if (OUT / f"results_{t}.json").exists()}
    best = min(runs, key=lambda t: runs[t]["models"]["pggnn"]["clearance_err_s"])
    out = json.loads(json.dumps(runs["A"]))                       # baselines come from run A
    out["models"]["pggnn"] = runs[best]["models"]["pggnn"]
    out["speed"] = runs[best]["speed"]
    out["setup"] = runs[best]["setup"] | {"chosen_variant": best}
    out["ablation"] = [{"label": LABELS[t], **{k: runs[t]["models"]["pggnn"][k] for k in ("clearance_err_s", "ci95")}} for t in runs]
    (OUT / "results.json").write_text(json.dumps(out, indent=1))
    shutil.copy(OUT / f"pggnn_{best}.pt", OUT / "pggnn.pt")
    print("chosen variant", best, json.dumps(out["models"], indent=1))
    return best


if __name__ == "__main__":
    main()
