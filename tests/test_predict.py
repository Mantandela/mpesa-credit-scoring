"""Tests for src/predict.py (score_statement) and src/build_reference.py.

The main tests build a tiny logistic model and reference files from toy statements in a temporary folder, so they need
no data and no trained artifacts. The last test reproduces stored predictions on the full data; it runs only when
CREDIT_DATA_DIR is set (PowerShell: $env:CREDIT_DATA_DIR = "data"; python -m pytest tests/test_predict.py).
"""
import json
import os
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

import build_reference as BR
import clean
import config as C
import feature_labels as FL
import features as Fe
import predict as P
import toy
from train_models import make_model

ROOT = Path(__file__).resolve().parent.parent
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
    total = e["base_value"] + sum(e["shap_values"].values())             # the unmerged values, all of them
    p = out["probability_of_default"]
    assert len(e["shap_values"]) >= len(toy_artifacts["F"])
    assert total == pytest.approx(e["logit"], abs=1e-6)
    assert total == pytest.approx(np.log(p / (1 - p)), abs=1e-6)
    for r in out["top_reasons"]:                                         # each reason carries its feature's own value
        assert r["shap_value"] == e["shap_values"][r["feature"]]


# ---------------------------------------------------------------- reasons
def _reason_checks(out):
    reasons = out["top_reasons"]
    assert len(reasons) == 5
    fams = [r["family"] for r in reasons]
    assert len(set(fams)) == 5, f"repeated family: {fams}"
    assert all(r["family"] == FL.family(r["feature"]) for r in reasons)
    for r in reasons:                                                    # no neutral (no-data) reason in the top 5
        assert not FL.is_missing_flag(r["feature"]) and r["value"] is not None and np.isfinite(r["value"])
        assert r["sentence"].startswith(("Raises your risk", "Lowers your risk"))
        assert r["family"] not in FL.EXCLUDED_FROM_REASONS
    abs_sv = [abs(r["shap_value"]) for r in reasons]
    assert abs_sv == sorted(abs_sv, reverse=True)
    groups = [FL._GROUP_OF[f] for f in fams if f in FL._GROUP_OF]     # one per measure group: no contradiction
    assert len(groups) == len(set(groups))
    for n in out["data_notes"]:
        assert n["sentence"].startswith("No data in this statement on:") and "risk" not in n["sentence"]
        assert n["family"] not in fams


def test_reasons_are_five_distinct_real_themes(toy_artifacts, raw_vendor):
    out = _score(toy_artifacts, raw_vendor, requested_amount=5000, requested_term_days=14)
    _reason_checks(out)
    # the first reason is the largest |SHAP| among features that have data and may be reasons
    bundle = joblib.load(toy_artifacts["model"])
    used, cut, _, _ = P._used_transactions(raw_vendor)
    med = out["inputs_used"]["scored_at"]
    _, X = P._feature_frame(used, cut, med["requested_amount"], med["requested_term_days"], bundle["features"])
    eligible = [abs(v) for n, v in out["explanation"]["shap_values"].items()
                if not FL.is_missing_flag(n) and FL.family(n) not in FL.EXCLUDED_FROM_REASONS and not np.isnan(X.iloc[0][n])]
    assert abs(out["top_reasons"][0]["shap_value"]) == max(eligible)


def test_missing_data_gives_neutral_notes_not_reasons(toy_artifacts):
    out = _score(toy_artifacts, toy.make_vendor(days=40))               # thin history: several features have no data
    assert out["data_notes"], "a 40-day statement should leave some measures without data"
    _reason_checks(out)


# ---------------------------------------------------------------- the request does not move the score
def test_score_does_not_depend_on_the_requested_loan(toy_artifacts, raw_vendor):
    outs = [_score(toy_artifacts, raw_vendor, requested_amount=a, requested_term_days=t)
            for a, t in ((1000, 7), (5000, 14), (20000, 30))]
    for k in ("probability_of_default", "score", "tier", "pillar_ratings", "top_reasons", "data_notes", "explanation"):
        assert outs[0][k] == outs[1][k] == outs[2][k], k                # exact
    ref = toy_artifacts["reference"]
    for o in outs:
        assert o["inputs_used"]["scored_at"] == {"requested_amount": ref["requested_amount"]["median"],
                                                 "requested_term_days": ref["requested_term_days"]["median"]}
        assert "score_at_median_request" in [w["code"] for w in o["warnings"]]
    assert [o["inputs_used"]["requested_amount"] for o in outs] == [max(1000.0, ref["requested_amount"]["p01"]), 5000.0,
                                                                    min(20000.0, ref["requested_amount"]["p99"])]


def test_score_is_the_model_at_the_median_request(toy_artifacts, raw_vendor):
    out = _score(toy_artifacts, raw_vendor, requested_amount=9000, requested_term_days=28)
    bundle = joblib.load(toy_artifacts["model"])
    used, cut, _, _ = P._used_transactions(raw_vendor)
    med = out["inputs_used"]["scored_at"]
    _, X = P._feature_frame(used, cut, med["requested_amount"], med["requested_term_days"], bundle["features"])
    assert out["probability_of_default"] == P._probability(X, bundle["model"])


BAND_RANK = {"comfortable": 0, "stretched": 1, "heavy": 2}


def test_affordability_never_improves_as_the_amount_rises(toy_artifacts, raw_vendor):
    outs = [_score(toy_artifacts, raw_vendor, requested_amount=a, requested_term_days=14)["affordability"]
            for a in [100, 500, 1000, 2500, 5000, 7500, 10000, 15000, 50000]]
    for key in ("amount_to_income_30", "amount_to_avg_monthly_income_90"):
        vals = [a[key] for a in outs]
        assert all(b >= a for a, b in zip(vals, vals[1:])), key
    ranks = [BAND_RANK[a["band"]] for a in outs]
    assert all(b >= a for a, b in zip(ranks, ranks[1:]))
    assert all(a["estimated_repayment"] == a["requested_amount"] for a in outs)
    # the ratios are the features.build_row ratios for the request given
    bundle = joblib.load(toy_artifacts["model"])
    used, cut, _, _ = P._used_transactions(raw_vendor)
    row, _ = P._feature_frame(used, cut, 7500, 14, bundle["features"])
    a = _score(toy_artifacts, raw_vendor, requested_amount=7500, requested_term_days=14)["affordability"]
    assert a["amount_to_income_30"] == row["amount_to_income_30"]
    assert a["amount_to_avg_monthly_income_90"] == row["amount_to_avg_monthly_income_90"]


def test_affordability_bands_follow_the_reference_cutoffs(toy_artifacts, raw_vendor):
    cut = toy_artifacts["reference"]["affordability_bands"]
    bands = set()
    for amount in np.linspace(1, 10 ** 6, 400):
        a = P._affordability({"history_days": 120.0, "income_total_30": 3000.0, "income_total_90": 9000.0}, float(amount),
                             14.0, toy_artifacts["reference"])
        r = a["amount_to_avg_monthly_income_90"]
        expect = "comfortable" if r <= cut["p50"] else "stretched" if r <= cut["p85"] else "heavy"
        assert a["band"] == expect
        bands.add(a["band"])
    assert bands == {"comfortable", "stretched", "heavy"}


def test_affordability_unknown_without_income(toy_artifacts, raw_vendor):
    no_income = toy.recompute_balance(raw_vendor[raw_vendor.paid_in == 0].reset_index(drop=True), opening=50000.0)
    out = _score(toy_artifacts, no_income, requested_amount=5000, requested_term_days=14)
    a = out["affordability"]
    assert a["band"] == "unknown" and a["amount_to_avg_monthly_income_90"] is None and a["amount_to_income_30"] is None
    json.dumps(out, allow_nan=False)


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


# ---------------------------------------------------------------- uploads (score_uploaded_file)
NAMES = ("JANE WANJIKU", "PETER OTIENO", "MARY AKINYI", "JOHN KAMAU", "GRACE MUTUA", "DAVID OCHIENG")
PHONES = ("254712345678", "0722987654", "254733111222", "0711222333", "254700999888", "0799123456")


def _personal_statement(raw_vendor) -> pd.DataFrame:
    """The toy statement in the M-Pesa sheet layout, with customer names and phone numbers in the details."""
    sheet = raw_vendor.sort_values("completion_time", ascending=False).copy()
    pay = sheet.details.str.startswith("Merchant Payment from")
    k = sheet.loc[pay, "counterparty_id"].str[-1].astype(int) % len(NAMES)
    sheet.loc[pay, "details"] = [f"Merchant Payment from {PHONES[i]} - {NAMES[i]}" for i in k]
    sheet = sheet.rename(columns={"receipt_no": "Receipt No.", "completion_time": "Completion Time", "details": "Details",
                                  "transaction_status": "Transaction Status", "paid_in": "Paid In",
                                  "withdrawn": "Withdrawn", "balance": "Balance"})
    return sheet[["Receipt No.", "Completion Time", "Details", "Transaction Status", "Paid In", "Withdrawn", "Balance"]]


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    """Point the temp folder at an empty directory and record every temporary file score_uploaded_file makes."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(P.tempfile, "tempdir", str(d))
    made = []
    real = P.tempfile.mkstemp

    def recording_mkstemp(*a, **kw):
        fd, name = real(*a, **kw)
        made.append(Path(name))
        return fd, name
    monkeypatch.setattr(P.tempfile, "mkstemp", recording_mkstemp)
    return d, made


def test_upload_is_deleted_after_success_and_holds_no_personal_data(toy_artifacts, raw_vendor, upload_dir, tmp_path):
    d, made = upload_dir
    sheet = _personal_statement(raw_vendor)
    data = sheet.to_csv(index=False).encode("utf-8")
    assert all(n.encode() in data for n in NAMES[:2]) and PHONES[0].encode() in data       # the input is personal
    out = P.score_uploaded_file(data, "my statement.csv", requested_amount=5000, requested_term_days=14,
                                model_path=toy_artifacts["model"], reference_path=toy_artifacts["ref"])
    assert len(made) == 1 and made[0].parent == d and made[0].suffix == ".csv"
    assert not made[0].exists() and not any(d.iterdir())                                       # deleted
    # the same result as scoring the frame
    direct = _score(toy_artifacts, raw_vendor, requested_amount=5000, requested_term_days=14)
    assert out["probability_of_default"] == pytest.approx(direct["probability_of_default"], abs=1e-12)
    text = json.dumps(out)
    for name in NAMES:
        for part in name.split():
            assert part not in text.upper()
    assert not re.search(r"(?<![\d.])\d{9,}", text), "a phone-like digit run is in the result"
    assert "CP_" not in text and "Merchant Payment" not in text and "my statement" not in text
    # xlsx bytes from a file object, too
    xp = tmp_path / "s.xlsx"
    sheet.to_excel(xp, index=False)
    with open(xp, "rb") as fh:
        out2 = P.score_uploaded_file(fh, "statement.xlsx", 5000, 14, model_path=toy_artifacts["model"],
                                     reference_path=toy_artifacts["ref"])
    assert out2["probability_of_default"] == pytest.approx(out["probability_of_default"], abs=1e-12)
    assert len(made) == 2 and not any(d.iterdir())


@pytest.mark.parametrize("content, filename, match", [
    (b"Receipt No.,Completion Time,Details\nnot,a,statement\n", "statement.csv", "Columns not found"),
    (b"\x00\x01 not a spreadsheet", "statement.xlsx", "."),
    (b"%PDF-1.4 broken", "statement.pdf", "PDF"),
])
def test_upload_is_deleted_after_an_error(toy_artifacts, upload_dir, content, filename, match):
    d, made = upload_dir
    with pytest.raises(ValueError, match=match):
        P.score_uploaded_file(content, filename, model_path=toy_artifacts["model"], reference_path=toy_artifacts["ref"])
    assert len(made) == 1 and not made[0].exists() and not any(d.iterdir())


def test_upload_rejects_unsupported_and_empty_files_without_writing(toy_artifacts, upload_dir):
    d, made = upload_dir
    with pytest.raises(ValueError, match="Excel"):
        P.score_uploaded_file(b"abc", "statement.docx")
    with pytest.raises(ValueError, match="empty"):
        P.score_uploaded_file(b"", "statement.csv")
    assert not made and not any(d.iterdir())


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
    bundle = joblib.load(need[3])
    ref = json.loads(need[4].read_text())
    errors = []
    for r in sample.itertuples(index=False):
        g = tx[tx.vendor_id == r.vendor_id]
        # the stored request, through the low-level steps (score_statement itself scores at the median request)
        used, cut, _, _ = P._used_transactions(g, r.application_date)
        _, X = P._feature_frame(used, cut, r.requested_amount, r.requested_term_days, bundle["features"])
        errors.append(abs(P._probability(X, bundle["model"]) - r.p_logistic))
        # score_statement = the same model at the median request, whatever request is passed
        out = P.score_statement(g, r.requested_amount, r.requested_term_days, r.application_date,
                                model_path=str(need[3]), reference_path=str(need[4]))
        _, Xm = P._feature_frame(used, cut, ref["requested_amount"]["median"], ref["requested_term_days"]["median"],
                                 bundle["features"])
        assert out["probability_of_default"] == P._probability(Xm, bundle["model"])
    assert max(errors) < 1e-6, f"max error {max(errors):.2e}"
