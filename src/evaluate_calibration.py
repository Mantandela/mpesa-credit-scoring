"""Calibration and uncertainty checks for the deployed logistic model. EVALUATION ONLY.

    python -m src.evaluate_calibration            (from the repo root; about a minute)

Nothing here retrains or changes the deployed model, the features, the score formula or the tier thresholds:
- the train/test split is train_models.split_vendors with the same seed (42), so the test vendors are the ones in
  docs/model_report.md (checked against data/processed/predictions.parquet);
- the test-set numbers come from the SAVED models (models/*.joblib), never a refit;
- the only fits are temporary: out-of-fold predictions on the TRAINING vendors (same 5-fold grouped CV as
  train_models) for a larger calibration sample, and a train-only bootstrap refit for the fuliza_late diagnostic.
  None of them is saved over a model file.

Outputs: reports/calibration/ (JSON summary, CSV tables, PNG figures at 200 dpi) and docs/calibration_report.md.
All outcomes are SIMULATED (see docs/assumptions.md): the numbers describe how well the model recovers the synthetic
outcome, not real-world performance.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold

try:                                       # python -m src.evaluate_calibration (repo root on the path)
    from src import scoring
    from src.train_models import ks_stat, make_model, oof_predictions, split_vendors
except ImportError:                        # imported as a plain module with src/ on the path (the tests)
    import scoring
    from train_models import ks_stat, make_model, oof_predictions, split_vendors

SEED = 42
N_BOOT = 2000
N_BOOT_COEF = 200
Z95 = float(stats.norm.ppf(0.975))
MODELS = ("logistic", "scorecard", "random_forest", "xgboost")
LABEL = {"logistic": "Logistic (deployed)", "scorecard": "Visible scorecard", "random_forest": "Random forest",
         "xgboost": "XGBoost"}


# ------------------------------------------------------------------ small statistics helpers (unit tested)
def wilson(k: int, n: int, z: float = Z95) -> tuple:
    """Wilson score interval for k successes in n trials. (nan, nan) when n is 0."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def brier_skill(y, p, p_ref: float) -> dict:
    """Brier score of p, of a constant predictor p_ref, and the skill score 1 - B / B_ref (1 perfect, 0 no better)."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    b = float(np.mean((p - y) ** 2))
    b_ref = float(np.mean((p_ref - y) ** 2))
    return {"brier": b, "brier_reference": b_ref, "reference_pd": float(p_ref),
            "brier_skill_score": float(1 - b / b_ref) if b_ref > 0 else float("nan")}


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _logistic_mle(X, y, offset=None, iters: int = 100):
    """Unpenalised logistic regression by Newton-Raphson: (coefficients, covariance)."""
    X, y = np.asarray(X, float), np.asarray(y, float)
    off = np.zeros(len(y)) if offset is None else np.asarray(offset, float)
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        mu = 1 / (1 + np.exp(-(X @ beta + off)))
        w = np.clip(mu * (1 - mu), 1e-12, None)
        info = X.T @ (X * w[:, None])
        step = np.linalg.solve(info, X.T @ (y - mu))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            break
    mu = 1 / (1 + np.exp(-(X @ beta + off)))
    info = X.T @ (X * np.clip(mu * (1 - mu), 1e-12, None)[:, None])
    return beta, np.linalg.inv(info)


def calibration_intercept_slope(y, p) -> dict:
    """Logistic regression of the outcome on logit(PD): intercept and slope (ideal 0 and 1) with 95% Wald intervals,
    plus calibration-in-the-large (the intercept with the slope fixed at 1, ideal 0: above 0 = the model predicts
    too little default overall, below 0 = too much)."""
    lp = logit(p)
    X = np.column_stack([np.ones(len(lp)), lp])
    b, cov = _logistic_mle(X, y)
    se = np.sqrt(np.diag(cov))
    a, cov1 = _logistic_mle(np.ones((len(lp), 1)), y, offset=lp)
    se1 = float(np.sqrt(cov1[0, 0]))
    return {"intercept": float(b[0]), "intercept_ci": [float(b[0] - Z95 * se[0]), float(b[0] + Z95 * se[0])],
            "slope": float(b[1]), "slope_ci": [float(b[1] - Z95 * se[1]), float(b[1] + Z95 * se[1])],
            "calibration_in_the_large": float(a[0]),
            "calibration_in_the_large_ci": [float(a[0] - Z95 * se1), float(a[0] + Z95 * se1)]}


def equal_count_bins(p, n_bins: int = 10) -> np.ndarray:
    """Bin index 0..n_bins-1 by rank of p (ties broken by order), so bins hold equal counts."""
    r = pd.Series(np.asarray(p, float)).rank(method="first").to_numpy()
    return np.minimum((r - 1) * n_bins // len(r), n_bins - 1).astype(int)


def decile_table(y, p, n_bins: int = 10) -> pd.DataFrame:
    y, p = np.asarray(y, int), np.asarray(p, float)
    b = equal_count_bins(p, n_bins)
    rows = []
    for i in range(n_bins):
        m = b == i
        n, k = int(m.sum()), int(y[m].sum())
        lo, hi = wilson(k, n)
        mp, obs = float(p[m].mean()), k / n
        rows.append({"decile": i + 1, "n": n, "defaults": k, "pd_min": float(p[m].min()), "pd_max": float(p[m].max()),
                     "mean_predicted_pd": mp, "observed_default_rate": obs, "wilson_low": lo, "wilson_high": hi,
                     "predicted_inside_interval": bool(lo <= mp <= hi)})
    return pd.DataFrame(rows)


def hosmer_lemeshow(y, p, n_groups: int = 10) -> dict:
    """Hosmer-Lemeshow statistic over equal-count groups, chi-square with n_groups - 2 degrees of freedom."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    b = equal_count_bins(p, n_groups)
    h = 0.0
    for i in range(n_groups):
        m = b == i
        n, o, e = m.sum(), y[m].sum(), p[m].sum()
        if 0 < e < n:
            h += (o - e) ** 2 / (e * (1 - e / n))
    df = n_groups - 2
    return {"statistic": float(h), "df": df, "p_value": float(stats.chi2.sf(h, df))}


def expected_calibration_error(y, p, n_bins: int = 10) -> float:
    """Weighted mean |mean predicted - observed| over equal-count bins."""
    y, p = np.asarray(y, float), np.asarray(p, float)
    b = equal_count_bins(p, n_bins)
    return float(sum((b == i).mean() * abs(p[b == i].mean() - y[b == i].mean()) for i in range(n_bins) if (b == i).any()))


def stratified_bootstrap_auc(y, scores: dict, n_boot: int = N_BOOT, seed: int = SEED) -> dict:
    """Paired percentile bootstrap of AUC, resampling defaults and non-defaults separately (so every resample keeps
    the test set's numbers of each). Every model is scored on the SAME resamples. Vectorised: AUC from average ranks
    (Mann-Whitney), which handles the ties that resampling creates. Returns {name: array of n_boot AUCs}."""
    y = np.asarray(y, int)
    pos, neg = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    n1, n0 = len(pos), len(neg)
    rng = np.random.default_rng(seed)
    idx = np.hstack([rng.choice(pos, (n_boot, n1)), rng.choice(neg, (n_boot, n0))])
    out = {}
    for name, s in scores.items():
        ranks = stats.rankdata(np.asarray(s, float)[idx], axis=1)
        out[name] = (ranks[:, :n1].sum(axis=1) - n1 * (n1 + 1) / 2) / (n1 * n0)
    return out


def percentile_interval(values) -> list:
    return [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))]


def vendor_bootstrap_auc(y, p, vendors, n_boot: int = N_BOOT, seed: int = SEED) -> list:
    """Percentile interval of AUC resampling VENDORS (all their applications together), as docs/model_report.md does.
    Wider than the row bootstrap because applications of one vendor are not independent."""
    df = pd.DataFrame({"y": np.asarray(y, int), "p": np.asarray(p, float), "v": np.asarray(vendors)})
    groups = [g for _, g in df.groupby("v")]
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        d = pd.concat([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        if 0 < d.y.sum() < len(d):
            vals.append(roc_auc_score(d.y, d.p))
    return percentile_interval(vals)


def score_formula(pd_values) -> np.ndarray:
    """The documented formula written out independently of scoring.pd_to_score:
    600 + 50 * log2(((1 - PD) / PD) / 5), rounded and clipped to 300-850."""
    p = np.asarray(pd_values, float)
    raw = 600 + 50 * np.log2(((1 - p) / p) / 5)
    return np.clip(np.rint(raw), 300, 850).astype(int)


def tier_bands() -> list:
    """[(name, lower PD, upper PD)] from scoring.TIER_BANDS (imported, never copied)."""
    out, lower = [], 0.0
    for upper, name in scoring.TIER_BANDS:
        out.append((name, lower, min(upper, 1.0)))
        lower = upper
    return out


def tier_table(y, p) -> pd.DataFrame:
    y, p = np.asarray(y, int), np.asarray(p, float)
    tiers = np.array([scoring.risk_tier(v) for v in p])                # the app's own rule
    rows = []
    for name, lo_b, hi_b in tier_bands():
        m = tiers == name
        n, k = int(m.sum()), int(y[m].sum())
        lo, hi = wilson(k, n)
        obs = k / n if n else float("nan")
        rows.append({"tier": name, "pd_band": f"{lo_b:.0%} to {hi_b:.0%}", "band_low": lo_b, "band_high": hi_b, "n": n,
                     "defaults": k, "mean_predicted_pd": float(p[m].mean()) if n else float("nan"),
                     "observed_default_rate": obs, "wilson_low": lo, "wilson_high": hi,
                     "observed_outside_band": bool(n and not (lo_b <= obs < hi_b)),
                     "interval_misses_band": bool(n and (hi < lo_b or lo >= hi_b))})
    return pd.DataFrame(rows)


def monotonic(tbl: pd.DataFrame) -> dict:
    """Observed default rate must RISE from Low to Very high risk (i.e. fall as the score rises)."""
    rates = [r for r in tbl.observed_default_rate if not math.isnan(r)]
    ok = all(a < b for a, b in zip(rates, rates[1:]))
    return {"rates_low_to_very_high": [float(r) for r in rates], "observed_rate_rises_with_tier": bool(ok),
            "empty_tiers": [t for t, n in zip(tbl.tier, tbl.n) if n == 0]}


def score_check(p) -> dict:
    """The formula reproduces scoring.pd_to_score; where each tier boundary PD lands on the score scale."""
    p = np.asarray(p, float)
    mine, theirs = score_formula(p), np.asarray(scoring.pd_to_score(p))
    bounds = []
    for upper, name in scoring.TIER_BANDS[:-1]:
        raw = 600 + 50 * math.log2(((1 - upper) / upper) / 5)
        rounded = int(scoring.pd_to_score(upper))
        just_below = int(scoring.pd_to_score(np.nextafter(upper, 0)))
        bounds.append({"pd": upper, "tier_below_pd": name, "score_exact": raw, "score_rounded": rounded,
                       "first_score_always_in_lower_risk_tier": math.floor(raw) + 1,
                       "rounded_score_shared_by_both_tiers": just_below == rounded})
    # tiers as the app assigns them (from PD) vs tiers read back from the integer score with the "first score always
    # in the lower-risk tier" cut-offs: they can differ only at the shared boundary scores
    cuts = [b["first_score_always_in_lower_risk_tier"] for b in bounds]
    names = [n for _, n in scoring.TIER_BANDS]
    from_score = [names[next((i for i, c in enumerate(cuts) if s >= c), len(cuts))] for s in theirs]
    from_pd = [scoring.risk_tier(v) for v in p]
    return {"n": int(len(p)), "formula_equals_pd_to_score": bool(np.array_equal(mine, theirs)),
            "max_abs_difference": int(np.max(np.abs(mine - theirs))) if len(p) else 0,
            "boundaries": bounds,
            "tier_from_pd_vs_tier_from_score_disagreements": int(sum(a != b for a, b in zip(from_pd, from_score)))}


def stability(y, p, repeats: int = 5, seed: int = SEED) -> dict:
    """AUC on both halves of `repeats` stratified random 50/50 splits of the test set."""
    y, p = np.asarray(y, int), np.asarray(p, float)
    aucs = []
    for r in range(repeats):
        for _, half in StratifiedKFold(n_splits=2, shuffle=True, random_state=seed + r).split(p, y):
            aucs.append(float(roc_auc_score(y[half], p[half])))
    return {"half_aucs": aucs, "mean": float(np.mean(aucs)), "min": float(np.min(aucs)), "max": float(np.max(aucs)),
            "half_size": int(len(y) // 2), "defaults_per_half": int(y.sum() // 2)}


def calibration_block(y, p, p_ref: float) -> dict:
    y, p = np.asarray(y, int), np.asarray(p, float)
    return {"n": int(len(y)), "defaults": int(y.sum()), "observed_default_rate": float(y.mean()),
            "mean_predicted_pd": float(p.mean()), **brier_skill(y, p, p_ref),
            "log_loss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6))), **calibration_intercept_slope(y, p),
            "hosmer_lemeshow": hosmer_lemeshow(y, p), "ece_10_equal_count": expected_calibration_error(y, p)}


# ------------------------------------------------------------------ fuliza_late diagnostic (temporary fits only)
def fuliza_diagnostic(tr, te, features, settings, n_boot: int = N_BOOT_COEF, seed: int = SEED) -> dict:
    """fuliza_late is a post-application OUTCOME (a Fuliza draw in the 60 days after the application unpaid after 30
    days), banned as a model input in train_models.py. Diagnostic only: its univariate AUC for default, and its
    coefficient when added to the logistic pipeline refitted on TRAIN rows (bootstrap). The refits are local objects,
    never saved; the deployed model has no fuliza_late coefficient."""
    yte = te.defaulted.astype(int).to_numpy()
    f_te = te.fuliza_late.astype(float).to_numpy()
    boot = stratified_bootstrap_auc(yte, {"fuliza_late": f_te}, N_BOOT, seed)["fuliza_late"]
    F2 = list(features) + ["fuliza_late"]
    Xtr, ytr = tr[F2], tr.defaulted.astype(int).to_numpy()
    point = make_model("logistic", **settings).fit(Xtr, ytr)
    j = len(features)                                     # fuliza_late's column, before the missing-value flags
    coef = float(point.named_steps["m"].coef_[0][j])
    rng = np.random.default_rng(seed)
    pos, neg = np.flatnonzero(ytr == 1), np.flatnonzero(ytr == 0)
    coefs = []
    for _ in range(n_boot):
        i = np.hstack([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        m = make_model("logistic", **settings).fit(Xtr.iloc[i], ytr[i])
        coefs.append(float(m.named_steps["m"].coef_[0][j]))
    ci = percentile_interval(coefs)
    return {"in_deployed_model": False, "share_late_test": float(f_te.mean()),
            "univariate_auc_test": float(roc_auc_score(yte, f_te)), "univariate_auc_test_ci": percentile_interval(boot),
            "univariate_auc_all_rows": None,
            "coef_train_refit": coef, "coef_bootstrap_ci": ci, "coef_ci_excludes_zero": bool(ci[0] > 0 or ci[1] < 0),
            "coef_bootstrap_resamples": n_boot}


# ------------------------------------------------------------------ figures
def _figures(out: Path, dec: pd.DataFrame, p_test, tiers: pd.DataFrame, auc_tbl: pd.DataFrame) -> list:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    files = []
    ink, indigo, gold = "#0E1226", "#3B2FC9", "#F5B83D"

    fig, (ax, axh) = plt.subplots(2, 1, figsize=(6, 7), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
    top = max(dec.wilson_high.max(), dec.mean_predicted_pd.max()) * 1.08
    ax.plot([0, top], [0, top], ls="--", color="#9AA0B4", lw=1, label="Perfect calibration")
    ax.errorbar(dec.mean_predicted_pd, dec.observed_default_rate,
                yerr=np.clip([dec.observed_default_rate - dec.wilson_low, dec.wilson_high - dec.observed_default_rate], 0, None),
                fmt="o", color=indigo, ecolor=indigo, capsize=3, label="Observed rate (Wilson 95%)")
    ax.set_xlim(0, top); ax.set_ylim(0, top)
    ax.set_ylabel("Observed default rate"); ax.set_title("Reliability: logistic model, test set, deciles of PD")
    ax.legend(loc="upper left", fontsize=8)
    axh.hist(p_test, bins=30, range=(0, top), color=gold, edgecolor="white")
    axh.set_xlabel("Predicted PD"); axh.set_ylabel("Applications")
    fig.tight_layout(); f = out / "reliability_diagram.png"; fig.savefig(f, dpi=200); plt.close(fig); files.append(f)

    fig, ax = plt.subplots(figsize=(6.5, 4))
    x = np.arange(len(tiers)); w = 0.38
    ax.bar(x - w / 2, tiers.mean_predicted_pd, w, color=indigo, label="Mean predicted PD")
    obs = tiers.observed_default_rate.fillna(0)
    ax.bar(x + w / 2, obs, w, color=gold, label="Observed default rate",
           yerr=np.clip([obs - tiers.wilson_low.fillna(0), tiers.wilson_high.fillna(0) - obs], 0, None), capsize=3, ecolor=ink)
    for i, (n, k) in enumerate(zip(tiers.n, tiers.defaults)):
        ax.text(i, -0.04, f"n={n}, {k} def.", ha="center", va="top", fontsize=8, color=ink)
    ax.set_xticks(x); ax.set_xticklabels(tiers.tier); ax.set_ylabel("Default rate")
    ax.set_ylim(-0.1, max(0.5, float(tiers.wilson_high.max()) * 1.1))
    ax.set_title("Predicted vs observed default rate by tier (test set)"); ax.legend(fontsize=8)
    fig.tight_layout(); f = out / "tier_calibration.png"; fig.savefig(f, dpi=200); plt.close(fig); files.append(f)

    fig, ax = plt.subplots(figsize=(6.5, 3.2))
    rows = auc_tbl.iloc[::-1].reset_index(drop=True)
    ax.errorbar(rows.auc, np.arange(len(rows)), xerr=np.clip([rows.auc - rows.auc_low, rows.auc_high - rows.auc], 0, None),
                fmt="s", color=indigo, ecolor=indigo, capsize=4)
    ax.set_yticks(np.arange(len(rows))); ax.set_yticklabels(rows.label)
    ax.axvline(0.5, color="#9AA0B4", ls=":", lw=1)
    ax.set_xlabel("Test AUC with 95% bootstrap interval (2,000 stratified resamples)")
    ax.set_title("Discrimination on the test set")
    fig.tight_layout(); f = out / "auc_forest_plot.png"; fig.savefig(f, dpi=200); plt.close(fig); files.append(f)
    return files


# ------------------------------------------------------------------ report
def _fmt(v, d=3):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{d}f}"


def _pct(v, d=1):
    return "-" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{100 * v:.{d}f}%"


def _ci(lo_hi, d=3, pct=False):
    f = _pct if pct else _fmt
    return f"{f(lo_hi[0], d)} to {f(lo_hi[1], d)}"


def verdict(cals: dict, dec: pd.DataFrame, tiers: dict, monos: dict) -> dict:
    """Plain-language reading of the checks, by fixed rules so the report and the numbers never disagree.
    cals / tiers / monos: {"test": ..., "oof_train": ..., "validation": ...}.

    Calibration counts as POOR when, in the test set or the larger out-of-fold sample, the calibration-in-the-large
    interval excludes 0 or the slope interval excludes 1; or a tier's 95% interval misses its PD band in any sample; or
    the Hosmer-Lemeshow p-value is below 0.05, or the tiers are out of order, in at least two of the three samples. A
    flag in one sample only is reported as noise-level (the test set has 62 defaults)."""
    def bias(c):
        lo, hi = c["calibration_in_the_large_ci"]
        return "under" if lo > 0 else "over" if hi < 0 else None

    def spread(c):
        lo, hi = c["slope_ci"]
        return "too_extreme" if hi < 1 else "too_compressed" if lo > 1 else None

    main = ("test", "oof_train")
    biases = {s: bias(cals[s]) for s in main if bias(cals[s])}
    spreads = {s: spread(cals[s]) for s in main if spread(cals[s])}
    hl_flags = [s for s, c in cals.items() if c["hosmer_lemeshow"]["p_value"] < 0.05]
    order_flags = [s for s, m in monos.items() if not m["observed_rate_rises_with_tier"]]
    band_misses = {s: t[t.interval_misses_band].tier.tolist() for s, t in tiers.items() if t.interval_misses_band.any()}
    missed = dec[~dec.predicted_inside_interval]
    over = missed[missed.mean_predicted_pd > missed.wilson_high].decile.tolist()
    under = missed[missed.mean_predicted_pd < missed.wilson_low].decile.tolist()
    poor = bool(biases or spreads or band_misses or len(hl_flags) >= 2 or len(order_flags) >= 2)
    if not poor:
        label = "well calibrated within the uncertainty of the data"
    elif set(biases.values()) == {"under"}:
        label = "under-predicts default"
    elif set(biases.values()) == {"over"}:
        label = "over-predicts default"
    else:
        label = "needs recalibration"
    return {"label": label, "calibration_poor": poor, "bias": biases, "spread": spreads,
            "hosmer_lemeshow_below_0_05": hl_flags, "tiers_out_of_order": order_flags, "tier_interval_misses_band": band_misses,
            "test_deciles_over_predicted": over, "test_deciles_under_predicted": under}


SAMPLE_NAMES = {"test": "test set", "oof_train": "out-of-fold training sample", "validation": "validation set"}


def _verdict_lines(S: dict) -> list:
    v, c = S["verdict"], S["calibration_test"]
    names = lambda keys: ", ".join(SAMPLE_NAMES[k] for k in keys)          # noqa: E731
    mono = {k: S[f"monotonicity_{k}"]["observed_rate_rises_with_tier"] for k in SAMPLE_NAMES}
    lines = [f"- **Calibration: {v['label']}.**"]
    if v["bias"]:
        lines.append("- Overall bias: " + "; ".join(f"{SAMPLE_NAMES[k]} {'under' if d == 'under' else 'over'}-predicts "
                                                     "default" for k, d in v["bias"].items()) + ".")
    else:
        lines.append(f"- No overall bias: calibration-in-the-large {_fmt(c['calibration_in_the_large'], 2)} "
                     f"({_ci(c['calibration_in_the_large_ci'], 2)}) on the test set; mean predicted PD "
                     f"{_pct(c['mean_predicted_pd'])} against an observed {_pct(c['observed_default_rate'])}.")
    if v["spread"]:
        lines.append("- Spread: " + "; ".join(f"{SAMPLE_NAMES[k]} {'too extreme (slope below 1)' if d == 'too_extreme' else 'too compressed (slope above 1)'}"
                                              for k, d in v["spread"].items()) + ".")
    else:
        lines.append(f"- No clear over- or under-spread: calibration slope {_fmt(c['slope'], 2)} ({_ci(c['slope_ci'], 2)}) "
                     f"on the test set, {_fmt(S['calibration_oof_train']['slope'], 2)} out-of-fold and "
                     f"{_fmt(S['calibration_validation']['slope'], 2)} on validation; every interval includes 1.")
    flags = []
    if v["hosmer_lemeshow_below_0_05"]:
        flags.append(f"Hosmer-Lemeshow p below 0.05 on the {names(v['hosmer_lemeshow_below_0_05'])}")
    if v["test_deciles_under_predicted"] or v["test_deciles_over_predicted"]:
        def dec_words(ds):
            return ("decile " if len(ds) == 1 else "deciles ") + ", ".join(str(d) for d in ds)
        parts = ([f"under-predicted in {dec_words(v['test_deciles_under_predicted'])}"] if v["test_deciles_under_predicted"] else []) + \
                ([f"over-predicted in {dec_words(v['test_deciles_over_predicted'])}"] if v["test_deciles_over_predicted"] else [])
        flags.append("the test set is " + " and ".join(parts))
    if v["tiers_out_of_order"]:
        flags.append(f"tiers out of order on the {names(v['tiers_out_of_order'])}")
    for t in S["tiers_test"]:
        if t["observed_outside_band"] and not t["interval_misses_band"]:
            flags.append(f"{t['tier']} on the test set has an observed rate of {_pct(t['observed_default_rate'])}, outside "
                         f"its {t['pd_band']} band, though its 95% interval ({_pct(t['wilson_low'])} to "
                         f"{_pct(t['wilson_high'])}) overlaps the band")
    if flags:
        single = len(v["hosmer_lemeshow_below_0_05"]) < 2 and len(v["tiers_out_of_order"]) < 2
        lines.append("- Flags: " + "; ".join(flags) + "." + (
            " Each appears in one sample only and not in the others, so it is read as sampling noise in a 62-default "
            "test set, not a property of the model." if single else ""))
    lines.append("- Tiers in order (observed default rate rising from Low to Very high risk): "
                 + ", ".join(f"{SAMPLE_NAMES[k]} {'yes' if ok else '**no**'}" for k, ok in mono.items()) + ".")
    if v["tier_interval_misses_band"]:
        lines.append("- Tier intervals outside their PD band: " + "; ".join(
            f"{SAMPLE_NAMES[k]}: {', '.join(t)}" for k, t in v["tier_interval_misses_band"].items()) + ".")
    return lines


def write_report(path: Path, S: dict, dec: pd.DataFrame, dec_oof: pd.DataFrame, tiers_by: dict,
                 auc_tbl: pd.DataFrame) -> None:
    c, co, cv, v, sc, st, fz = (S["calibration_test"], S["calibration_oof_train"], S["calibration_validation"],
                                S["verdict"], S["score_check"], S["stability"], S["fuliza_late"])
    L = ["# Calibration and uncertainty report", "",
         "Evaluation only: the deployed logistic model (`models/logistic.joblib`), its 52 features, the score formula and "
         "the tier thresholds are unchanged. Produced by `python -m src.evaluate_calibration` (seed 42; numbers in "
         "`reports/calibration/`). **All outcomes are simulated**, so these numbers describe how well the model recovers "
         "the synthetic default, not how it would perform on real borrowers.", "",
         f"Test set: {S['test']['n']} applications from {S['test']['vendors']} vendors, {S['test']['defaults']} defaults "
         f"({_pct(S['test']['default_rate'])}). Same vendor split as `docs/model_report.md`.", "",
         "## Verdict", "", *_verdict_lines(S),
         f"- Discrimination: logistic test AUC {_fmt(S['discrimination']['logistic']['auc'])} "
         f"({_ci(S['discrimination']['logistic']['ci'])}). "
         + ("Every paired difference with the other models has an interval that includes 0, so the data do not support "
            "ranking the models." if all(r["diff_ci_includes_0"] for r in S["paired_differences"].values()) else
            "At least one paired difference excludes 0; see the table."), "",
         "## What each number means", "",
         "| Metric | In one sentence |", "|---|---|",
         "| AUC | The chance that a randomly chosen defaulter gets a higher PD than a randomly chosen non-defaulter (0.5 = coin toss, 1 = perfect ranking). |",
         "| Gini | 2 x AUC - 1, the same ranking quality on a 0 to 1 scale. |",
         "| KS | The largest gap between the PD distributions of defaulters and non-defaulters. |",
         "| Brier score | The mean squared gap between the PD and the 0/1 outcome (lower is better). |",
         "| Brier skill score | How much better the Brier score is than always predicting the training default rate (0 = no better, 1 = perfect). |",
         "| Log loss | The average penalty for confident wrong predictions (lower is better). |",
         "| Calibration slope | Below 1: predictions too extreme; above 1: too timid; 1 is ideal. |",
         "| Calibration-in-the-large | Above 0: the model predicts too little default overall; below 0: too much; 0 is ideal. |",
         "| Hosmer-Lemeshow | A chi-square test of predicted vs observed defaults across 10 groups; indicative only with this few defaults. |",
         "| ECE | The average gap between predicted and observed default rates over 10 equal-size groups. |",
         "| Wilson interval | A 95% interval for an observed rate that behaves well with small counts. |", "",
         "## Discrimination (test set)", "",
         "95% percentile intervals from 2,000 bootstrap resamples stratified by outcome; the differences are paired "
         "(every model scored on the same resamples).", "",
         "| Model | Test AUC | 95% interval | Difference vs logistic | 95% interval | Includes 0 |", "|---|---|---|---|---|---|"]
    for _, r in auc_tbl.iterrows():
        if r.model == "logistic":
            L.append(f"| {r.label} | {_fmt(r.auc)} | {_fmt(r.auc_low)} to {_fmt(r.auc_high)} | - | - | - |")
        else:
            L.append(f"| {r.label} | {_fmt(r.auc)} | {_fmt(r.auc_low)} to {_fmt(r.auc_high)} | {r.diff_vs_logistic:+.3f} | "
                     f"{r.diff_low:+.3f} to {r.diff_high:+.3f} | {'yes' if r.diff_includes_0 else 'no'} |")
    d = S["discrimination"]["logistic"]
    L += ["", "The visible scorecard is the rule the synthetic defaults were drawn from (without its hidden terms), "
          "scored with no fitting, so it is close to the best ranking the visible data allow; it is a ceiling to compare "
          "with, not a competing model.", "",
          f"Logistic: KS {_fmt(d['ks'])}, Gini {_fmt(d['gini'])}. Resampling whole vendors instead (as "
          f"`docs/model_report.md` does, because one vendor's applications are not independent) gives a wider interval: "
          f"{_ci(d['vendor_bootstrap_ci'])}.", "",
          "## Calibration of the PD", "",
          "| | Test set | Out-of-fold, training vendors | Validation set |", "|---|---|---|---|",
          *[f"| {label} | " + " | ".join(fn(x) for x in (c, co, cv)) + " |" for label, fn in (
              ("Applications (defaults)", lambda x: f"{x['n']} ({x['defaults']})"),
              ("Observed default rate", lambda x: _pct(x["observed_default_rate"])),
              ("Mean predicted PD", lambda x: _pct(x["mean_predicted_pd"])),
              ("Brier score", lambda x: _fmt(x["brier"], 4)),
              (f"Brier, constant {_pct(c['reference_pd'])} (training default rate)", lambda x: _fmt(x["brier_reference"], 4)),
              ("Brier skill score", lambda x: _fmt(x["brier_skill_score"])),
              ("Log loss", lambda x: _fmt(x["log_loss"])),
              ("Calibration intercept (slope free)", lambda x: f"{_fmt(x['intercept'], 2)} ({_ci(x['intercept_ci'], 2)})"),
              ("Calibration slope", lambda x: f"{_fmt(x['slope'], 2)} ({_ci(x['slope_ci'], 2)})"),
              ("Calibration-in-the-large", lambda x: f"{_fmt(x['calibration_in_the_large'], 2)} ({_ci(x['calibration_in_the_large_ci'], 2)})"),
              ("Hosmer-Lemeshow (10 groups, 8 df), indicative",
               lambda x: f"{_fmt(x['hosmer_lemeshow']['statistic'], 1)}, p = {_fmt(x['hosmer_lemeshow']['p_value'])}"),
              ("ECE (10 equal-count bins)", lambda x: _fmt(x["ece_10_equal_count"])))], "",
          "- **Test set**: the deployed model on the test vendors (as in `docs/model_report.md`).",
          "- **Out-of-fold, training vendors**: the same logistic pipeline and settings refitted in 5 grouped folds of the "
          "training vendors, so every training application gets a prediction from a model that did not see it. A larger "
          "sample for the calibration check; temporary fits, not the deployed model.",
          "- **Validation set**: the deployed model on the validation vendors, which it never trained on (they were used "
          "only for reporting and lender cut-offs). A second independent holdout of the same size as the test set.", "",
          "### By decile of predicted PD (test set)", "",
          "| Decile | n | Defaults | Mean predicted PD | Observed rate | Wilson 95% | Predicted inside interval |",
          "|---|---|---|---|---|---|---|"]
    for _, r in dec.iterrows():
        L.append(f"| {r.decile} | {r.n} | {r.defaults} | {_pct(r.mean_predicted_pd)} | {_pct(r.observed_default_rate)} | "
                 f"{_pct(r.wilson_low)} to {_pct(r.wilson_high)} | {'yes' if r.predicted_inside_interval else '**no**'} |")
    L += ["", "### By decile of predicted PD (out-of-fold, training vendors)", "",
          "| Decile | n | Defaults | Mean predicted PD | Observed rate | Wilson 95% | Predicted inside interval |",
          "|---|---|---|---|---|---|---|"]
    for _, r in dec_oof.iterrows():
        L.append(f"| {r.decile} | {r.n} | {r.defaults} | {_pct(r.mean_predicted_pd)} | {_pct(r.observed_default_rate)} | "
                 f"{_pct(r.wilson_low)} to {_pct(r.wilson_high)} | {'yes' if r.predicted_inside_interval else '**no**'} |")
    L += ["", "![Reliability diagram](../reports/calibration/reliability_diagram.png)", "",
          "## By app tier", "",
          "Tiers come from `scoring.TIER_BANDS` and `scoring.risk_tier` (imported, not copied). \"Outside band\" means the "
          "observed rate is outside the tier's PD band; \"interval misses band\" means even its 95% interval does.", "",
          "| Sample | Tier | PD band | n | Defaults | Mean predicted PD | Observed rate | Wilson 95% | Outside band | Interval misses band |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for label, t in tiers_by.items():
        for _, r in t.iterrows():
            L.append(f"| {label} | {r.tier} | {r.pd_band} | {r.n} | {r.defaults} | {_pct(r.mean_predicted_pd)} | "
                     f"{_pct(r.observed_default_rate)} | {_pct(r.wilson_low)} to {_pct(r.wilson_high)} | "
                     f"{'**yes**' if r.observed_outside_band else 'no'} | {'**yes**' if r.interval_misses_band else 'no'} |")
    L += ["", "Monotonicity: the observed default rate should rise from Low to Very high risk (fall as the score rises).", ""]
    for k, name in SAMPLE_NAMES.items():
        m = S[f"monotonicity_{k}"]
        L.append(f"- {name.capitalize()}: {', '.join(_pct(x) for x in m['rates_low_to_very_high'])}: "
                 + ("rises at every step." if m["observed_rate_rises_with_tier"] else "**does not rise at every step.**"))
    L += ["",
          "![Tier calibration](../reports/calibration/tier_calibration.png)", "",
          "## Score formula", "",
          f"`600 + 50 x log2(((1 - PD) / PD) / 5)`, rounded and clipped to 300-850, written out independently, gives "
          f"{'exactly' if sc['formula_equals_pd_to_score'] else '**not**'} the scores of `scoring.pd_to_score` for all "
          f"{sc['n']} test PDs (largest difference {sc['max_abs_difference']} points). The data hold no separately stored "
          "test-set scores, so this compares the formula with the code that the app uses.", "",
          "| Tier boundary PD | Exact score | Rounded score | First score always in the lower-risk tier | Rounded score shared by both tiers |",
          "|---|---|---|---|---|"]
    for b in sc["boundaries"]:
        L.append(f"| {_pct(b['pd'], 0)} | {b['score_exact']:.2f} | {b['score_rounded']} | {b['first_score_always_in_lower_risk_tier']} | "
                 f"{'yes' if b['rounded_score_shared_by_both_tiers'] else 'no'} |")
    L += ["", "Tiers are assigned from the PD, not from the rounded score. A PD just under a boundary and the boundary PD "
          "itself round to the same score, so one score per boundary can belong to either tier (cosmetic: at most a "
          f"one-point overlap). On the test set, {sc['tier_from_pd_vs_tier_from_score_disagreements']} application(s) "
          "sit on such a shared score.", "",
          "## How much a small test set moves", "",
          f"AUC of the logistic model on each half of 5 stratified random 50/50 splits of the test set (about "
          f"{st['half_size']} applications and {st['defaults_per_half']} defaults per half): mean {_fmt(st['mean'])}, "
          f"range {_fmt(st['min'])} to {_fmt(st['max'])}.", "",
          "![AUC forest plot](../reports/calibration/auc_forest_plot.png)", "",
          "## fuliza_late", "",
          "`fuliza_late` is a post-application outcome (a Fuliza draw in the 60 days after the application still unpaid "
          "30 days later). It is banned as an input in `train_models.py`, so the deployed model has no coefficient for it.", "",
          f"- Univariate AUC for default on the test set: {_fmt(fz['univariate_auc_test'])} "
          f"({_ci(fz['univariate_auc_test_ci'])}); on all {S['all_rows']} rows: {_fmt(fz['univariate_auc_all_rows'])}. "
          f"{'The interval includes 0.5: no evidence it separates defaulters from non-defaulters.' if fz['univariate_auc_test_ci'][0] <= 0.5 <= fz['univariate_auc_test_ci'][1] else 'The interval excludes 0.5.'}",
          f"- Diagnostic only: adding it to the logistic pipeline refitted on the training vendors gives a coefficient of "
          f"{fz['coef_train_refit']:+.3f}, bootstrap 95% interval {_ci(fz['coef_bootstrap_ci'])} "
          f"({fz['coef_bootstrap_resamples']} resamples); the interval "
          f"{'excludes' if fz['coef_ci_excludes_zero'] else 'includes'} 0. These refits are temporary objects, never "
          "saved, and fuliza_late must stay out of the model because it is only known after the loan.", ""]
    if not v["calibration_poor"]:
        L += ["## Recalibration", "",
              "Not recommended on this evidence. If a later run shows a bias or slope problem that repeats across samples, "
              "Platt scaling fitted on the validation vendors is the first option. The rules behind the verdict are in "
              "`verdict()` in `src/evaluate_calibration.py`.", ""]
    else:
        L += ["## Possible fixes (not applied)", "",
              "Neither is applied; both keep the model's ranking (AUC) and change only the PD, and so the score and tier.", "",
              "- **Platt scaling**: fit `logit(PD_new) = a + b x logit(PD)` on a held-out calibration split (for example "
              "the validation vendors, which the deployed model did not train on). Two parameters, stable with few "
              "defaults; it fixes an overall bias (a) and over- or under-spread predictions (b). The score formula and "
              "the tier cut-offs then apply to the recalibrated PD.",
              "- **Isotonic regression** on the same split: a free-form monotone mapping. It can fix uneven "
              "miscalibration that Platt cannot, but with about 60 defaults in a calibration split it is step-shaped and "
              "can overfit; Platt is the safer first choice here.",
              "- Either one needs the calibration split kept apart from the test set, and the test-set checks above re-run "
              "afterwards.", ""]
    L += ["## Limits", "",
          "- **The data are simulated.** Defaults are drawn from a known scorecard probability, so the model is recovering "
          "a synthetic rule. Nothing here says how it would perform on real vendors.",
          f"- **The test set has only {S['test']['defaults']} defaults.** Intervals are wide: a tier or decile holds a "
          "handful of defaults, the Hosmer-Lemeshow test is indicative only, and the half-sample AUCs above show how far "
          "one number can move.",
          "- **Model ranking is not supported where intervals overlap.** The paired AUC differences are the right test, "
          "and an interval that includes 0 means the data cannot tell the models apart.",
          "- The bootstrap resamples applications. One vendor can have up to 4 applications, which are not independent; "
          "the vendor-level interval above is the more cautious one.", ""]
    path.write_text("\n".join(L), encoding="utf-8")


# ------------------------------------------------------------------ main
def main(argv=None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--features", default="data/processed/features.parquet")
    ap.add_argument("--columns", default="data/processed/feature_columns.json")
    ap.add_argument("--predictions", default="data/processed/predictions.parquet")
    ap.add_argument("--models-dir", default="models")
    ap.add_argument("--out", default="reports/calibration")
    ap.add_argument("--report", default="docs/calibration_report.md")
    ap.add_argument("--seed", type=int, default=SEED)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    feat = pd.read_parquet(a.features)
    F = json.load(open(a.columns))["features"]
    deployed = joblib.load(os.path.join(a.models_dir, "logistic.joblib"))
    assert deployed["features"] == F and deployed["seed"] == a.seed, "the saved model does not match the features/seed"
    assign = split_vendors(feat, a.seed)
    feat["split"] = feat.vendor_id.map(assign)
    if os.path.exists(a.predictions):                     # the same test vendors as docs/model_report.md
        pred = pd.read_parquet(a.predictions)
        same = feat.set_index("application_id").split.reindex(pred.application_id).to_numpy()
        assert (same == pred.split.to_numpy()).all(), "split differs from data/processed/predictions.parquet"
    tr, va, te = (feat[feat.split == s] for s in ("train", "val", "test"))
    yte, ytr, yva = (d.defaulted.astype(int).to_numpy() for d in (te, tr, va))

    # test-set predictions from the SAVED models (no refit)
    P = {"logistic": deployed["model"].predict_proba(te[F])[:, 1], "scorecard": te.scorecard_score.to_numpy()}
    for n in ("random_forest", "xgboost"):
        m = joblib.load(os.path.join(a.models_dir, f"{n}.joblib"))
        P[n] = m["model"].predict_proba(te[m["features"]])[:, 1]
    if os.path.exists(a.predictions):
        stored = pred.set_index("application_id").p_logistic.reindex(te.application_id).to_numpy()
        assert np.allclose(stored, P["logistic"], atol=1e-9), "saved model does not reproduce stored test predictions"

    # 1. discrimination with uncertainty
    boot = stratified_bootstrap_auc(yte, {k: P[k] for k in MODELS}, N_BOOT, a.seed)
    rows, diffs = [], {}
    for k in MODELS:
        auc = float(roc_auc_score(yte, P[k]))
        lo, hi = percentile_interval(boot[k])
        row = {"model": k, "label": LABEL[k], "auc": auc, "auc_low": lo, "auc_high": hi}
        if k != "logistic":
            dd = boot["logistic"] - boot[k]
            dlo, dhi = percentile_interval(dd)
            row.update({"diff_vs_logistic": float(roc_auc_score(yte, P["logistic"]) - auc), "diff_low": dlo, "diff_high": dhi,
                        "diff_includes_0": bool(dlo <= 0 <= dhi)})
            diffs[k] = {"logistic_minus_model": row["diff_vs_logistic"], "ci": [dlo, dhi], "diff_ci_includes_0": row["diff_includes_0"]}
        rows.append(row)
    auc_tbl = pd.DataFrame(rows)
    auc_tbl.to_csv(out / "auc_bootstrap.csv", index=False)
    lg = float(roc_auc_score(yte, P["logistic"]))
    discrimination = {k: {"auc": float(r.auc), "ci": [float(r.auc_low), float(r.auc_high)]}
                      for k, r in zip(auc_tbl.model, auc_tbl.itertuples())}
    discrimination["logistic"].update({"ks": ks_stat(yte, P["logistic"]), "gini": 2 * lg - 1,
                                       "vendor_bootstrap_ci": vendor_bootstrap_auc(yte, P["logistic"], te.vendor_id, N_BOOT, a.seed)})

    # 2. calibration (test, and out-of-fold on the training vendors with the deployed settings)
    p_ref = float(ytr.mean())
    cal = calibration_block(yte, P["logistic"], p_ref)
    dec = decile_table(yte, P["logistic"])
    oof = oof_predictions("logistic", deployed["settings"], tr[F], tr.defaulted.astype(int), tr.vendor_id, a.seed)
    cal_oof = calibration_block(ytr, oof, p_ref)
    dec_oof = decile_table(ytr, oof)
    # a second untouched holdout: the validation vendors, scored by the SAVED model (it never trained on them)
    p_val = deployed["model"].predict_proba(va[F])[:, 1]
    cal_val = calibration_block(yva, p_val, p_ref)
    dec_val = decile_table(yva, p_val)
    pd.concat([dec.assign(sample="test"), dec_oof.assign(sample="oof_train"), dec_val.assign(sample="validation")]
              ).to_csv(out / "calibration_deciles.csv", index=False)

    # 3-4. tiers and monotonicity
    tiers, tiers_oof, tiers_val = tier_table(yte, P["logistic"]), tier_table(ytr, oof), tier_table(yva, p_val)
    pd.concat([tiers.assign(sample="test"), tiers_oof.assign(sample="oof_train"), tiers_val.assign(sample="validation")]
              ).to_csv(out / "tier_calibration.csv", index=False)

    # 5-7. score formula, stability, fuliza_late
    fz = fuliza_diagnostic(tr, te, F, deployed["settings"], N_BOOT_COEF, a.seed)
    fz["univariate_auc_all_rows"] = float(roc_auc_score(feat.defaulted.astype(int), feat.fuliza_late.astype(float)))

    S = {"seed": a.seed, "note": "Evaluation only. Simulated outcomes: not real-world performance.",
         "all_rows": int(len(feat)),
         "test": {"n": int(len(te)), "vendors": int(te.vendor_id.nunique()), "defaults": int(yte.sum()),
                  "default_rate": float(yte.mean())},
         "train": {"n": int(len(tr)), "defaults": int(ytr.sum()), "default_rate": p_ref},
         "bootstrap": {"resamples": N_BOOT, "stratified_by_outcome": True, "interval": "percentile 95%"},
         "discrimination": discrimination, "paired_differences": diffs,
         "validation": {"n": int(len(va)), "defaults": int(yva.sum()), "default_rate": float(yva.mean())},
         "calibration_test": cal, "calibration_oof_train": cal_oof, "calibration_validation": cal_val,
         "tiers_test": tiers.to_dict("records"), "tiers_oof_train": tiers_oof.to_dict("records"),
         "tiers_validation": tiers_val.to_dict("records"),
         "monotonicity_test": monotonic(tiers), "monotonicity_oof_train": monotonic(tiers_oof),
         "monotonicity_validation": monotonic(tiers_val),
         "score_check": score_check(P["logistic"]), "stability": stability(yte, P["logistic"], 5, a.seed),
         "fuliza_late": fz, "tier_bands": [list(b) for b in tier_bands()]}
    S["verdict"] = verdict({"test": cal, "oof_train": cal_oof, "validation": cal_val}, dec,
                           {"test": tiers, "oof_train": tiers_oof, "validation": tiers_val},
                           {"test": S["monotonicity_test"], "oof_train": S["monotonicity_oof_train"],
                            "validation": S["monotonicity_validation"]})
    S["figures"] = [str(f.as_posix()) for f in _figures(out, dec, P["logistic"], tiers, auc_tbl)]
    (out / "calibration_summary.json").write_text(json.dumps(S, indent=2, default=float), encoding="utf-8")
    write_report(Path(a.report), S, dec, dec_oof, {"Test": tiers, "OOF train": tiers_oof, "Validation": tiers_val},
                 auc_tbl)
    print(f"wrote {out}/ and {a.report}")
    return S


if __name__ == "__main__":
    main()
