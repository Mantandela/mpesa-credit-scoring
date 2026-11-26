"""Convert a probability of default (PD) into a 300-850 score and a risk tier (Chapter 4, FR6).

The conversion does not change the model or its ranking. It is a monotone rescaling of the PD, so a higher PD always gives a lower score.

Method: points to double the odds (PDO), the usual way scorecards are scaled.
    odds_good = (1 - PD) / PD
    score     = BASE_SCORE + (PDO / ln 2) * ln(odds_good / BASE_ODDS)
then rounded and clipped to 300-850.

The three constants are ASSUMPTIONS (docs/assumptions.md), not estimates from data:
    BASE_SCORE = 600 at BASE_ODDS = 5 : 1 good to bad. 5:1 is a PD of 16.7%, the average default rate the scorecard is
                 calibrated to (FinAccess 2024, 16.6%). A vendor at the portfolio average scores 600.
    PDO        = 50 points for every doubling of the odds.
With these, PD 2% scores 765 (764.6 before rounding), 5% 696, 16.7% exactly 600, 17% 598, 50% 484 and 80% 384.
Tier boundaries on the score scale: 660.08 (PD 8%), 598.28 (17%), 545.02 (30%); the tier comes from the PD, so the
rounded scores 660, 598 and 545 can fall in either neighbouring tier (docs/scoring_function.md).

Risk tiers are bands of the PD. They are illustrative cut-offs; check the share of applications in each band after the
final run, and change them in TIER_BANDS if one band is nearly empty.

Run from the repo root:  python src/scoring.py      prints a small table
"""
import math

import numpy as np

BASE_SCORE = 600
BASE_ODDS = 5.0
PDO = 50.0
SCORE_MIN, SCORE_MAX = 300, 850
PD_FLOOR, PD_CEIL = 1e-4, 1 - 1e-4          # keeps the log finite when a model returns exactly 0 or 1

# (upper PD limit, tier name), checked in order
TIER_BANDS = ((0.08, "Low risk"), (0.17, "Moderate risk"), (0.30, "High risk"), (1.01, "Very high risk"))


def pd_to_score(pd_values):
    """PD (a number or an array between 0 and 1) to an integer score between 300 and 850."""
    p = np.clip(np.asarray(pd_values, dtype=float), PD_FLOOR, PD_CEIL)
    score = BASE_SCORE + (PDO / math.log(2)) * np.log(((1 - p) / p) / BASE_ODDS)
    out = np.clip(np.rint(score), SCORE_MIN, SCORE_MAX).astype(int)
    return int(out) if out.ndim == 0 else out


def score_to_pd(score):
    """Inverse of pd_to_score (before rounding and clipping)."""
    odds_good = BASE_ODDS * np.exp((np.asarray(score, dtype=float) - BASE_SCORE) * math.log(2) / PDO)
    return 1.0 / (1.0 + odds_good)


def risk_tier(pd_value):
    """Name of the risk tier for one PD."""
    p = float(pd_value)
    for upper, name in TIER_BANDS:
        if p < upper:
            return name
    return TIER_BANDS[-1][1]


if __name__ == "__main__":
    print(f"{'PD':>6} {'score':>6}  tier")
    for p in (0.02, 0.05, 0.08, 0.12, 0.167, 0.25, 0.38, 0.50, 0.80):
        print(f"{p:6.1%} {pd_to_score(p):6d}  {risk_tier(p)}")