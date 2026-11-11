"""Stage 4c: the three-class outcome (0 on time, 1 late, 2 default). Secondary target.

Run from the repo root, after scorecard.py:
    python src/train_multiclass.py               python src/train_multiclass.py --quick

Same vendor split as train_models.py (70/15/15 by vendor, balanced by persona). Fixed, modest model settings (no grid), because the
late class is small. Reports, on the test vendors: one-vs-rest AUC per class and macro average, accuracy, balanced accuracy,
macro F1, the confusion matrix and recall per class. Baseline: always predicting the most common class.
Class 1 (late) is read from Fuliza repayment after the application date, class 2 (default) comes from the scorecard.
"""
import argparse
import json
import os
import warnings
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import QuantileTransformer
from xgboost import XGBClassifier

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_models import md_table, split_vendors  # noqa: E402

warnings.filterwarnings("ignore")
CLASSES = ["on time", "late", "default"]


def make(name, quick):
    imp = SimpleImputer(strategy="median", add_indicator=True)
    if name == "logistic":
        return Pipeline([("imp", imp), ("q", QuantileTransformer(n_quantiles=100, output_distribution="normal", random_state=0)),
                         ("m", LogisticRegression(C=0.1, max_iter=3000))])
    if name == "random_forest":
        return Pipeline([("imp", imp), ("m", RandomForestClassifier(n_estimators=200 if quick else 500, min_samples_leaf=5,
                                                                    max_features="sqrt", n_jobs=-1, random_state=0))])
    return XGBClassifier(n_estimators=150 if quick else 300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                         min_child_weight=2, tree_method="hist", n_jobs=-1, random_state=0, eval_metric="mlogloss")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/features.parquet")
    ap.add_argument("--columns", default="data/processed/feature_columns.json")
    ap.add_argument("--report", default="docs/model_report_3class.md")
    ap.add_argument("--summary-json", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()

    feat = pd.read_parquet(a.features)
    F = json.load(open(a.columns))["features"]
    feat["split"] = feat.vendor_id.map(split_vendors(feat, a.seed))
    tr, te = feat[feat.split == "train"], feat[feat.split == "test"]
    ytr, yte = tr.repayment_status.astype(int).to_numpy(), te.repayment_status.astype(int).to_numpy()
    share = pd.DataFrame([{"split": s, "applications": len(d), **{c: int((d.repayment_status == k).sum()) for k, c in enumerate(CLASSES)}}
                          for s, d in (("train", tr), ("test", te))])

    rows, cms, per_class, summary = [], {}, [], {}
    majority = int(np.bincount(ytr).argmax())
    rows.append({"model": "majority class", "macro AUC": 0.5, "accuracy": float((yte == majority).mean()),
                 "balanced accuracy": 0.333, "macro F1": f1_score(yte, np.full(len(yte), majority), average="macro")})
    for name in ("logistic", "random_forest", "xgboost"):
        m = make(name, a.quick).fit(tr[F], ytr)
        P = m.predict_proba(te[F])
        pred = P.argmax(1)
        aucs = {c: roc_auc_score((yte == k).astype(int), P[:, k]) if 0 < (yte == k).sum() < len(yte) else np.nan
                for k, c in enumerate(CLASSES)}
        rows.append({"model": name, "macro AUC": float(np.nanmean(list(aucs.values()))), "accuracy": float((pred == yte).mean()),
                     "balanced accuracy": balanced_accuracy_score(yte, pred), "macro F1": f1_score(yte, pred, average="macro")})
        cm = confusion_matrix(yte, pred, labels=[0, 1, 2])
        cms[name] = cm
        per_class.append({"model": name, **{f"AUC {c}": v for c, v in aucs.items()},
                          **{f"recall {c}": cm[k, k] / max(cm[k].sum(), 1) for k, c in enumerate(CLASSES)}})
        summary[name] = {"macro_auc": rows[-1]["macro AUC"], "per_class_auc": aucs}
    res, pc = pd.DataFrame(rows), pd.DataFrame(per_class)
    print(share.to_string(index=False), "\n\n", res.round(3).to_string(index=False), "\n\n", pc.round(3).to_string(index=False))

    L = ["# Three-class model report (secondary target)", "",
         f"Classes: 0 on time, 1 late (a Fuliza draw unpaid past {30} days, not defaulted), 2 default (from the scorecard). Seed {a.seed}, "
         f"{len(F)} features, split by vendor. Outcomes are simulated, so these numbers describe recovery of the simulated labels.", "",
         "## Class counts", "", md_table(share), "",
         "## Results on test vendors", "", md_table(res), "",
         "Macro AUC is the average of the one-vs-rest AUCs. The late class is small, so its figures are noisy.", "",
         "## Per class", "", md_table(pc), ""]
    for n, cm in cms.items():
        L += [f"### Confusion matrix, {n} (rows actual, columns predicted)", "",
              "| actual \\ predicted | on time | late | default |", "|---|---|---|---|"]
        L += [f"| {CLASSES[i]} | {cm[i, 0]} | {cm[i, 1]} | {cm[i, 2]} |" for i in range(3)] + [""]
    os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
    open(a.report, "w", encoding="utf-8").write("\n".join(L) + "\n")
    if a.summary_json:
        json.dump(summary, open(a.summary_json, "w"), indent=2, default=float)
    print("wrote", a.report)


if __name__ == "__main__":
    main()