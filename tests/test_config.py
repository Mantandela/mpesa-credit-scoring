"""Consistency tests for src/config.py: the numbers that every other stage trusts."""
import pytest

import clean
import config as C
import features as Fe
import toy


# ---------------------------------------------------------------- scorecard
def test_every_weight_set_covers_all_pillars_and_sums_to_one():
    for name, w in C.WEIGHT_SETS.items():
        assert set(w) == set(C.SCORECARD_PILLARS), name
        assert sum(w.values()) == pytest.approx(1.0), name
        assert all(v >= 0 for v in w.values()), name
    assert C.MAIN_WEIGHTS in C.WEIGHT_SETS


def test_directions_are_plus_or_minus_one_and_no_feature_is_in_two_pillars():
    seen = {}
    for pillar, feats in C.SCORECARD_PILLARS.items():
        for f, d in feats.items():
            assert d in (-1, 1), (pillar, f)
            assert f not in seen, f"{f} is in both {seen[f]} and {pillar}"
            seen[f] = pillar


def test_every_scorecard_feature_is_a_column_the_feature_stage_produces():
    tx = clean.clean(toy.make_vendor(days=120), as_of="2026-12-31")
    produced = set(Fe.build(tx, toy.make_apps(dates=("2026-03-15",))).columns)
    missing = {f for feats in C.SCORECARD_PILLARS.values() for f in feats} - produced
    assert not missing, f"scorecard uses features that features.py does not create: {sorted(missing)}"


@pytest.mark.parametrize("feature", ["cash_deposit_share_90", "withdraw_share_of_income_90"])
def test_features_with_an_unsupported_direction_are_model_inputs_only_not_scorecard_inputs(feature):
    # Decision: their risk direction is not supported, so the scorecard does not use them (docs/scorecard_mapping.md)
    assert feature not in {f for feats in C.SCORECARD_PILLARS.values() for f in feats}
    tx = clean.clean(toy.make_vendor(days=120), as_of="2026-12-31")
    assert feature in Fe.build(tx, toy.make_apps(dates=("2026-03-15",))).columns   # still built, so still a model input


def test_scorecard_coefficients_are_positive():
    assert C.SCORECARD_SCALE > 0 and C.HIDDEN_RISK_COEF >= 0 and C.SHOCK_COEF >= 0 and C.SCORE_CLIP > 0
    assert C.SHOCK_COEF in C.SHOCK_COEF_LEVELS


# ---------------------------------------------------------------- outcome design (90-day window, 30-day lateness)
def test_outcome_window_settings_agree_with_each_other():
    assert C.OBS_WINDOW_DAYS == 90 and C.LATE_THRESHOLD_DAYS == 30
    assert C.FULIZA_COUNT_DAYS + C.LATE_THRESHOLD_DAYS == C.OBS_WINDOW_DAYS   # every counted draw has 30 days to be repaid
    assert 0 < C.TARGET_DEFAULT_RATE < 1
    lo, hi = C.SHOCK_CLIP
    assert 0 < lo < 1 < hi and C.SHOCK_INFLOW_EFFECT > 0


# ---------------------------------------------------------------- personas
def test_persona_shares_sum_to_one():
    assert sum(p["share"] for p in C.PERSONAS.values()) == pytest.approx(1.0)


def test_every_persona_range_is_ordered_low_to_high():
    for name, p in C.PERSONAS.items():
        for key, val in p.items():
            if isinstance(val, tuple):
                assert val[0] <= val[1], (name, key)


def test_hidden_risk_rises_from_stable_to_struggling():
    mid = {n: sum(p["latent_risk"]) / 2 for n, p in C.PERSONAS.items()}
    assert mid["stable"] < mid["growing"] < mid["seasonal"] < mid["struggling"]
    assert min(mid, key=mid.get) == "stable" and max(mid, key=mid.get) == "struggling"


def test_adjacent_personas_are_valid_and_never_self():
    assert set(C.ADJACENT) == set(C.PERSONAS)
    for k, near in C.ADJACENT.items():
        assert k not in near and set(near) <= set(C.PERSONAS)


def test_fee_tables_are_sorted_and_end_with_an_open_top_band():
    for table in (C.SEND_FEE, C.WITHDRAW_FEE, C.PAYBILL_FEE):
        bounds = [b for b, _ in table]
        assert bounds == sorted(bounds) and bounds[-1] >= 10**9
        fees = [f for _, f in table]
        assert fees == sorted(fees)                        # a larger amount never costs less