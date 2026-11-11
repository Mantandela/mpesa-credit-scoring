"""Sensitivity run: do the conclusions depend on the scorecard weights or on the size of the hidden shock?

Run from the repo root, after scorecard.py:
    python src/sensitivity.py                 all variants in VARIANTS below
    python src/sensitivity.py --quick

The transactions and features do not depend on the weights, so for each variant this script only redraws the labels for the SAME
applications (scorecard.draw_default), trains the models (src/train_models.py) and records the results. Fuliza lateness is read from
the transactions, so it does not change between variants (only the default draw and the status that depends on it do).

Variants: the four weight sets in config.WEIGHT_SETS at the main shock coefficient, and the main weights at the other shock levels.
The shock coefficient controls how much of default the statements cannot explain (larger = harder to predict).
Each result is reported next to the best possible AUC (the scorecard probability itself) and the visible scorecard with no fitting.

Writes docs/sensitivity_report.md, docs/figures/sensitivity.png and per-variant files under data/processed/sensitivity/.
"""
import argparse
import json
import os
import subprocess
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from outcomes import best_possible_auc  # noqa: E402
from scorecard import draw_default  # noqa: E402

MODELS = ("logistic", "random_forest", "xgboost")
BASE = ("scorecard_baseline", "rule_baseline")


def variants():
    v = [(f"{w}, shock {C.SHOCK_COEF}", w, C.SHOCK_COEF) for w in C.WEIGHT_SETS]
    v += [(f"{C.MAIN_WEIGHTS}, shock {s}", C.MAIN_WEIGHTS, s) for s in C.SHOCK_COEF_LEVELS if s != C.SHOCK_COEF]
    return v


def md(rows, cols):
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(f"{r[c]:.3f}" if isinstance(r[c], (float, np.floating)) else str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/features.parquet")
    ap.add_argument("--columns", default="data/processed/feature_columns.json")
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--out-root", default="data/processed/sensitivity")
    ap.add_argument("--report", default="docs/sensitivity_report.md")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()

    feat = pd.read_parquet(a.features)
    cols = json.load(open(a.columns))
    os.makedirs(a.out_root, exist_ok=True)
    here = os.path.dirname(os.path.abspath(__file__))
    rows, summ = [], {}
    for k, (label, wname, shock) in enumerate(variants()):
        tag = f"v{k}"
        new = draw_default(feat, C.WEIGHT_SETS[wname], shock, a.seed)
        ceil = best_possible_auc(new)
        fpath = os.path.join(a.out_root, f"features_{tag}.parquet")
        new.to_parquet(fpath, index=False)
        sjson = os.path.join(a.out_root, f"summary_{tag}.json")
        cmd = [sys.executable, os.path.join(here, "train_models.py"), "--features", fpath, "--columns", a.columns,
               "--out", os.path.join(a.out_root, tag), "--models-dir", os.path.join("models", f"sens_{tag}"),
               "--report", os.path.join("docs", f"model_report_{tag}.md"), "--figure", os.path.join("docs", "figures", f"roc_{tag}.png"),
               "--summary-json", sjson, "--seed", str(a.seed)] + (["--quick"] if a.quick else [])
        print(f"\n=== {label}: training ...", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-1500:], r.stderr[-1500:])
            raise SystemExit(f"training failed for {label}")
        s = json.load(open(sjson))
        summ[label] = s
        rows.append({"label": label, "weights": wname, "shock": shock, "default_rate": float(new.defaulted.mean()),
                     "late": float((new.repayment_status == 1).mean()), **ceil})
        print(f"    best possible {ceil['oracle_auc']:.3f}; scorecard {s['test']['scorecard_baseline']['test AUC']:.3f}; " +
              ", ".join(f"{m} {s['test'][m]['test AUC']:.3f}" for m in MODELS), flush=True)

    L = ["# Sensitivity report: scorecard weights and hidden shock", "",
         f"{len(feat)} applications, {feat.vendor_id.nunique()} vendors, {len(cols['features'])} features, seed {a.seed}. Each variant redraws "
         "`defaulted` from a different scorecard (weights or shock size) for the same applications and retrains the models. All outcomes "
         "are simulated, so these numbers show how well the models recover simulated labels, not performance on real borrowers.", "",
         "Published cash-flow-only models reached AUCs of about 0.53 to 0.73 (CRA for FinRegLab, 2019), a useful reference for how "
         "predictable real defaults are.", "",
         "## 1. How predictable is default in each variant?", "",
         "Best possible AUC is the scorecard probability itself. Persona only is the AUC from knowing just the vendor's persona. "
         "Inside a persona is the best possible AUC among vendors of the same persona.", "",
         md([{"variant": r["label"], "default rate": r["default_rate"], "late share": r["late"], "best possible AUC": r["oracle_auc"],
              "persona only": r["persona_only_auc"], "inside a persona": r["within_persona_oracle_auc"]} for r in rows],
            ["variant", "default rate", "late share", "best possible AUC", "persona only", "inside a persona"]), "",
         "## 2. Test AUC with 95% interval (vendors never seen in training)", ""]
    t2 = []
    for r in rows:
        s = summ[r["label"]]
        row = {"variant": r["label"], "test defaults": f"{s['n_test_defaults']} of {s['n_test']}"}
        for m in MODELS + BASE:
            x = s["test"][m]
            row[m] = f"{x['test AUC']:.3f} ({x['test AUC 95% low']:.2f} to {x['test AUC 95% high']:.2f})"
        t2.append(row)
    L += [md(t2, ["variant", "test defaults", *MODELS, *BASE]), "",
          "`scorecard_baseline` is the visible scorecard (features and weights, no fitting). `rule_baseline` ranks only by near-zero-balance days.", "",
          "## 3. Cross-validated AUC (train and validation vendors, grouped by vendor)", "",
          "More applications than the test set, so less noisy. This is the main comparison between models.", "",
          md([{"variant": r["label"], **{m: summ[r["label"]]["oof_auc_train_val"][m] for m in MODELS}} for r in rows], ["variant", *MODELS]), "",
          "## 4. Share of the achievable gain captured", "",
          "(Cross-validated AUC - 0.5) divided by (best possible AUC - 0.5). 100% means the model matches the scorecard probability.", "",
          md([{"variant": r["label"], **{m: f"{(summ[r['label']]['oof_auc_train_val'][m] - 0.5) / (r['oracle_auc'] - 0.5):.0%}" for m in MODELS}}
              for r in rows], ["variant", *MODELS]), "",
          "## 5. Lender view: default rate among approved applicants when 80% are approved (test)", "",
          md([{"variant": r["label"], "no scoring": summ[r["label"]]["default_rate_test"],
               **{m: summ[r["label"]]["default_rate_among_approved_80"][m] for m in MODELS + BASE}} for r in rows],
             ["variant", "no scoring", *MODELS, *BASE]), "",
          "Per-variant detail is in docs/model_report_v<number>.md (numbers follow the order of the tables)."]
    os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
    open(a.report, "w", encoding="utf-8").write("\n".join(L) + "\n")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        os.makedirs("docs/figures", exist_ok=True)
        x = np.arange(len(rows))
        plt.figure(figsize=(9, 4.5))
        plt.plot(x, [r["oracle_auc"] for r in rows], "k-o", label="best possible")
        plt.plot(x, [r["persona_only_auc"] for r in rows], "k--o", label="persona only")
        plt.plot(x, [summ[r["label"]]["oof_auc_train_val"]["scorecard_baseline"] if "scorecard_baseline" in summ[r["label"]]["oof_auc_train_val"]
                     else summ[r["label"]]["test"]["scorecard_baseline"]["test AUC"] for r in rows], "g-s", label="visible scorecard (test)")
        for m in MODELS:
            plt.plot(x, [summ[r["label"]]["oof_auc_train_val"][m] for r in rows], "-o", label=m)
        plt.xticks(x, [r["label"] for r in rows], rotation=25, ha="right", fontsize=8)
        plt.ylabel("AUC"); plt.ylim(0.5, 1.0); plt.legend(fontsize=8); plt.tight_layout()
        plt.savefig("docs/figures/sensitivity.png", dpi=160); plt.close()
    except Exception as e:
        print("figure skipped:", e)
    print(f"\nwrote {a.report} and docs/figures/sensitivity.png")


if __name__ == "__main__":
    main()