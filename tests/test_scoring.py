"""Unit tests for the PD to score conversion (src/scoring.py). Run from the repo root:  python -m pytest tests"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import scoring as S


def test_higher_pd_gives_lower_score():
    pds = np.linspace(0.01, 0.95, 60)
    scores = S.pd_to_score(pds)
    assert (np.diff(scores) <= 0).all()


def test_score_stays_inside_range_even_for_extreme_pd():
    for p in (0.0, 1e-9, 0.5, 1 - 1e-9, 1.0):
        assert S.SCORE_MIN <= S.pd_to_score(p) <= S.SCORE_MAX


def test_portfolio_average_pd_scores_the_base_score():
    avg_pd = 1 / (1 + S.BASE_ODDS)                    # 16.7%
    assert S.pd_to_score(avg_pd) == S.BASE_SCORE


def test_pdo_points_double_the_odds():
    p1 = 0.20
    odds = (1 - p1) / p1
    p2 = 1 / (1 + 2 * odds)                           # odds of good twice as high
    assert abs((S.pd_to_score(p2) - S.pd_to_score(p1)) - S.PDO) <= 1


def test_score_to_pd_inverts_the_conversion():
    for p in (0.03, 0.10, 0.30, 0.60):
        assert abs(float(S.score_to_pd(S.pd_to_score(p))) - p) < 0.01


def test_risk_tiers_follow_the_bands_and_never_improve_with_risk():
    order = [name for _, name in S.TIER_BANDS]
    tiers = [order.index(S.risk_tier(p)) for p in np.linspace(0, 1, 101)]
    assert tiers == sorted(tiers)
    assert S.risk_tier(0.03) == "Low risk" and S.risk_tier(0.9) == "Very high risk"