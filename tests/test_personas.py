"""The generator must match the persona table (docs/personas.md) for supplier payments, bills and Fuliza restocks.

Runs the generator in memory (120 vendors, seed 42, full histories, about 25 seconds) and checks every rule in
src/persona_check.py: one rule per persona-table cell. The rules read only statements, personas and features, never an
outcome, so a failure here means the generator and the written table disagree, not that a model got worse.

The persona mix is set to 20% each for this test only, so every persona has about 24 vendors; the mix does not change
how a vendor of a persona behaves. The seed is fixed; the rules also passed for seeds 1 to 9 when they were written.
"""
import pytest

import config as C
import persona_check as PC

N_VENDORS, SEED = 120, 42


@pytest.fixture(scope="module")
def measures():
    with pytest.MonkeyPatch.context() as mp:
        for p in C.PERSONAS.values():
            mp.setitem(p, "share", 1 / len(C.PERSONAS))
        return PC.measures(*PC.generate(N_VENDORS, seed=SEED))


def test_every_persona_is_in_the_sample(measures):
    assert set(measures) == set(PC.PERSONA_ORDER)
    assert all(m["vendors"] >= 10 for m in measures.values()), {p: m["vendors"] for p, m in measures.items()}


@pytest.mark.parametrize("i", range(14))
def test_persona_table_cell(measures, i):
    rules = PC.rules(measures)
    assert len(rules) == 14, "a persona_check rule was added or removed: update the range above"
    cell, rule, ok = rules[i]
    assert ok, f"generator disagrees with personas.md: {cell} ({rule})\n{PC.table(measures)}"


def test_struggling_vendors_pay_suppliers_less_often_than_stable_ones(measures):
    # The original bug: Fuliza-funded restocks gave struggling vendors more supplier payments than stable vendors
    assert measures["struggling"]["supplier_count_90_median"] < measures["stable"]["supplier_count_90_median"]


def test_growing_vendors_pay_bills_at_least_as_often_as_struggling_ones(measures):
    # The original bug: growing vendors' bills failed against a swept wallet (median 0 months paid, struggling 1)
    assert measures["growing"]["paybill_months_paid_90_median"] >= measures["struggling"]["paybill_months_paid_90_median"]
    assert measures["growing"]["paybill_months_paid_90_median"] >= 3
