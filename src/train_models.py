"""Stage 4: split by vendor and train the three models.

Run from the repo root:
    python src/train_models.py                    reads data/processed/features.parquet and feature_columns.json
    python src/train_models.py --seed 7           another random split
    python src/train_models.py --quick            smaller grids and fewer trees (for a fast check)

What it does
1. Splits VENDORS (not applications) 70/15/15 into train, validation and test, balanced by persona, so no vendor
   appears in two splits. A vendor can have up to four applications, so a split by application would leak.
2. Tunes each model on the training vendors only, with 5-fold cross-validation grouped by vendor.
3. Fits the best setting on train, uses the validation set to set the approval cutoff, and scores the test set once.
4. Compares: logistic regression, Random Forest, XGBoost and a one-feature rule baseline.

Writes: models/*.joblib, data/processed/predictions.parquet, docs/model_report.md, docs/figures/roc_test.png
Only the columns listed as "features" in feature_columns.json are model inputs. persona, gender, business_type,
and every outcome or hidden column (defaulted, repayment_status, scorecard_p, hidden_shock, ...) are never inputs.
They are kept in the predictions file for checks only.
"""
import argparse
import json
import os
import warnings
import joblib
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.base import clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import QuantileTransformer
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
SPLITS = (0.70, 0.15, 0.15)
APPROVAL_LEVELS = (0.70, 0.80, 0.90)


# ---------------------------------------------------------------- split
def split_vendors(feat: pd.DataFrame, seed: int) -> dict:
    """Assign each vendor to train, val or test. Balanced by persona. Returns {vendor_id: split}."""
    rng = np.random.default_rng(seed)
    assign = {}
    for _, g in feat.drop_duplicates("vendor_id").groupby("persona"):
        ids = g.vendor_id.to_numpy().copy()
        rng.shuffle(ids)
        n = len(ids)
        n_tr, n_va = int(round(SPLITS[0] * n)), int(round(SPLITS[1] * n))
        for i, v in enumerate(ids):
            assign[v] = "train" if i < n_tr else "val" if i < n_tr + n_va else "test"
    return assign


# ---------------------------------------------------------------- models
def make_model(name, **p):
    imp = SimpleImputer(strategy="median", add_indicator=True)
    if name == "logistic":
        return Pipeline([("imp", imp), ("q", QuantileTransformer(n_quantiles=100, output_distribution="normal", random_state=0)),
                         ("m", LogisticRegression(C=p.get("C", 0.1), max_iter=3000))])
    if name == "random_forest":
        return Pipeline([("imp", imp), ("m", RandomForestClassifier(
            n_estimators=p.get("n_estimators", 500), min_samples_leaf=p.get("min_samples_leaf", 5),
            max_features="sqrt", n_jobs=-1, random_state=0))])
    if name == "xgboost":                                    # handles missing values itself
        return XGBClassifier(n_estimators=p.get("n_estimators", 300), max_depth=p.get("max_depth", 3), learning_rate=0.05,
                             subsample=0.8, colsample_bytree=0.8, min_child_weight=2, eval_metric="logloss",
                             tree_method="hist", n_jobs=-1, random_state=0)
    raise ValueError(name)


def grids(quick):
    if quick:
        return {"logistic": [{"C": 0.1}], "random_forest": [{"min_samples_leaf": 5, "n_estimators": 200}],
                "xgboost": [{"max_depth": 3, "n_estimators": 150}]}
    return {"logistic": [{"C": c} for c in (0.01, 0.03, 0.1, 0.3, 1.0)],
            "random_forest": [{"min_samples_leaf": m} for m in (3, 5, 10)],
            "xgboost": [{"max_depth": d, "n_estimators": n} for d, n in ((2, 200), (3, 200), (3, 400))]}


def proba(model, X):
    return model.predict_proba(X)[:, 1]


def cv_auc(name, params, X, y, groups, seed):
    skf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    s = []
    for tr, te in skf.split(X, y, groups):
        m = make_model(name, **params).fit(X.iloc[tr], y.iloc[tr])
        s.append(roc_auc_score(y.iloc[te], proba(m, X.iloc[te])))
    return float(np.mean(s)), float(np.std(s))


def oof_predictions(name, params, X, y, groups, seed):
    out = np.zeros(len(y))
    skf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=seed)
    for tr, te in skf.split(X, y, groups):
        out[te] = proba(make_model(name, **params).fit(X.iloc[tr], y.iloc[tr]), X.iloc[te])
    return out


# ---------------------------------------------------------------- metrics
def ks_stat(y, p):
    return float(ks_2samp(p[y == 1], p[y == 0]).statistic)


def bad_rate_at(y, p, cutoff):
    approved = p <= cutoff
    return float(approved.mean()), (float(y[approved].mean()) if approved.any() else np.nan)


def metrics(y, p):
    y = np.asarray(y)
    return {"AUC": roc_auc_score(y, p), "PR-AUC": average_precision_score(y, p), "KS": ks_stat(y, p),
            "Brier": brier_score_loss(y, np.clip(p, 0, 1))}


def bootstrap_auc(y, p, vendors, n=1000, seed=0):
    """95% interval for AUC, resampling vendors (all their applications together)."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"y": y, "p": p, "v": vendors})
    by = {v: g for v, g in df.groupby("v")}
    ids = np.array(list(by))
    vals = []
    for _ in range(n):
        d = pd.concat([by[v] for v in rng.choice(ids, len(ids))])
        if 0 < d.y.sum() < len(d):
            vals.append(roc_auc_score(d.y, d.p))
    return tuple(np.percentile(vals, [2.5, 97.5]))


def md_table(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(f"{v:.3f}" if isinstance(v, (float, np.floating)) else str(v) for v in r) + " |")
    return "\n".join(out)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/features.parquet")
    ap.add_argument("--columns", default="data/processed/feature_columns.json")
    ap.add_argument("--out", default="data/processed")
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--report", default="docs/model_report.md")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--figure", default="docs/figures/roc_test.png")
    ap.add_argument("--summary-json", default=None, help="also write the key numbers to this json file")
    a = ap.parse_args()

    feat = pd.read_parquet(a.features) if a.features.endswith(".parquet") else pd.read_csv(a.features)
    cols = json.load(open(a.columns))
    F = cols["features"]
    banned = {"persona", "latent_risk", "txn_type_true", "gender", "business_type", "defaulted", "days_past_due", "late_or_default",
              "repayment_status", "scorecard_p", "scorecard_score", "hidden_shock", "fuliza_late", "fuliza_n_draws",
              "fuliza_max_lag_days", "window_complete"}
    assert not banned & set(F), f"banned columns in features: {banned & set(F)}"

    assign = split_vendors(feat, a.seed)
    feat["split"] = feat.vendor_id.map(assign)
    assert not (feat.groupby("vendor_id").split.nunique() > 1).any(), "a vendor is in two splits"
    tr, va, te = (feat[feat.split == s] for s in ("train", "val", "test"))
    split_tbl = pd.DataFrame([{"split": s, "vendors": d.vendor_id.nunique(), "applications": len(d),
                               "defaults": int(d.defaulted.sum()), "default_rate": d.defaulted.mean()}
                              for s, d in (("train", tr), ("val", va), ("test", te))])
    print(split_tbl.to_string(index=False), "\n")

    Xtr, ytr, gtr = tr[F], tr.defaulted.astype(int), tr.vendor_id
    Xva, yva = va[F], va.defaulted.astype(int).to_numpy()
    Xte, yte = te[F], te.defaulted.astype(int).to_numpy()

    # ---- tune on train only
    best, fitted, tune_rows = {}, {}, []
    for name, grid in grids(a.quick).items():
        scored = [(cv_auc(name, p, Xtr, ytr, gtr, a.seed), p) for p in grid]
        (m, s), p = max(scored, key=lambda t: t[0][0])
        best[name] = p
        tune_rows.append({"model": name, "best_settings": str(p), "cv_auc_mean": m, "cv_auc_sd": s})
        fitted[name] = make_model(name, **p).fit(Xtr, ytr)
        print(f"{name}: best {p}  CV AUC {m:.3f} +/- {s:.3f}")

    # ---- score validation and test
    P_va = {n: proba(m, Xva) for n, m in fitted.items()}
    P_te = {n: proba(m, Xte) for n, m in fitted.items()}
    # rule baseline: more near-zero-balance days = riskier. No fitting.
    base_col = "near_zero_day_share_90"
    fill = float(tr[base_col].median())
    P_va["rule_baseline"] = va[base_col].fillna(fill).to_numpy()
    P_te["rule_baseline"] = te[base_col].fillna(fill).to_numpy()

    names = ["logistic", "random_forest", "xgboost", "rule_baseline"]
    if "scorecard_score" in feat.columns:              # the visible scorecard, with no fitting: the baseline to beat
        P_va["scorecard_baseline"] = va.scorecard_score.to_numpy()
        P_te["scorecard_baseline"] = te.scorecard_score.to_numpy()
        names.append("scorecard_baseline")
    rows = []
    for n in names:
        mva, mte = metrics(yva, P_va[n]), metrics(yte, P_te[n])
        lo, hi = bootstrap_auc(yte, P_te[n], te.vendor_id.to_numpy(), n=300 if a.quick else 1000)
        rows.append({"model": n, "val AUC": mva["AUC"], "test AUC": mte["AUC"], "test AUC 95% low": lo, "test AUC 95% high": hi,
                     "test PR-AUC": mte["PR-AUC"], "test KS": mte["KS"],
                     "test Brier": mte["Brier"] if n not in ("rule_baseline", "scorecard_baseline") else np.nan})
    res = pd.DataFrame(rows)
    print("\n", res.round(3).to_string(index=False))

    # ---- lender view: cutoff set on validation, applied to test
    lend = []
    for n in names:
        for r in APPROVAL_LEVELS:
            cutoff = float(np.quantile(P_va[n], r))
            ar, br = bad_rate_at(yte, P_te[n], cutoff)
            lend.append({"model": n, "approval target": f"{r:.0%}", "actual approval on test": ar, "default rate among approved": br})
    lend = pd.DataFrame(lend)

    # ---- do the models separate vendors inside each persona? (out-of-fold on train+val)
    dev = pd.concat([tr, va])
    Xd, yd, gd = dev[F], dev.defaulted.astype(int), dev.vendor_id
    oof = {n: oof_predictions(n, best[n], Xd, yd, gd, a.seed) for n in ("logistic", "random_forest", "xgboost")}
    pers = []
    for ps, g in dev.groupby("persona"):
        row = {"persona": ps, "applications": len(g), "default_rate": g.defaulted.mean()}
        idx = np.where(dev.persona.to_numpy() == ps)[0]
        for n in oof:
            yy = yd.to_numpy()[idx]
            row[n] = roc_auc_score(yy, oof[n][idx]) if 0 < yy.sum() < len(yy) else np.nan
        pers.append(row)
    pers = pd.DataFrame(pers)
    overall_oof = {n: roc_auc_score(yd, oof[n]) for n in oof}

    # ---- importance
    xgb = fitted["xgboost"]
    imp_x = pd.Series(xgb.feature_importances_, index=F).sort_values(ascending=False).head(12)
    lr = fitted["logistic"]
    names_lr = list(F) + [f"{F[i]} (missing flag)" for i in lr.named_steps["imp"].indicator_.features_]
    coef = pd.Series(lr.named_steps["m"].coef_[0], index=names_lr)
    coef = coef.reindex(coef.abs().sort_values(ascending=False).index).head(12)

    # ---- save
    os.makedirs(a.out, exist_ok=True)
    os.makedirs(a.models_dir, exist_ok=True)
    for n, m in fitted.items():
        joblib.dump({"model": m, "features": F, "settings": best[n], "seed": a.seed}, os.path.join(a.models_dir, f"{n}.joblib"))
    keep = [c for c in ("application_id", "vendor_id", "split", "defaulted", "repayment_status", "late_or_default", "persona",
                        "gender", "business_type", "scorecard_p") if c in feat.columns]
    pred = feat[keep].copy()
    for n, m in fitted.items():
        pred[f"p_{n}"] = proba(m, feat[F])
    pred.to_parquet(os.path.join(a.out, "predictions.parquet"), index=False)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        os.makedirs(os.path.dirname(a.figure) or ".", exist_ok=True)
        plt.figure(figsize=(5.5, 5))
        for n in names:
            fpr, tpr, _ = roc_curve(yte, P_te[n])
            plt.plot(fpr, tpr, label=f"{n} (AUC {roc_auc_score(yte, P_te[n]):.2f})")
        plt.plot([0, 1], [0, 1], "k:", lw=1)
        plt.xlabel("False positive rate"); plt.ylabel("True positive rate"); plt.title("ROC on test vendors")
        plt.legend(loc="lower right", fontsize=8); plt.tight_layout()
        plt.savefig(a.figure, dpi=160); plt.close()
    except Exception as e:
        print("figure skipped:", e)

    # ---- report
    few = int(te.defaulted.sum()) < 15
    L = ["# Model report", "",
         f"Seed {a.seed}. Split by vendor, balanced by persona. {len(F)} features. Labels are simulated (see assumptions.md), so "
         "these numbers describe how well the models recover the synthetic outcome, not performance on real borrowers.", "",
         "## Split", "", md_table(split_tbl), ""]
    if few:
        L += [f"**Warning:** the test set has only {int(te.defaulted.sum())} defaults, so test results are noisy. Read the intervals and the cross-validated figures.", ""]
    L += ["## Tuning (train vendors only, 5-fold CV grouped by vendor)", "", md_table(pd.DataFrame(tune_rows)), "",
          "## Results", "", md_table(res), "",
          "Intervals come from resampling test vendors 1,000 times. `rule_baseline` ranks vendors by share of near-zero-balance days "
          "with no fitting. `scorecard_baseline` is the visible cash-flow scorecard (features and weights only, no hidden terms), also with no "
          "fitting. A model should beat both clearly to justify its complexity.", "",
          "## Lender view: default rate among approved applicants (test)", "",
          "The cutoff is set on the validation set so that the target share is approved, then applied to the test set. "
          f"Default rate with no scoring on test: {yte.mean():.1%}.", "", md_table(lend), "",
          "## Inside each persona (out-of-fold AUC on train + validation)", "",
          "If the models only recognised which persona a vendor belongs to, these numbers would sit near 0.5. "
          f"Overall out-of-fold AUC: logistic {overall_oof['logistic']:.3f}, random forest {overall_oof['random_forest']:.3f}, xgboost {overall_oof['xgboost']:.3f}.", "",
          md_table(pers), "",
          "## What the models use", "", "XGBoost importance (gain, top 12):", "",
          "\n".join(f"- {k}: {v:.3f}" for k, v in imp_x.items()), "",
          "Logistic regression coefficients (inputs are rank-normalised, so sizes are comparable; positive = higher risk):", "",
          "\n".join(f"- {k}: {v:+.2f}" for k, v in coef.items()), "",
          "Next: SHAP explanations, fairness check by gender, and the affordability simulation."]
    os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
    with open(a.report, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    if a.summary_json:
        summary = {
            "seed": a.seed, "n_test": int(len(te)), "n_test_defaults": int(te.defaulted.sum()),
            "default_rate_test": float(te.defaulted.mean()),
            "test": res.set_index("model")[["val AUC", "test AUC", "test AUC 95% low", "test AUC 95% high", "test PR-AUC", "test KS"]].to_dict("index"),
            "cv_auc_train": {r["model"]: {"mean": r["cv_auc_mean"], "sd": r["cv_auc_sd"]} for r in tune_rows},
            "oof_auc_train_val": overall_oof,
            "oof_within_persona": pers.set_index("persona")[["applications", "default_rate", "logistic", "random_forest", "xgboost"]].to_dict("index"),
            "default_rate_among_approved_80": {r["model"]: r["default rate among approved"]
                                              for _, r in lend[lend["approval target"] == "80%"].iterrows()},
        }
        with open(a.summary_json, "w") as f:
            json.dump(summary, f, indent=2, default=float)
    print(f"\nwrote {a.report}, {a.out}/predictions.parquet, {a.models_dir}/, {a.figure}")


if __name__ == "__main__":
    main()