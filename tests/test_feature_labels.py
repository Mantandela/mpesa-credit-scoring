"""Every model feature must have a plain-English label (src/feature_labels.py)."""
import json
import os
from pathlib import Path

import pytest

import clean
import config as C
import feature_labels as FL
import features as Fe
import toy

ROOT = Path(__file__).resolve().parent.parent


def _features_from_code():
    """The feature list as build_row makes it (same order as data/processed/feature_columns.json)."""
    return list(Fe.build_row(clean.clean(toy.make_vendor(), as_of="2026-12-31"), toy.make_apps().iloc[0]).keys())


def _feature_columns_files():
    base = os.environ.get("CREDIT_DATA_DIR")
    cands = [ROOT / "data" / "processed" / "feature_columns.json"]
    if base:
        cands.insert(0, (Path(base) if Path(base).is_absolute() else ROOT / base) / "processed" / "feature_columns.json")
    return [p for p in cands if p.exists()]


def test_every_feature_built_by_the_code_has_a_label():
    missing = [f for f in _features_from_code() if f not in FL.FEATURE_LABELS]
    assert not missing, f"features without a label: {missing}"


def test_every_feature_in_feature_columns_json_has_a_label():
    files = _feature_columns_files()
    if not files:
        pytest.skip("data/processed/feature_columns.json not found")
    for p in files:
        feats = json.loads(p.read_text())["features"]
        missing = [f for f in feats if f not in FL.FEATURE_LABELS]
        assert not missing, f"{p}: features without a label: {missing}"


def test_scorecard_features_have_labels_and_labels_are_unique():
    for members in C.SCORECARD_PILLARS.values():
        assert all(f in FL.FEATURE_LABELS for f in members)
    feats = _features_from_code()
    labels = [FL.FEATURE_LABELS[f] for f in feats]
    assert len(set(labels)) == len(labels), "two features share a label"
    assert all(lbl and lbl == lbl.strip() for lbl in labels)


def test_missing_flag_label():
    assert FL.label("balance_trend_90 (missing flag)") == FL.FEATURE_LABELS["balance_trend_90"] + " (missing flag)"
    assert FL.is_missing_flag("balance_trend_90 (missing flag)") and FL.base_feature("balance_trend_90 (missing flag)") == "balance_trend_90"
    s = FL.reason_sentence("balance_trend_90 (missing flag)", 0.3, 1.0)        # missing data is neutral
    assert s == "No data in this statement on: " + FL.FEATURE_LABELS["balance_trend_90"]


def test_reason_sentence_example():
    s = FL.reason_sentence("near_zero_day_share_90", 0.42, 0.31, reference_median=0.12)
    assert s == "Raises your risk: days with almost no money left in your wallet (high: 31% of days)"
    s = FL.reason_sentence("balance_median_eod_90", -0.2, 4200.0, reference_median=900.0)
    assert s == "Lowers your risk: typical end-of-day wallet balance (high: KES 4,200)"
    s = FL.reason_sentence("weekly_income_cv_90", 0.1, float("nan"), reference_median=0.3)
    assert s.startswith("No data in this statement on:") and "risk" not in s


def test_unknown_feature_raises():
    with pytest.raises(KeyError):
        FL.label("not_a_feature")
    with pytest.raises(KeyError):
        FL.family("not_a_feature")


# ---------------------------------------------------------------- families and reason selection
def test_every_feature_belongs_to_exactly_one_family():
    feats = _features_from_code()
    for p in _feature_columns_files():
        assert json.loads(p.read_text())["features"] == feats
    owners = {f: [fam for fam, members in FL.FEATURE_FAMILIES.items() if f in members] for f in feats}
    assert all(len(v) == 1 for v in owners.values()), {f: v for f, v in owners.items() if len(v) != 1}
    members = [f for m in FL.FEATURE_FAMILIES.values() for f in m]
    assert sorted(members) == sorted(feats), "a family lists a feature the model does not have"
    assert FL.family("fuliza_repay_lag_median_days_90 (missing flag)") == FL.family("fuliza_repay_lag_median_days_90")
    assert FL.family("withdraw_share_of_income_30") == FL.family("withdraw_share_of_income_90") == "withdraw_share_of_income"


def test_measure_groups_name_real_families():
    grouped = [fam for fams in FL.MEASURE_GROUPS.values() for fam in fams]
    assert all(fam in FL.FEATURE_FAMILIES for fam in grouped)
    assert len(grouped) == len(set(grouped)), "a family is in two measure groups"
    assert not set(grouped) & FL.EXCLUDED_FROM_REASONS


def _values(shap, missing=()):
    return {n: (1.0 if FL.is_missing_flag(n) else float("nan")) if n in missing or FL.base_feature(n) in missing
            else (0.0 if FL.is_missing_flag(n) else 0.5) for n in shap}


def test_missing_data_is_neutral_and_does_not_take_a_place():
    flag = "fuliza_repay_lag_median_days_90 (missing flag)"
    shap = {flag: 0.9, "fuliza_repay_lag_median_days_90": 0.0, "near_zero_day_share_90": 0.5, "till_share_90": -0.4,
            "weekly_income_cv_90": 0.3, "balance_cv_90": 0.2, "history_days": -0.1, "reversal_count_90": 0.05}
    reasons, notes = FL.select_reasons(shap, _values(shap, missing={"fuliza_repay_lag_median_days_90"}))
    assert [r["feature"] for r in reasons] == ["near_zero_day_share_90", "till_share_90", "weekly_income_cv_90",
                                               "balance_cv_90", "history_days"]
    assert all(r["sentence"].startswith(("Raises your risk", "Lowers your risk")) for r in reasons)
    assert notes == [{"family": "fuliza_repay_lag_median_days_90", "label": FL.FEATURE_LABELS["fuliza_repay_lag_median_days_90"],
                      "sentence": "No data in this statement on: typical time taken to repay Fuliza"}]
    assert all("risk" not in n["sentence"] for n in notes)


def test_one_reason_per_family_with_the_largest_shap():
    shap = {"withdraw_share_of_income_30": 0.20, "withdraw_share_of_income_60": -0.11, "withdraw_share_of_income_90": 0.05,
            "income_count_30": -0.3, "income_count_90": -0.31, "till_share_90": 0.1}
    reasons, _ = FL.select_reasons(shap, _values(shap))
    assert [(r["feature"], r["family"]) for r in reasons] == [("income_count_90", "income_count"),
                                                              ("withdraw_share_of_income_30", "withdraw_share_of_income"),
                                                              ("till_share_90", "till_share_90")]
    # the 30-day member had no data: the family falls back to the next member, and gets no "no data" note
    shap2 = dict(shap, withdraw_share_of_income_30=0.9)
    reasons, notes = FL.select_reasons(shap2, _values(shap2, missing={"withdraw_share_of_income_30"}))
    assert reasons[1]["feature"] == "withdraw_share_of_income_60" and not notes


def test_contradicting_or_repeated_reasons_keep_the_larger_shap():
    shap = {"fuliza_draws_90": -0.4, "fuliza_amount_90": 0.3, "debt_service_ratio_90": -0.2,
            "balance_median_eod_90": -0.25, "balance_min_eod_90": -0.1, "till_share_90": 0.05, "history_days": 0.01}
    reasons, _ = FL.select_reasons(shap, _values(shap))
    fams = [r["family"] for r in reasons]
    # fuliza_amount_90 would contradict fuliza_draws; debt_service_ratio_90 and balance_min_eod_90 would repeat a theme
    assert fams == ["fuliza_draws", "balance_median_eod_90", "till_share_90", "history_days"]


def test_loan_request_fields_are_never_reasons():
    shap = {"requested_amount": 2.0, "amount_to_income_30": -1.5, "requested_term_days": 1.0,
            "amount_to_avg_monthly_income_90": 0.9, "till_share_90": 0.1}
    reasons, notes = FL.select_reasons(shap, _values(shap))
    assert [r["feature"] for r in reasons] == ["till_share_90"] and not notes
