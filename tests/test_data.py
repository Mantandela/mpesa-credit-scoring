"""Tests on the generated data itself (the sample in data/sample/, made by scripts/make_sample.py).

By default the tests read data/sample/. To run the same tests on your FULL data, point them at it:
    PowerShell:  $env:CREDIT_DATA_DIR = "data"; python -m pytest tests/test_data.py
Each test is skipped when the folder is missing, so a fresh clone without data still passes.

These tests check the data that is stored, so they do not notice a generator change until the sample is made again.
The code itself is checked by the other test files, which use small statements built in tests/toy.py.
"""
import json
import os

import numpy as np
import pandas as pd
import pytest

import config as C
import features as Fe

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
BASE = os.environ.get("CREDIT_DATA_DIR") or os.path.join(ROOT, "data", "sample")
BASE = BASE if os.path.isabs(BASE) else os.path.join(ROOT, BASE)

OUTCOME_COLUMNS = {"defaulted", "late_or_default", "days_past_due", "repayment_status", "scorecard_p", "fuliza_late"}
BANNED_FEATURES = {"persona", "latent_risk", "txn_type_true", "gender", "business_type", "defaulted", "days_past_due",
                   "late_or_default", "repayment_status", "scorecard_p", "scorecard_score", "hidden_shock", "fuliza_late",
                   "fuliza_n_draws", "fuliza_max_lag_days", "window_complete"}


def _path(*p):
    full = os.path.join(BASE, *p)
    if not os.path.exists(full):
        pytest.skip(f"{full} not found (make the sample with scripts/make_sample.py)")
    return full


@pytest.fixture(scope="module")
def vendors():
    return pd.read_parquet(_path("synthetic", "vendors.parquet"))


@pytest.fixture(scope="module")
def apps():
    return pd.read_parquet(_path("synthetic", "loan_applications.parquet"))


@pytest.fixture(scope="module")
def tx():
    t = pd.read_parquet(_path("synthetic", "transactions.parquet"))
    t["completion_time"] = pd.to_datetime(t["completion_time"])
    return t.sort_values(["vendor_id", "completion_time"], kind="stable").reset_index(drop=True)


@pytest.fixture(scope="module")
def ctx():
    t = pd.read_parquet(_path("interim", "transactions_clean.parquet"))
    t["completion_time"] = pd.to_datetime(t["completion_time"])
    return t


@pytest.fixture(scope="module")
def feat():
    return pd.read_parquet(_path("processed", "features.parquet"))


@pytest.fixture(scope="module")
def cols():
    return json.load(open(_path("processed", "feature_columns.json")))


# ---------------------------------------------------------------- generated statements (rules from docs/data_dictionary.md)
def test_all_five_personas_are_present_and_known(vendors):
    assert set(vendors.persona) == set(C.PERSONAS)


def test_every_application_and_transaction_belongs_to_a_known_vendor(vendors, apps, tx):
    assert set(apps.vendor_id) <= set(vendors.vendor_id) and set(tx.vendor_id) <= set(vendors.vendor_id)
    assert apps.application_id.is_unique and vendors.vendor_id.is_unique


def test_each_row_has_paid_in_or_withdrawn_not_both(tx):
    assert ((tx.paid_in > 0) & (tx.withdrawn > 0)).sum() == 0


def test_running_balance_reconciles_within_each_vendor(tx):
    prev = tx.groupby("vendor_id")["balance"].shift(1)
    chk = (prev + tx.paid_in - tx.withdrawn - tx.balance).abs()
    assert (chk[prev.notna()] < 0.01).all()


def test_receipt_numbers_are_unique_and_times_strictly_increase(tx):
    assert tx.receipt_no.is_unique
    assert (tx.groupby("vendor_id").completion_time.diff().dropna() > pd.Timedelta(0)).all()


def test_no_negative_amounts_or_balances(tx):
    assert (tx[["paid_in", "withdrawn", "balance"]] >= 0).all().all()


def test_fuliza_draws_are_between_50_and_1000(tx):
    draws = tx[tx.txn_type_true == "FULIZA_DRAW"].paid_in
    assert len(draws) > 0 and draws.between(50, 1000).all()


def test_every_application_has_90_days_of_statement_after_it(vendors, apps):
    v = vendors.set_index("vendor_id")
    end = pd.to_datetime(v.start_date) + pd.to_timedelta(v.statement_days - 1, unit="D")
    gap = (apps.vendor_id.map(end) - pd.to_datetime(apps.application_date)).dt.days
    assert (gap >= C.OBS_WINDOW_DAYS).all(), f"shortest window {gap.min()} days"


def test_hidden_shock_looks_standard_normal_and_no_outcome_is_stored_with_the_applications(apps):
    assert abs(apps.hidden_shock.mean()) < 0.5 and 0.6 < apps.hidden_shock.std() < 1.4
    assert not OUTCOME_COLUMNS & set(apps.columns)


# ---------------------------------------------------------------- cleaned statements
def test_cleaning_kept_every_row_and_raised_no_integrity_flag(tx, ctx):
    assert len(ctx) == len(tx) and set(ctx.receipt_no) == set(tx.receipt_no)
    for flag in ("flag_both_amounts", "flag_balance_break", "flag_duplicate_receipt", "flag_time_not_increasing", "flag_negative"):
        assert ctx[flag].sum() == 0, flag


def test_classification_from_the_wording_matches_the_generator_truth(ctx):
    assert (ctx.txn_type == ctx.txn_type_true).mean() > 0.999


# ---------------------------------------------------------------- features and labels
def test_one_feature_row_per_application(feat, apps):
    assert feat.application_id.is_unique and set(feat.application_id) == set(apps.application_id)


def test_feature_list_has_no_label_hidden_or_slicing_column(cols, feat):
    F = cols["features"]
    assert not BANNED_FEATURES & set(F) and not set(cols["meta"]) & set(F) and set(F) <= set(feat.columns)
    assert not feat[F].isin([np.inf, -np.inf]).any().any()


def test_labels_are_consistent_with_each_other(feat):
    assert set(feat.defaulted.unique()) <= {0, 1} and set(feat.repayment_status.unique()) <= {0, 1, 2}
    assert ((feat.defaulted == 1) == (feat.repayment_status == 2)).all()          # default is class 2
    assert ((feat.late_or_default == 1) == (feat.repayment_status >= 1)).all()
    assert (feat.fuliza_late[feat.fuliza_n_draws == 0] == 0).all()                  # no draw, so nothing can be late
    assert feat.scorecard_p.between(0, 1).all()
    # a vendor can be quiet at the end of its statement, so a few windows may be flagged incomplete (1 of 2,244 in the full run)
    assert feat.window_complete.mean() > 0.99
    assert (feat.repayment_status[~feat.window_complete] == 2).all()    # a short window must never hide a late payment

def test_stored_features_equal_a_rebuild_from_the_cleaned_statements(feat, apps, ctx, cols):
    """Each stored feature row must equal what features.py gives from the transactions before its application date."""
    F = cols["features"]
    A = apps.merge(feat[["application_id"]], on="application_id").copy()
    A["application_date"] = pd.to_datetime(A.application_date)
    for app in A.sample(min(12, len(A)), random_state=0).itertuples(index=False):
        g = ctx[ctx.vendor_id == app.vendor_id].sort_values("completion_time", kind="stable")
        rebuilt = Fe.build_row(g, app)
        stored = feat.set_index("application_id").loc[app.application_id]
        for k, v in rebuilt.items():
            assert k in F
            assert np.isclose(float(stored[k]), float(v), equal_nan=True), (app.application_id, k)


def test_nothing_after_the_application_date_is_needed_for_the_stored_features(feat, apps, ctx):
    """Cut each vendor's statement at the application date: the features must not change (no leakage)."""
    A = apps.copy()
    A["application_date"] = pd.to_datetime(A.application_date)
    for app in A.sample(min(8, len(A)), random_state=1).itertuples(index=False):
        g = ctx[ctx.vendor_id == app.vendor_id].sort_values("completion_time", kind="stable")
        full = Fe.build_row(g, app)
        cut = Fe.build_row(g[g.completion_time < app.application_date], app)
        for k in full:
            assert np.isclose(float(full[k]), float(cut[k]), equal_nan=True), (app.application_id, k)


# ---------------------------------------------------------------- rates (only meaningful with enough applications)
def test_default_rate_and_persona_order_on_a_large_dataset(feat):
    if len(feat) < 1500:
        pytest.skip("rate checks need the full data: set CREDIT_DATA_DIR=data")
    assert 0.12 < feat.defaulted.mean() < 0.22
    by = feat.groupby("persona").defaulted.mean()
    assert by.idxmax() == "struggling" and by["struggling"] > 2 * by["stable"]


def test_no_single_feature_predicts_default_almost_perfectly_on_a_large_dataset(feat, cols):
    from sklearn.metrics import roc_auc_score
    if feat.defaulted.sum() < 200:
        pytest.skip("leakage screen needs the full data: set CREDIT_DATA_DIR=data")
    for f in cols["features"]:
        x = feat[f].fillna(feat[f].median())
        if x.nunique() > 1:
            auc = roc_auc_score(feat.defaulted, x)
            assert max(auc, 1 - auc) < 0.85, f"{f} has AUC {auc:.2f}: the label may leak into it"