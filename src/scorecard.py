"""Stage 4a: the cash-flow scorecard and the outcomes (docs/scorecard_mapping.md).

Run from the repo root, after generator.py, clean.py and features.py:
    python src/scorecard.py                      main weights (config.MAIN_WEIGHTS), writes the labels into features.parquet
    python src/scorecard.py --weights equal      another weight set from config.WEIGHT_SETS

How the outcomes are made
1. Each feature is turned into a z-score across applications (missing values = the median, so z = 0) and clipped to +/- 3.
   Multiplied by its direction (+1 raises risk, -1 lowers it), then averaged inside its pillar.
2. score = sum over pillars of (pillar weight x pillar average). This is the VISIBLE part of the scorecard, built only from features.
3. logit(p) = intercept + SCORECARD_SCALE x score + HIDDEN_RISK_COEF x z(latent_risk) + SHOCK_COEF x hidden_shock.
   The last two terms are things a statement cannot show. The intercept is set so the average p equals TARGET_DEFAULT_RATE.
4. defaulted ~ Bernoulli(p). The scorecard gives a probability, never the final say.
5. Fuliza lateness is read from the transactions after the application date (src/outcomes.py). repayment_status: 2 default,
   1 late, 0 on time. late_or_default = status >= 1.

The score, p, latent_risk and hidden_shock are saved as meta columns for checking. They are never model inputs.
All weights, directions and coefficients are author assumptions (config.py, docs/assumptions.md).
"""
import argparse
import json
import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from outcomes import TX_COLUMNS, best_possible_auc, fuliza_outcomes, repayment_status  # noqa: E402

LABEL_COLUMNS = ["scorecard_score", "scorecard_p", "hidden_shock", "latent_risk", "defaulted", "fuliza_n_draws", "fuliza_late",
                 "fuliza_max_lag_days", "window_complete", "repayment_status", "late_or_default"]


def pillar_scores(feat: pd.DataFrame) -> pd.DataFrame:
    """One column per pillar: average of direction x clipped z-score of its features."""
    out = {}
    for pillar, members in C.SCORECARD_PILLARS.items():
        cols = []
        for f, direction in members.items():
            if f not in feat.columns:
                raise SystemExit(f"scorecard feature missing from the features table: {f}")
            x = feat[f].astype(float)
            sd = x.std(ddof=0)
            z = (x - x.median()) / sd if sd and not np.isnan(sd) else x * 0.0
            cols.append(direction * z.fillna(0.0).clip(-C.SCORE_CLIP, C.SCORE_CLIP))
        out[pillar] = pd.concat(cols, axis=1).mean(axis=1)
    return pd.DataFrame(out, index=feat.index)


def visible_score(feat: pd.DataFrame, weights: dict) -> pd.Series:
    ps = pillar_scores(feat)
    if abs(sum(weights.values()) - 1) > 1e-9:
        raise SystemExit("pillar weights must sum to 1")
    return sum(w * ps[k] for k, w in weights.items())


def calibrate_intercept(lin: np.ndarray, target: float) -> float:
    lo, hi = -15.0, 15.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if (1 / (1 + np.exp(-(mid + lin)))).mean() > target:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def draw_default(feat: pd.DataFrame, weights: dict, shock_coef: float, seed: int, scale=C.SCORECARD_SCALE,
                 hidden_coef=C.HIDDEN_RISK_COEF, target=C.TARGET_DEFAULT_RATE) -> pd.DataFrame:
    """Returns a copy of feat with scorecard_score, scorecard_p, defaulted (and repayment_status if fuliza_late is present)."""
    score = visible_score(feat, weights)
    zr = (feat.latent_risk - feat.latent_risk.mean()) / feat.latent_risk.std(ddof=0)
    lin = (scale * score + hidden_coef * zr + shock_coef * feat.hidden_shock).to_numpy()
    p = 1 / (1 + np.exp(-(calibrate_intercept(lin, target) + lin)))
    rng = np.random.default_rng([int(seed), 11])
    out = feat.copy()
    out["scorecard_score"], out["scorecard_p"] = score.to_numpy(), p
    out["defaulted"] = (rng.random(len(out)) < p).astype(int)
    if "fuliza_late" in out:
        out["repayment_status"] = repayment_status(out.defaulted, out.fuliza_late)
        out["late_or_default"] = (out.repayment_status >= 1).astype(int)
    return out


def read_clean_fuliza(path: str, apps: pd.DataFrame) -> pd.DataFrame:
    """Fuliza outcomes, reading the cleaned file one parquet row group (a block of whole vendors) at a time."""
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    parts = []
    for i in range(pf.num_row_groups):
        tx = pf.read_row_group(i, columns=TX_COLUMNS).to_pandas()
        tx["completion_time"] = pd.to_datetime(tx["completion_time"])
        sub = apps[apps.vendor_id.isin(tx.vendor_id.unique())]
        if len(sub):
            parts.append(fuliza_outcomes(tx, sub))
        print(f"  fuliza outcomes: chunk {i + 1}/{pf.num_row_groups}", flush=True)
    return pd.concat(parts, ignore_index=True)


def report(df: pd.DataFrame, feats: list, weights_name: str, ceil: dict, shock_coef: float) -> str:
    from sklearn.metrics import roc_auc_score
    L = ["# Scorecard and outcome report", "",
         f"{len(df):,} applications, {df.vendor_id.nunique()} vendors. Weight set `{weights_name}`, shock coefficient {shock_coef}, "
         f"scale {C.SCORECARD_SCALE}, hidden risk coefficient {C.HIDDEN_RISK_COEF}. All outcomes are simulated.", "",
         "## Outcome shares", "",
         "| outcome | share |", "|---|---|",
         f"| defaulted (class 2) | {df.defaulted.mean():.1%} |",
         f"| late, not defaulted (class 1) | {(df.repayment_status == 1).mean():.1%} |",
         f"| on time (class 0) | {(df.repayment_status == 0).mean():.1%} |", "",
         f"Applications with at least one Fuliza draw in the counting window: {(df.fuliza_n_draws > 0).mean():.1%}. "
         f"Applications with a complete {C.OBS_WINDOW_DAYS}-day window: {df.window_complete.mean():.1%}.", "",
         "## By persona", "", "| persona | applications | default | late | on time | mean p |", "|---|---|---|---|---|---|"]
    for ps, g in df.groupby("persona"):
        L.append(f"| {ps} | {len(g)} | {g.defaulted.mean():.1%} | {(g.repayment_status == 1).mean():.1%} | "
                 f"{(g.repayment_status == 0).mean():.1%} | {g.scorecard_p.mean():.3f} |")
    L += ["", "## How predictable is default?", "",
          f"- Best possible AUC (the scorecard probability itself): {ceil['oracle_auc']:.3f}",
          f"- Persona only: {ceil['persona_only_auc']:.3f}",
          f"- Inside a persona (average): {ceil['within_persona_oracle_auc']:.3f}",
          f"- Visible score only (features, no hidden terms) against default: {roc_auc_score(df.defaulted, df.scorecard_score):.3f}",
          "",
          "For scale: published cash-flow-only models reached AUCs of about 0.53 to 0.73 (CRA for FinRegLab, 2019).", "",
          "## Do default and Fuliza lateness move together?", "",
          f"- Late share among defaulters: {(df[df.defaulted == 1].fuliza_late).mean():.1%}",
          f"- Late share among non-defaulters: {(df[df.defaulted == 0].fuliza_late).mean():.1%}",
          f"- AUC of `fuliza_late` as a predictor of default: "
          f"{roc_auc_score(df.defaulted, df.fuliza_late):.3f}", "",
          "## Pillar scores against default (AUC, above 0.5 = higher score, more default)", ""]
    ps = pillar_scores(df)
    for k in ps.columns:
        L.append(f"- {k}: {roc_auc_score(df.defaulted, ps[k]):.3f}")
    L += ["", "## Single features with the strongest signal against default", ""]
    a = {f: roc_auc_score(df.defaulted, df[f].fillna(df[f].median())) for f in feats if df[f].nunique() > 1}
    top = sorted(a.items(), key=lambda t: -abs(t[1] - 0.5))[:10]
    L += [f"- {k}: {v:.3f}" for k, v in top]
    L += ["", "Single-feature AUCs above about 0.85 would suggest the label leaks into the features."]
    # transparency check: does the raw association agree with the direction fixed in advance? Directions are NOT changed to fit.
    dis = []
    for pillar, members in C.SCORECARD_PILLARS.items():
        for f, direction in members.items():
            x = df[f].fillna(df[f].median())
            if x.nunique() > 1 and (roc_auc_score(df.defaulted, x) - 0.5) * direction <= 0:
                dis.append(f"{f} ({pillar[0]}, set to {'+' if direction > 0 else '-'}1, raw AUC {roc_auc_score(df.defaulted, x):.3f})")
    L += ["", "## Directions that disagree with the raw association", "",
          "Directions were fixed from lending logic before any results (docs/scorecard_mapping.md) and are not tuned to the data. "
          "A disagreement means the feature's raw link to default is opposite to its assumed direction, usually because of persona "
          "structure in the simulated statements. It is a limitation to report, not something to fix by changing the direction.", ""]
    L += [f"- {x}" for x in dis] or ["- none"]
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/features.parquet")
    ap.add_argument("--columns", default="data/processed/feature_columns.json")
    ap.add_argument("--clean", default="data/interim")
    ap.add_argument("--dir", default="data/synthetic")
    ap.add_argument("--weights", default=C.MAIN_WEIGHTS, choices=list(C.WEIGHT_SETS))
    ap.add_argument("--shock-coef", type=float, default=C.SHOCK_COEF)
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--report", default="docs/scorecard_report.md")
    a = ap.parse_args()

    feat = pd.read_parquet(a.features)
    cols = json.load(open(a.columns))
    feats = cols["features"]
    feat = feat.drop(columns=[c for c in LABEL_COLUMNS if c in feat.columns])
    ext = (lambda n: pd.read_parquet(os.path.join(a.dir, n + ".parquet")))
    apps, ve = ext("loan_applications"), ext("vendors")
    feat = feat.merge(apps[["application_id", "hidden_shock"]], on="application_id", how="left")
    feat = feat.merge(ve[["vendor_id", "latent_risk"]], on="vendor_id", how="left")

    src = os.path.join(a.clean, "transactions_clean.parquet")
    apps_d = apps[["application_id", "vendor_id", "application_date"]].copy()
    apps_d["application_date"] = pd.to_datetime(apps_d.application_date)
    fo = read_clean_fuliza(src, apps_d)
    feat = feat.merge(fo, on="application_id", how="left")

    out = draw_default(feat, C.WEIGHT_SETS[a.weights], a.shock_coef, a.seed)
    ceil = best_possible_auc(out)
    meta = [c for c in cols["meta"] if c not in LABEL_COLUMNS] + LABEL_COLUMNS
    out = out[meta + feats]
    out.to_parquet(a.features, index=False)
    with open(a.columns, "w") as f:
        json.dump({"features": feats, "meta": meta}, f, indent=2)
    txt = report(out, feats, a.weights, ceil, a.shock_coef)
    os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
    open(a.report, "w", encoding="utf-8").write(txt)
    print(txt)
    print(f"wrote {a.features}, {a.columns}, {a.report}")


if __name__ == "__main__":
    main()