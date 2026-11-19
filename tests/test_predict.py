"""Tests for src/predict.py (score_statement) and src/build_reference.py.

The main tests build a tiny logistic model and reference files from toy statements in a temporary folder, so they need
no data and no trained artifacts. The last test reproduces stored predictions on the full data; it runs only when
CREDIT_DATA_DIR is set (PowerShell: $env:CREDIT_DATA_DIR = "data"; python -m pytest tests/test_predict.py).
"""
import json
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

import build_reference as BR
import clean
import config as C
import features as Fe
import predict as P
import toy
from train_models import make_model

ROOT = Path(__file__).resolve().parent.parent
AFFORDABILITY = ("requested_amount", "amount_to_income_30", "amount_to_avg_monthly_income_90")
APP_DATE = "2026-03-15"


def _toy_table(n_vendors=24, seed=0):
    """Features for 3 applications per toy vendor, with varied requests and a label driven by affordability."""
    rng = np.random.default_rng(seed)
    vt = toy.make_vendors_table([f"V{i:04d}" for i in range(n_vendors)])
    parts = []
    for i, vid in enumerate(vt.vendor_id):
        raw = toy.make_vendor(vid, days=150 + 5 * (i % 6), daily_in=80.0 + 25 * i, opening=200.0 * (i % 5), n_customers=2 + i % 9)
        apps = toy.make_apps(vid, dates=("2026-03-05", "2026-04-02", "2026-05-01"))
        apps["requested_amount"] = rng.uniform(500, 10000, len(apps)).round(-1)
        apps["requested_term_days"] = rng.integers(7, 31, len(apps)).astype(float)
        f = Fe.build(clean.clean(raw, as_of="2026-12-31"), apps)
        parts.append(pd.concat([apps[["application_id", "vendor_id", "application_date"]], f], axis=1))
    feat = pd.concat(parts, ignore_index=True).merge(vt, on="vendor_id")
    z = lambda c: (feat[c] - feat[c].mean()) / feat[c].std()  # noqa: E731
    lin = 1.5 * z("amount_to_avg_monthly_income_90") + z("amount_to_income_30") + 0.8 * z("requested_amount") \
        - 0.5 * z("income_total_90") + 0.3 * rng.normal(size=len(feat))
    feat["defaulted"] = (lin > np.median(lin)).astype(int)
    return feat


@pytest.fixture(scope="module")
def toy_artifacts(tmp_path_factory):
    d = tmp_path_factory.mktemp("toy_models")
    feat = _toy_table()
    F = [c for c in Fe.build_row(clean.clean(toy.make_vendor(), as_of="2026-12-31"),
                                 toy.make_apps().iloc[0]).keys()]
    model = make_model("logistic", C=1.0).fit(feat[F], feat.defaulted)
    joblib.dump({"model": model, "features": F, "settings": {"C": 1.0}, "seed": 42}, d / "logistic.joblib")
    ref, bg = BR.build(feat, F, split_seed=42)
    BR.write(ref, bg, d)
    return {"model": str(d / "logistic.joblib"), "ref": str(d / "reference.json"), "F": F, "feat": feat, "reference": ref}


def _score(art, statement, **kw):
    return P.score_statement(statement, model_path=art["model"], reference_path=art["ref"], **kw)


# ---------------------------------------------------------------- reference files
def test_reference_contents(toy_artifacts):
    ref = toy_artifacts["reference"]
    assert ref["features"] == toy_artifacts["F"]
    assert set(ref["pillar_distribution"]["values"]) == set(C.SCORECARD_PILLARS)
    assert all(len(v) == 101 and np.all(np.diff(v) >= 0) for v in ref["pillar_distribution"]["values"].values())
    for c in ("requested_amount", "requested_term_days"):
        assert ref[c]["p01"] <= ref[c]["median"] <= ref[c]["p99"]
    assert ref["background"]["split"] == "train" and ref["background"]["n"] > 0


def test_pillar_scores_with_stored_stats_match_the_scorecard(toy_artifacts):
    import scorecard as SC
    feat = toy_artifacts["feat"]
    a = SC.pillar_scores(feat)
    b = SC.pillar_scores(feat, stats=SC.feature_stats(feat))
    pd.testing.assert_frame_equal(a, b, check_exact=True)


def test_background_comes_from_train_vendors_only(toy_artifacts):
    from train_models import split_vendors
    feat, F = toy_artifacts["feat"], toy_artifacts["F"]
    _, bg = BR.build(feat, F, split_seed=42)
    train = feat[feat.vendor_id.map(split_vendors(feat, 42)) == "train"][F].reset_index(drop=True)
    merged = bg.merge(train.drop_duplicates(), how="left", indicator=True)
    assert (merged["_merge"] == "both").all()


# ---------------------------------------------------------------- output
def test_output_shape_and_ranges(toy_artifacts, raw_vendor):
    out = _score(toy_artifacts, raw_vendor, requested_amount=5000, requested_term_days=14)
    for k in ("probability_of_default", "score", "tier", "pillar_ratings", "top_reasons", "inputs_used", "warnings", "model_info"):
        assert k in out
    assert 0 < out["probability_of_default"] < 1
    assert 300 <= out["score"] <= 850
    assert out["tier"] in {"Low risk", "Moderate risk", "High risk", "Very high risk"}
    assert [p["pillar"] for p in out["pillar_ratings"]] == list(C.SCORECARD_PILLARS)
    assert all(0 <= p["rating"] <= 100 and p["label"] in {"Weak", "Fair", "Good", "Strong"} for p in out["pillar_ratings"])
    assert len(out["top_reasons"]) == 5
    for r in out["top_reasons"]:
        assert r["direction"] in {"raises risk", "lowers risk"} and (r["shap_value"] > 0) == (r["direction"] == "raises risk")
        assert r["label"] and r["sentence"].startswith(("Raises your risk", "Lowers your risk"))
    assert out["model_info"]["n_features"] == len(toy_artifacts["F"]) and out["model_info"]["seed"] == 42
    json.dumps(out, allow_nan=False)                               # JSON-serialisable, no NaN


def test_shap_values_add_up_to_the_decision_function(toy_artifacts, raw_vendor):
    out = _score(toy_artifacts, raw_vendor, requested_amount=5000, requested_term_days=14)
    e = out["explanation"]
    total = e["base_value"] + sum(e["shap_values"].values())
    p = out["probability_of_default"]
    assert total == pytest.approx(e["logit"], abs=1e-6)
    assert total == pytest.approx(np.log(p / (1 - p)), abs=1e-6)
    top = sorted(e["shap_values"].items(), key=lambda kv: -abs(kv[1]))[:5]
    assert [r["feature"] for r in out["top_reasons"]] == [k for k, _ in top]


def test_higher_amount_never_lowers_risk(toy_artifacts, raw_vendor):
    m = joblib.load(toy_artifacts["model"])["model"]
    coef = dict(zip(toy_artifacts["F"], m.named_steps["m"].coef_[0]))
    assert all(coef[f] > 0 for f in AFFORDABILITY), "toy model precondition: affordability features raise risk"
    ref = toy_artifacts["reference"]["requested_amount"]
    pds = [_score(toy_artifacts, raw_vendor, requested_amount=a, requested_term_days=14)["probability_of_default"]
           for a in np.linspace(ref["p01"], ref["p99"], 7)]
    assert all(b >= a - 1e-12 for a, b in zip(pds, pds[1:]))
    assert pds[-1] > pds[0]


def test_defaults_are_the_reference_medians(toy_artifacts, raw_vendor):
    out = _score(toy_artifacts, raw_vendor)
    ref = toy_artifacts["reference"]
    assert out["inputs_used"]["requested_amount"] == ref["requested_amount"]["median"]
    assert out["inputs_used"]["requested_term_days"] == ref["requested_term_days"]["median"]
    last = pd.Timestamp(raw_vendor.completion_time.max()).normalize() + pd.Timedelta(days=1)
    assert out["inputs_used"]["application_date"] == last.date().isoformat()
    assert out["inputs_used"]["transactions_after_date_ignored"] == 0


# ---------------------------------------------------------------- warnings and errors
def test_thin_history_warning(toy_artifacts):
    short = _score(toy_artifacts, toy.make_vendor(days=60))
    assert "thin_history" in [w["code"] for w in short["warnings"]]
    long = _score(toy_artifacts, toy.make_vendor(days=120))
    assert "thin_history" not in [w["code"] for w in long["warnings"]]


def test_inputs_outside_the_training_range_are_clipped_with_a_warning(toy_artifacts, raw_vendor):
    ref = toy_artifacts["reference"]
    out = _score(toy_artifacts, raw_vendor, requested_amount=10 ** 7, requested_term_days=1)
    codes = [w["code"] for w in out["warnings"]]
    assert "requested_amount_clipped" in codes and "requested_term_days_clipped" in codes
    assert out["inputs_used"]["requested_amount"] == ref["requested_amount"]["p99"]
    assert out["inputs_used"]["requested_term_days"] == ref["requested_term_days"]["p01"]
    inside = _score(toy_artifacts, raw_vendor, requested_amount=ref["requested_amount"]["median"], requested_term_days=14)
    assert not any(w["code"].endswith("_clipped") for w in inside["warnings"])


def test_no_usable_transactions_raises_a_clear_error(toy_artifacts, raw_vendor):
    with pytest.raises(ValueError, match="No usable transactions"):
        _score(toy_artifacts, raw_vendor, application_date="2025-01-01")
    with pytest.raises(ValueError, match="no transactions"):
        _score(toy_artifacts, raw_vendor.iloc[0:0])


def test_integrity_flags_are_reported_as_counts(toy_artifacts, raw_vendor):
    bad = raw_vendor.copy()
    bad.loc[5, "balance"] += 50.0                                   # one balance break
    out = _score(toy_artifacts, bad)
    w = next(w for w in out["warnings"] if w["code"] == "integrity_flags")
    assert w["counts"]["flag_balance_break"] >= 1
    assert all(isinstance(v, int) for v in w["counts"].values())


def test_transactions_after_the_application_date_are_never_used(toy_artifacts, raw_vendor):
    a = _score(toy_artifacts, raw_vendor, requested_amount=4000, requested_term_days=14, application_date=APP_DATE)
    changed = raw_vendor.copy()
    after = changed.completion_time >= pd.Timestamp(APP_DATE)
    assert after.any()
    changed.loc[after, ["paid_in", "withdrawn", "balance"]] *= 7.0
    changed.loc[after, "details"] = "OverDraft of Credit Party"
    changed = pd.concat([changed, changed[after].head(5)], ignore_index=True)    # extra future rows too
    b = _score(toy_artifacts, changed, requested_amount=4000, requested_term_days=14, application_date=APP_DATE)
    for k in ("probability_of_default", "score", "pillar_ratings", "top_reasons"):
        assert a[k] == b[k]
    assert a["inputs_used"]["transactions_used"] == b["inputs_used"]["transactions_used"]


def test_a_statement_file_gives_the_same_result_as_the_frame(toy_artifacts, raw_vendor, tmp_path):
    p = tmp_path / "statement.csv"
    sheet = raw_vendor.sort_values("completion_time", ascending=False)
    sheet = sheet.rename(columns={"receipt_no": "Receipt No.", "completion_time": "Completion Time", "details": "Details",
                                  "transaction_status": "Transaction Status", "paid_in": "Paid In",
                                  "withdrawn": "Withdrawn", "balance": "Balance"})
    sheet[["Receipt No.", "Completion Time", "Details", "Transaction Status", "Paid In", "Withdrawn", "Balance"]].to_csv(p, index=False)
    a = _score(toy_artifacts, raw_vendor, requested_amount=5000, requested_term_days=14)
    b = _score(toy_artifacts, p, requested_amount=5000, requested_term_days=14)
    assert b["probability_of_default"] == pytest.approx(a["probability_of_default"], abs=1e-12)


def test_stale_reference_is_refused(toy_artifacts, tmp_path):
    ref = dict(toy_artifacts["reference"], features=toy_artifacts["F"][:-1])
    (tmp_path / "reference.json").write_text(json.dumps(ref))
    pd.read_parquet(Path(toy_artifacts["ref"]).with_name("shap_background.parquet")).to_parquet(tmp_path / "shap_background.parquet")
    with pytest.raises(ValueError, match="build_reference"):
        P.score_statement(toy.make_vendor(), model_path=toy_artifacts["model"], reference_path=str(tmp_path / "reference.json"))


# ---------------------------------------------------------------- full data (opt-in)
def test_reproduces_stored_predictions_on_the_full_data():
    base = os.environ.get("CREDIT_DATA_DIR")
    if not base:
        pytest.skip("set CREDIT_DATA_DIR=data to run against the full data and trained model")
    base = Path(base) if Path(base).is_absolute() else ROOT / base
    need = [base / "processed" / "features.parquet", base / "processed" / "predictions.parquet",
            base / "synthetic" / "transactions.parquet", ROOT / "models" / "logistic.joblib", ROOT / "models" / "reference.json"]
    missing = [p.as_posix() for p in need if not p.exists()]
    if missing:
        pytest.skip(f"missing: {missing} (run src/train_models.py and src/build_reference.py)")
    feat = pd.read_parquet(need[0], columns=["application_id", "vendor_id", "application_date", "requested_amount",
                                             "requested_term_days"])
    pred = pd.read_parquet(need[1], columns=["application_id", "p_logistic"])
    sample = feat.sample(10, random_state=7).merge(pred, on="application_id")
    tx = pd.read_parquet(need[2], filters=[("vendor_id", "in", list(sample.vendor_id.unique()))])
    errors = []
    for r in sample.itertuples(index=False):
        out = P.score_statement(tx[tx.vendor_id == r.vendor_id], r.requested_amount, r.requested_term_days, r.application_date,
                                model_path=str(need[3]), reference_path=str(need[4]))
        errors.append(abs(out["probability_of_default"] - r.p_logistic))
    assert max(errors) < 1e-6, f"max error {max(errors):.2e}"
