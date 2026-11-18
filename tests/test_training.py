"""Tests for stage 4, src/train_models.py: metrics, the three models, and a full small run of the script.

The vendor split itself is tested in tests/test_split.py."""
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
import pytest

import train_models as T


# ---------------------------------------------------------------- metrics
def test_metrics_on_a_textbook_example():
    y, p = np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.35, 0.8])
    m = T.metrics(y, p)
    assert m["AUC"] == pytest.approx(0.75)
    assert m["Brier"] == pytest.approx(np.mean((p - y) ** 2))


def test_perfect_ranking_gives_auc_and_ks_of_one():
    y, p = np.array([0, 0, 0, 1, 1]), np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    m = T.metrics(y, p)
    assert m["AUC"] == 1.0 and m["KS"] == 1.0 and m["PR-AUC"] == 1.0


def test_reversed_ranking_gives_auc_of_zero():
    assert T.metrics(np.array([0, 0, 1, 1]), np.array([0.9, 0.8, 0.2, 0.1]))["AUC"] == 0.0


def test_bad_rate_at_a_cutoff():
    y, p = np.array([0, 0, 1, 1]), np.array([0.1, 0.2, 0.3, 0.4])
    assert T.bad_rate_at(y, p, 0.25) == (0.5, 0.0)          # approve the two lowest scores, neither defaults
    assert T.bad_rate_at(y, p, 1.0) == (1.0, 0.5)
    approval, bad = T.bad_rate_at(y, p, 0.0)                # nobody approved: the bad rate is undefined, not zero
    assert approval == 0.0 and np.isnan(bad)


def test_bootstrap_interval_is_ordered_reproducible_and_resamples_whole_vendors():
    rng = np.random.default_rng(0)
    vendors = np.repeat(np.arange(60), 3)
    y = (rng.random(180) < 0.2).astype(int)
    p = y * 0.3 + rng.random(180)
    lo, hi = T.bootstrap_auc(y, p, vendors, n=200, seed=1)
    assert 0 <= lo < hi <= 1 and lo <= T.metrics(y, p)["AUC"] <= hi
    assert (lo, hi) == T.bootstrap_auc(y, p, vendors, n=200, seed=1)


# ---------------------------------------------------------------- models and settings
def _toy_xy(n=240, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"a": rng.normal(size=n), "b": rng.normal(size=n), "c": rng.normal(size=n)})
    y = pd.Series((X.a + 0.3 * rng.normal(size=n) > 0.7).astype(int))
    X.loc[rng.random(n) < 0.15, "b"] = np.nan                # missing values must not break any model
    return X, y


@pytest.mark.parametrize("name", ["logistic", "random_forest", "xgboost"])
def test_each_model_handles_missing_values_and_returns_probabilities(name):
    X, y = _toy_xy()
    m = T.make_model(name).fit(X, y)
    p = T.proba(m, X)
    assert p.shape == (len(X),) and ((p >= 0) & (p <= 1)).all()
    assert T.metrics(y, p)["AUC"] > 0.8                      # the signal is strong, so a working model finds it


def test_unknown_model_name_is_rejected():
    with pytest.raises(ValueError):
        T.make_model("neural_net")


def test_tuning_grids():
    full, quick = T.grids(False), T.grids(True)
    assert set(full) == set(quick) == {"logistic", "random_forest", "xgboost"}
    assert all(len(quick[k]) == 1 for k in quick) and all(len(full[k]) > 1 for k in full)
    assert [g["C"] for g in full["logistic"]] == [0.01, 0.03, 0.1, 0.3, 1.0]


def test_grouped_cv_auc_returns_mean_and_spread():
    X, y = _toy_xy(300)
    groups = pd.Series(np.repeat(np.arange(100), 3))
    mean, sd = T.cv_auc("logistic", {"C": 0.1}, X, y, groups, seed=0)
    assert 0.5 < mean <= 1 and sd >= 0


# ---------------------------------------------------------------- a full run of the script on a small table
def _features_table(n_vendors=300, seed=0):
    rng = np.random.default_rng(seed)
    persona = rng.choice(["stable", "growing", "seasonal", "new", "struggling"], n_vendors)
    rows = []
    for i in range(n_vendors):
        for k in range(rng.integers(1, 4)):
            rows.append({"application_id": f"A{i}_{k}", "vendor_id": f"V{i:04d}", "persona": persona[i]})
    d = pd.DataFrame(rows)
    d["near_zero_day_share_90"] = rng.random(len(d))
    d["income_total_90"] = rng.normal(size=len(d))
    d["fuliza_draws_90"] = rng.poisson(2, len(d)).astype(float)
    d.loc[rng.random(len(d)) < 0.1, "income_total_90"] = np.nan
    d["scorecard_score"] = d.near_zero_day_share_90 + 0.2 * rng.normal(size=len(d))
    d["defaulted"] = (d.near_zero_day_share_90 + 0.25 * rng.normal(size=len(d)) > 0.8).astype(int)
    return d


def _run(tmp_path, monkeypatch, features, feature_list):
    feat_path, cols_path = tmp_path / "features.parquet", tmp_path / "feature_columns.json"
    features.to_parquet(feat_path, index=False)
    json.dump({"features": feature_list, "meta": []}, open(cols_path, "w"))
    args = ["train_models.py", "--features", str(feat_path), "--columns", str(cols_path), "--out", str(tmp_path / "out"),
            "--models-dir", str(tmp_path / "models"), "--report", str(tmp_path / "report.md"),
            "--figure", str(tmp_path / "roc.png"), "--summary-json", str(tmp_path / "summary.json"), "--quick"]
    monkeypatch.setattr(sys, "argv", args)
    T.main()


def test_script_runs_end_to_end_and_writes_its_outputs(tmp_path, monkeypatch):
    feats = _features_table()
    _run(tmp_path, monkeypatch, feats, ["near_zero_day_share_90", "income_total_90", "fuliza_draws_90"])
    for f in ("report.md", "summary.json", "out/predictions.parquet", "models/logistic.joblib",
              "models/random_forest.joblib", "models/xgboost.joblib"):
        assert os.path.exists(tmp_path / f), f
    summary = json.load(open(tmp_path / "summary.json"))
    assert set(summary["test"]) == {"logistic", "random_forest", "xgboost", "rule_baseline", "scorecard_baseline"}
    assert summary["test"]["logistic"]["test AUC"] > 0.7        # the signal is strong in this table
    pred = pd.read_parquet(tmp_path / "out" / "predictions.parquet")
    assert len(pred) == len(feats) and pred.split.isin(["train", "val", "test"]).all()
    assert pred[["p_logistic", "p_random_forest", "p_xgboost"]].apply(lambda s: s.between(0, 1).all()).all()
    assert (pred.groupby("vendor_id").split.nunique() == 1).all()          # no vendor in two splits
    assert "# Model report" in (tmp_path / "report.md").read_text()


def test_saved_model_reproduces_the_saved_predictions(tmp_path, monkeypatch):
    feats = _features_table(seed=3)
    F = ["near_zero_day_share_90", "income_total_90", "fuliza_draws_90"]
    _run(tmp_path, monkeypatch, feats, F)
    saved = joblib.load(tmp_path / "models" / "logistic.joblib")
    assert saved["features"] == F and saved["seed"] == 42
    pred = pd.read_parquet(tmp_path / "out" / "predictions.parquet").set_index("application_id")
    again = saved["model"].predict_proba(feats.set_index("application_id")[F])[:, 1]
    np.testing.assert_allclose(pred.loc[feats.application_id, "p_logistic"].to_numpy(), again)


@pytest.mark.parametrize("banned", ["persona", "defaulted", "scorecard_score", "scorecard_p", "hidden_shock", "latent_risk",
                                    "repayment_status", "fuliza_late"])
def test_labels_hidden_columns_and_persona_are_refused_as_features(tmp_path, monkeypatch, banned):
    feats = _features_table()
    feats[banned] = feats[banned] if banned in feats else 0.0
    with pytest.raises(AssertionError, match="banned columns"):
        _run(tmp_path, monkeypatch, feats, ["near_zero_day_share_90", banned])