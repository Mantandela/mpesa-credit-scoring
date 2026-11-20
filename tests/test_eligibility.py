"""Estimated eligibility (src/eligibility.py): a PROTOTYPE policy, tested as a pure function."""
import json
import math
from pathlib import Path

import pytest

import eligibility as EL

ROOT = Path(__file__).resolve().parent.parent
CUT = EL.Cutoffs(comfortable=0.056367105686659244, stretched=0.41940241208515233)    # the trained model's values
TIERS = ("Low risk", "Moderate risk", "High risk", "Very high risk")


def test_policy_is_one_dict_with_the_agreed_tier_factors():
    assert EL.ELIGIBILITY_POLICY["tier_factor"] == {"Low": 0.50, "Moderate": 0.35, "High": 0.15, "Very high": 0.0}
    assert EL.ELIGIBILITY_POLICY["round_down_to"] == 100


@pytest.mark.parametrize("tier, factor", [("Low risk", 0.50), ("Moderate risk", 0.35), ("High risk", 0.15),
                                          ("Very high risk", 0.0)])
def test_each_tier_factor(tier, factor):
    income = 164000.0
    e = EL.eligibility(tier, income, CUT)
    assert e["tier_factor"] == factor
    assert e["max_amount"] == math.floor(factor * CUT.stretched * income / 100) * 100
    assert e["comfortable_amount"] == math.floor(min(CUT.comfortable * income, e["max_amount"]) / 100) * 100
    assert e["status"] == ("not_eligible" if factor == 0 else "eligible")


def test_worked_example():
    e = EL.eligibility("Low risk", 164000, CUT)          # 0.5 x 0.4194 x 164,000 = 34,391; 0.0564 x 164,000 = 9,244
    assert (e["status"], e["max_amount"], e["comfortable_amount"]) == ("eligible", 34300, 9200)
    assert EL.eligibility("Moderate", 164000, CUT)["max_amount"] == 24000                  # 24,073.7 rounded down


def test_amounts_round_down_to_100():
    cut = EL.Cutoffs(comfortable=0.05, stretched=0.40)
    e = EL.eligibility("Low", 10_999, cut)                 # max 0.5 x 0.4 x 10,999 = 2,199.8 -> 2,100; comfortable 549.95 -> 500
    assert (e["max_amount"], e["comfortable_amount"]) == (2100, 500)
    e = EL.eligibility("Low", 10_000, cut)                 # exactly 2,000 and 500 stay as they are
    assert (e["max_amount"], e["comfortable_amount"]) == (2000, 500)
    assert all(v % 100 == 0 for t in TIERS for inc in (1234.5, 98765, 5e5)
               for v in (EL.eligibility(t, inc, CUT)["max_amount"], EL.eligibility(t, inc, CUT)["comfortable_amount"]))


def test_comfortable_never_above_max():
    tight = EL.Cutoffs(comfortable=0.10, stretched=0.30)  # High: max 0.15 x 0.3 = 0.045 x income, below 0.10 x income
    e = EL.eligibility("High", 100000, tight)
    assert e["max_amount"] == 4500 and e["comfortable_amount"] == 4500
    for t in TIERS:
        for inc in (500, 7000, 64000, 250000):
            for cut in (CUT, tight):
                e = EL.eligibility(t, inc, cut)
                assert e["comfortable_amount"] <= e["max_amount"]


@pytest.mark.parametrize("income", [None, 0, 0.0, -5000, float("nan")])
def test_missing_or_zero_income_is_unknown(income):
    e = EL.eligibility("Low risk", income, CUT)
    assert e["status"] == "unknown" and e["max_amount"] is None and e["comfortable_amount"] is None


def test_very_high_tier_is_not_eligible():
    e = EL.eligibility("Very high risk", 1_000_000, CUT)
    assert e == {"status": "not_eligible", "max_amount": 0, "comfortable_amount": 0, "tier_factor": 0.0}


def test_a_tiny_income_can_round_to_not_eligible():
    assert EL.eligibility("High", 1000, CUT)["status"] == "not_eligible"        # 0.15 x 0.42 x 1,000 = 62.9 -> 0


def test_monotone_in_income():
    incomes = [0.01, 100, 999, 5000, 25000, 64000, 164000, 400000, 2e6]
    for t in TIERS:
        maxes = [EL.eligibility(t, i, CUT)["max_amount"] for i in incomes]
        comf = [EL.eligibility(t, i, CUT)["comfortable_amount"] for i in incomes]
        assert maxes == sorted(maxes) and comf == sorted(comf), t


def test_tier_names_and_unknown_tiers():
    assert EL.tier_key("Moderate risk") == EL.tier_key("moderate") == "Moderate"
    assert EL.tier_key("Very high risk") == "Very high"
    with pytest.raises(ValueError):
        EL.eligibility("Medium risk", 1000, CUT)


def test_cutoffs_are_read_from_the_reference_file(tmp_path):
    ref = {"affordability_bands": {"feature": "amount_to_avg_monthly_income_90", "p50": 0.07, "p85": 0.5, "n": 10}}
    p = tmp_path / "reference.json"
    p.write_text(json.dumps(ref))
    assert EL.load_cutoffs(p) == EL.Cutoffs(comfortable=0.07, stretched=0.5)
    assert EL.cutoffs_from_reference(ref) == EL.Cutoffs(0.07, 0.5)
    real = ROOT / "models" / "reference.json"
    if real.exists():                                        # the trained reference (gitignored; absent in CI)
        bands = json.loads(real.read_text())["affordability_bands"]
        assert EL.load_cutoffs(real) == EL.Cutoffs(bands["p50"], bands["p85"])
    src = (ROOT / "src" / "eligibility.py").read_text(encoding="utf-8")
    assert "0.056" not in src.split('"""', 2)[2] and "0.419" not in src.split('"""', 2)[2]   # never hard-coded in code
