"""Unit tests for src/evaluate_calibration.py on small synthetic inputs (no data files or saved models needed)."""
import math

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

import evaluate_calibration as EC
import scoring


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


# ---------------------------------------------------------------- Wilson interval
def test_wilson_known_values_and_edges():
    lo, hi = EC.wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)      # symmetric at 0.5
    lo, hi = EC.wilson(0, 10)
    assert lo == 0.0 and hi == pytest.approx(0.2775, abs=1e-4)                                   # never below 0
    lo, hi = EC.wilson(10, 10)
    assert hi == pytest.approx(1.0) and hi <= 1.0 and lo == pytest.approx(0.7225, abs=1e-4)      # never above 1
    assert all(math.isnan(v) for v in EC.wilson(0, 0))
    for k, n in ((1, 35), (13, 35), (62, 350), (287, 1579)):
        lo, hi = EC.wilson(k, n)
        assert lo <= k / n <= hi                                                                  # contains the rate


# ---------------------------------------------------------------- Brier skill score
def test_brier_skill_score():
    y = np.array([0, 0, 1, 1])
    perfect = EC.brier_skill(y, y.astype(float), 0.5)
    assert perfect["brier"] == 0 and perfect["brier_reference"] == 0.25 and perfect["brier_skill_score"] == 1
    const = EC.brier_skill(y, np.full(4, 0.5), 0.5)
    assert const["brier_skill_score"] == 0                                    # the reference itself: no skill
    worse = EC.brier_skill(y, np.array([0.9, 0.9, 0.1, 0.1]), 0.5)
    assert worse["brier"] == pytest.approx(0.81) and worse["brier_skill_score"] == pytest.approx(1 - 0.81 / 0.25)


# ---------------------------------------------------------------- calibration slope and intercept
def test_calibration_slope_near_one_for_a_perfectly_calibrated_predictor():
    rng = np.random.default_rng(7)
    p = _sigmoid(rng.normal(-1.5, 1.0, 20000))
    y = rng.binomial(1, p)
    c = EC.calibration_intercept_slope(y, p)
    assert c["slope"] == pytest.approx(1, abs=0.08) and c["intercept"] == pytest.approx(0, abs=0.08)
    assert c["slope_ci"][0] < 1 < c["slope_ci"][1] and c["calibration_in_the_large"] == pytest.approx(0, abs=0.05)
    # predictions twice as extreme on the logit scale: slope near 0.5; a constant overstatement: negative CITL
    too_extreme = _sigmoid(2 * np.log(p / (1 - p)))
    assert EC.calibration_intercept_slope(y, too_extreme)["slope"] == pytest.approx(0.5, abs=0.05)
    too_high = _sigmoid(np.log(p / (1 - p)) + 0.7)
    assert EC.calibration_intercept_slope(y, too_high)["calibration_in_the_large"] == pytest.approx(-0.7, abs=0.08)


def test_hosmer_lemeshow_and_ece_on_calibrated_and_biased_predictors():
    rng = np.random.default_rng(11)
    p = _sigmoid(rng.normal(-1.5, 1.0, 20000))
    y = rng.binomial(1, p)
    assert EC.hosmer_lemeshow(y, p)["p_value"] > 0.01 and EC.expected_calibration_error(y, p) < 0.01
    biased = np.clip(p * 1.6, 0, 0.99)
    assert EC.hosmer_lemeshow(y, biased)["p_value"] < 1e-6 and EC.expected_calibration_error(y, biased) > 0.05
    assert EC.hosmer_lemeshow(y, p)["df"] == 8


def test_decile_table_has_equal_counts_and_wilson_bounds():
    rng = np.random.default_rng(3)
    p = rng.uniform(0.01, 0.6, 350)
    y = rng.binomial(1, p)
    t = EC.decile_table(y, p)
    assert list(t.n) == [35] * 10 and t.defaults.sum() == y.sum()
    assert (t.mean_predicted_pd.diff().dropna() > 0).all()                     # deciles in PD order
    assert ((t.wilson_low <= t.observed_default_rate) & (t.observed_default_rate <= t.wilson_high)).all()


# ---------------------------------------------------------------- bootstrap
def test_stratified_bootstrap_is_seeded_paired_and_matches_sklearn():
    rng = np.random.default_rng(5)
    y = np.r_[np.ones(20, int), np.zeros(80, int)]
    s1 = rng.normal(size=100) + y
    s2 = np.round(rng.normal(size=100), 1)                                     # ties, which resampling adds more of
    a = EC.stratified_bootstrap_auc(y, {"a": s1, "b": s2}, n_boot=300, seed=1)
    b = EC.stratified_bootstrap_auc(y, {"a": s1, "b": s2}, n_boot=300, seed=1)
    assert np.array_equal(a["a"], b["a"]) and np.array_equal(a["b"], b["b"])                    # deterministic
    assert not np.array_equal(a["a"], EC.stratified_bootstrap_auc(y, {"a": s1}, 300, seed=2)["a"])
    # rebuild the first resample: the rank formula equals sklearn's AUC, and both models used the same rows
    g = np.random.default_rng(1)
    pos, neg = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    idx = np.hstack([g.choice(pos, (300, 20)), g.choice(neg, (300, 80))])
    for name, s in (("a", s1), ("b", s2)):
        assert a[name][0] == pytest.approx(roc_auc_score(y[idx[0]], s[idx[0]]))
        assert a[name][17] == pytest.approx(roc_auc_score(y[idx[17]], s[idx[17]]))
    perfect = EC.stratified_bootstrap_auc(y, {"p": y.astype(float)}, n_boot=50, seed=0)["p"]
    assert np.all(perfect == 1.0)
    noise = EC.stratified_bootstrap_auc(y, {"n": rng.normal(size=100)}, n_boot=2000, seed=0)["n"]
    lo, hi = EC.percentile_interval(noise)
    assert lo < roc_auc_score(y, rng.normal(size=100)) + 0.5 and lo < hi


# ---------------------------------------------------------------- score formula and tiers
def test_score_formula_identity_with_the_app_code():
    pds = np.r_[np.linspace(0.001, 0.999, 2000), [1 / 6, 0.02, 0.05, 0.08, 0.17, 0.30, 0.5, 0.8]]
    assert np.array_equal(EC.score_formula(pds), scoring.pd_to_score(pds))
    assert int(EC.score_formula([1 / 6])[0]) == 600                           # 5:1 odds score 600
    assert int(EC.score_formula([0.02])[0]) == 765 and int(EC.score_formula([0.5])[0]) == 484   # 764.6 rounds up
    assert EC.score_formula([1e-6])[0] == 850 and EC.score_formula([0.9999])[0] == 300        # clipped


def test_tier_boundaries_come_from_the_code_and_show_the_one_point_overlap():
    check = EC.score_check(np.array([0.05, 0.0799, 0.08, 0.12, 0.25, 0.5]))
    assert check["formula_equals_pd_to_score"] and check["max_abs_difference"] == 0
    b = check["boundaries"]
    assert [x["pd"] for x in b] == [u for u, _ in scoring.TIER_BANDS[:-1]]                       # imported, not copied
    assert [x["score_rounded"] for x in b] == [660, 598, 545]
    assert [x["first_score_always_in_lower_risk_tier"] for x in b] == [661, 599, 546]
    assert all(x["rounded_score_shared_by_both_tiers"] for x in b)
    assert check["tier_from_pd_vs_tier_from_score_disagreements"] == 1    # PD 7.99% is Low but scores 660


def test_tier_table_and_monotonicity():
    assert [n for n, _, _ in EC.tier_bands()] == [n for _, n in scoring.TIER_BANDS]
    p = np.r_[np.full(10, 0.05), np.full(10, 0.12), np.full(12, 0.25), np.full(10, 0.5)]
    y = np.r_[np.zeros(10), np.r_[np.ones(2), np.zeros(8)], np.r_[np.ones(3), np.zeros(9)],
              np.r_[np.ones(5), np.zeros(5)]].astype(int)
    t = EC.tier_table(y, p)
    assert list(t.n) == [10, 10, 12, 10] and list(t.defaults) == [0, 2, 3, 5]
    assert list(t.observed_outside_band) == [False, True, False, False]                         # 20% is above 17%
    assert EC.monotonic(t)["observed_rate_rises_with_tier"]
    y2 = y.copy()
    y2[:3] = 1                                                                                    # Low now 30%
    assert not EC.monotonic(EC.tier_table(y2, p))["observed_rate_rises_with_tier"]


def test_stability_uses_five_stratified_halves():
    rng = np.random.default_rng(9)
    y = np.r_[np.ones(62, int), np.zeros(288, int)]
    p = rng.normal(size=350) + y
    s = EC.stability(y, p, repeats=5, seed=42)
    assert len(s["half_aucs"]) == 10 and s["min"] <= s["mean"] <= s["max"] and s["defaults_per_half"] == 31
    assert s == EC.stability(y, p, repeats=5, seed=42)                                           # seeded


def test_verdict_rules():
    rng = np.random.default_rng(1)
    p = _sigmoid(rng.normal(-1.5, 1.0, 4000))
    y = rng.binomial(1, p)
    good = EC.calibration_block(y, p, float(y.mean()))
    dec, tiers = EC.decile_table(y, p), EC.tier_table(y, p)
    mono = EC.monotonic(tiers)
    v = EC.verdict({"test": good, "oof_train": good, "validation": good}, dec,
                   {"test": tiers, "oof_train": tiers, "validation": tiers}, {"test": mono, "oof_train": mono, "validation": mono})
    assert not v["calibration_poor"] and v["label"].startswith("well calibrated")
    high = np.clip(p * 1.8, 0, 0.99)
    bad = EC.calibration_block(y, high, float(y.mean()))
    v = EC.verdict({"test": bad, "oof_train": good, "validation": good}, EC.decile_table(y, high),
                   {"test": EC.tier_table(y, high), "oof_train": tiers, "validation": tiers},
                   {"test": mono, "oof_train": mono, "validation": mono})
    assert v["calibration_poor"] and v["bias"] == {"test": "over"}
