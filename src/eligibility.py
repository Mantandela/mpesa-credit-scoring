"""Estimated loan eligibility from a score result. PROTOTYPE POLICY: placeholder values, not validated.

    eligibility(tier, monthly_income, cutoffs) -> {"status", "max_amount", "comfortable_amount", ...}

Rule (all amounts KES, rounded DOWN to the nearest 100):
    max_amount         = tier_factor[tier] * cutoffs.stretched * monthly_income
    comfortable_amount = min(cutoffs.comfortable * monthly_income, max_amount)
    status             = "eligible" if max_amount > 0 else "not_eligible"
                         "unknown" (no amounts) when monthly income is missing or <= 0

cutoffs are the affordability band cutoffs in models/reference.json (amount_to_avg_monthly_income_90 at the 50th
percentile = comfortable, 85th = stretched; about 0.056 and 0.419 for the trained model). They are always read from
the reference file, never written here.

Caveats: the tier factors are placeholders chosen for the prototype; monthly income is the statement's customer
TURNOVER (money received), not profit; the cutoffs describe simulated applicants; nothing here is validated on real
repayment outcomes. The lender makes the final decision.
"""
import json
import math
from dataclasses import dataclass
from pathlib import Path

ELIGIBILITY_POLICY = {
    # share of the "stretched" loan size (cutoffs.stretched x monthly income) a vendor of each risk tier may borrow
    "tier_factor": {"Low": 0.50, "Moderate": 0.35, "High": 0.15, "Very high": 0.0},
    "round_down_to": 100,                 # KES
    "status": "prototype",                # placeholder values, not validated on repayment outcomes
}

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Cutoffs:
    comfortable: float        # amount / monthly income at the 50th percentile of applications
    stretched: float          # ... at the 85th percentile


def cutoffs_from_reference(ref: dict) -> Cutoffs:
    b = ref["affordability_bands"]
    return Cutoffs(comfortable=float(b["p50"]), stretched=float(b["p85"]))


def load_cutoffs(reference_path=ROOT / "models" / "reference.json") -> Cutoffs:
    return cutoffs_from_reference(json.loads(Path(reference_path).read_text(encoding="utf-8")))


def tier_key(tier: str) -> str:
    """'Moderate risk' -> 'Moderate' (scoring.risk_tier names end in ' risk')."""
    t = str(tier).strip()
    key = t[:-len(" risk")] if t.lower().endswith(" risk") else t
    for k in ELIGIBILITY_POLICY["tier_factor"]:
        if k.lower() == key.lower():
            return k
    raise ValueError(f"unknown risk tier: {tier!r}")


def _round_down(x: float) -> int:
    step = ELIGIBILITY_POLICY["round_down_to"]
    return int(math.floor(x / step + 1e-9) * step)


def eligibility(tier: str, monthly_income, cutoffs: Cutoffs) -> dict:
    """Estimated eligibility for one vendor. See the module docstring for the rule and its caveats."""
    factor = ELIGIBILITY_POLICY["tier_factor"][tier_key(tier)]
    if monthly_income is None or not math.isfinite(float(monthly_income)) or float(monthly_income) <= 0:
        return {"status": "unknown", "max_amount": None, "comfortable_amount": None, "tier_factor": factor}
    income = float(monthly_income)
    max_amount = _round_down(factor * cutoffs.stretched * income)
    comfortable = _round_down(min(cutoffs.comfortable * income, max_amount))
    return {"status": "eligible" if max_amount > 0 else "not_eligible", "max_amount": max_amount,
            "comfortable_amount": comfortable, "tier_factor": factor}
