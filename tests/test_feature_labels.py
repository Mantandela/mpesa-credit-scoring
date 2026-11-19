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
    s = FL.reason_sentence("balance_trend_90 (missing flag)", 0.3, 1.0)
    assert s.startswith("Raises your risk:") and "no data" in s


def test_reason_sentence_example():
    s = FL.reason_sentence("near_zero_day_share_90", 0.42, 0.31, reference_median=0.12)
    assert s == "Raises your risk: days with almost no money left in your wallet (high: 31% of days)"
    s = FL.reason_sentence("balance_median_eod_90", -0.2, 4200.0, reference_median=900.0)
    assert s == "Lowers your risk: typical end-of-day wallet balance (high: KES 4,200)"
    assert "no data" in FL.reason_sentence("weekly_income_cv_90", 0.1, float("nan"), reference_median=0.3)


def test_unknown_feature_raises():
    with pytest.raises(KeyError):
        FL.label("not_a_feature")
