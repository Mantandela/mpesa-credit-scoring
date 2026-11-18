"""Tests for stage 3, src/features.py: values on a statement small enough to check by hand, and the no-leakage rule."""
import json
import sys

import numpy as np
import pandas as pd
import pytest

import clean
import features as Fe
import toy

EXPECTED_N_FEATURES = 52               # docs/data_dictionary.md section 4. Change it here when a feature is added or dropped
APP_DATE = "2026-03-15"                # 73 days after the first transaction (2026-01-01)


@pytest.fixture(scope="module")
def tx():
    return clean.clean(toy.make_vendor(days=120), as_of="2026-12-31")


@pytest.fixture(scope="module")
def app():
    return next(toy.make_apps(dates=(APP_DATE,), amount=5000.0, term=14).itertuples(index=False))


@pytest.fixture(scope="module")
def row(tx, app):
    return Fe.build_row(tx, app)


# ---------------------------------------------------------------- hand-checked values
# The toy vendor (tests/toy.py): till payment of 200 every day, a supplier payment of 300 on days where day%7==3,
# an agent withdrawal of 500 plus a fee of 11 where day%7==5, a paybill of 800 where day%30==10, and a Fuliza draw of 300
# repaid with 309 two days later where day%15==6. At the application date (day 73) the history is 73 days.
def test_history_and_requested_loan(row):
    assert row["history_days"] == 73
    assert row["requested_amount"] == 5000 and row["requested_term_days"] == 14


def test_income_windows(row):
    assert row["income_total_30"] == 30 * 200 and row["income_count_30"] == 30
    assert row["income_total_90"] == 73 * 200 and row["income_count_90"] == 73         # only 73 days exist
    assert row["income_active_day_share_30"] == pytest.approx(1.0)
    assert row["median_ticket_30"] == 200 and row["unique_senders_30"] == 6 and row["till_share_90"] == 1.0


def test_supplier_paybill_and_fee_counts(row):
    assert row["supplier_count_90"] == 10 and row["paybill_months_paid_90"] == 3
    assert row["fee_share_of_income_90"] == pytest.approx(10 * 11 / (73 * 200))


def test_fuliza_features(row):
    assert row["fuliza_draws_90"] == 5 and row["fuliza_amount_90"] == 1500
    assert row["fuliza_repay_lag_median_days_90"] == pytest.approx(2 + 10 / (24 * 60))   # 09:40 draw, 09:50 repayment two days on
    assert row["days_since_last_fuliza_draw"] == 6
    assert row["debt_service_ratio_90"] == pytest.approx(5 * 309 / (73 * 200))


def test_cash_flow_ratios(row):
    spend = 10 * 300 + 3 * 800 + 10 * 11                    # suppliers + paybills + fees. Agent cash-out is not spending
    assert row["net_cash_flow_ratio_90"] == pytest.approx((73 * 200 - spend) / (73 * 200))
    assert row["amount_to_income_30"] == pytest.approx(5000 / 6000)
    assert row["amount_to_avg_monthly_income_90"] == pytest.approx(5000 / (73 * 200 * 30 / 73))


def test_balance_never_near_zero_on_the_toy_vendor(row):
    assert row["near_zero_day_share_30"] == 0 and row["balance_min_eod_90"] > 100


def test_feature_count_and_no_label_or_slicing_columns(tx):
    apps = toy.make_apps(dates=(APP_DATE,))
    cols = set(Fe.build(tx, apps).columns)
    assert len(cols) == EXPECTED_N_FEATURES, sorted(cols)
    assert not cols & set(Fe.META) and not cols & {"persona", "gender", "defaulted", "latent_risk", "hidden_shock", "txn_type_true"}


# ---------------------------------------------------------------- the no-leakage rule
def test_changing_everything_after_the_application_date_changes_no_feature(tx, app):
    cut = pd.Timestamp(APP_DATE)
    later = tx.copy()
    after = later.completion_time >= cut
    later.loc[after, ["paid_in", "withdrawn", "balance"]] *= 10
    later.loc[after, "txn_type"] = "FULIZA_DRAW"
    a, b = Fe.build_row(tx, app), Fe.build_row(later, app)
    assert a.keys() == b.keys()
    for k in a:
        assert np.isclose(a[k], b[k], equal_nan=True), k


def test_transaction_exactly_at_midnight_of_the_application_date_is_left_out(tx, app):
    cut = pd.Timestamp(APP_DATE)
    base = Fe.build_row(tx, app)["income_total_30"]
    extra = tx.iloc[[0]].copy()
    extra["txn_type"], extra["paid_in"], extra["withdrawn"] = "TILL_PAYMENT_IN", 999.0, 0.0
    at_cut, just_before = extra.copy(), extra.copy()
    at_cut["completion_time"] = cut
    just_before["completion_time"] = cut - pd.Timedelta(seconds=1)
    assert Fe.build_row(pd.concat([tx, at_cut]), app)["income_total_30"] == base
    assert Fe.build_row(pd.concat([tx, just_before]), app)["income_total_30"] == base + 999


def test_leakage_test_passes_for_the_real_builder_and_catches_a_leaky_one(tx, monkeypatch):
    apps = toy.make_apps(dates=("2026-02-10", "2026-03-15", "2026-04-20"))
    assert Fe.leakage_test(tx, apps, n=3) == 0
    monkeypatch.setattr(Fe, "build_row", lambda g, a: {"total": float(g.paid_in.sum())})      # uses all rows: a leak
    assert Fe.leakage_test(tx, apps, n=3) > 0


# ---------------------------------------------------------------- other rules
def test_failed_payment_share_counts_failed_rows_but_income_ignores_them(tx, app):
    assert Fe.build_row(tx, app)["failed_payment_share_90"] == 0
    bad = tx.iloc[[0]].copy()
    bad["txn_type"], bad["is_failed"], bad["paid_in"], bad["withdrawn"] = "SEND_MONEY_OUT", True, 0.0, 0.0
    bad["completion_time"] = pd.Timestamp(APP_DATE) - pd.Timedelta(days=2)
    r = Fe.build_row(pd.concat([tx, bad]), app)
    assert r["failed_payment_share_90"] == pytest.approx(1 / (10 + 3 + 1))     # 10 supplier + 3 paybill payments + 1 failed
    assert r["income_total_90"] == 73 * 200


def test_a_failed_incoming_payment_is_not_counted_as_income(tx, app):
    base = Fe.build_row(tx, app)
    bad = tx.iloc[[0]].copy()
    bad["txn_type"], bad["is_failed"], bad["paid_in"], bad["withdrawn"] = "TILL_PAYMENT_IN", True, 0.0, 0.0
    bad["counterparty_id"] = "CP_FAILED"
    bad["completion_time"] = pd.Timestamp(APP_DATE) - pd.Timedelta(days=1, hours=-12)
    r = Fe.build_row(pd.concat([tx, bad]), app)
    for k in ("income_count_30", "income_count_90", "unique_senders_30", "unique_senders_90", "income_active_day_share_30",
              "median_ticket_30", "till_share_90"):
        assert r[k] == base[k], k


def test_application_before_any_history_gets_only_the_request_fields(tx):
    early = next(toy.make_apps(dates=("2025-12-01",)).itertuples(index=False))
    r = Fe.build_row(tx, early)
    assert r["history_days"] == 0 and set(r) == {"requested_amount", "requested_term_days", "history_days"}


def test_ratio_with_no_income_is_missing_not_infinite(tx):
    quiet = tx[tx.txn_type != "TILL_PAYMENT_IN"]
    r = Fe.build_row(quiet, next(toy.make_apps(dates=(APP_DATE,)).itertuples(index=False)))
    assert np.isnan(r["amount_to_income_30"]) and np.isnan(r["net_cash_flow_ratio_90"])
    assert not any(np.isinf(v) for v in r.values() if isinstance(v, float))


# ---------------------------------------------------------------- chunked build equals the in-memory build
def _write_chunks(path, frames):
    import pyarrow as pa
    import pyarrow.parquet as pq
    writer = None
    for f in frames:
        table = pa.Table.from_pandas(f, preserve_index=False)
        writer = writer or pq.ParquetWriter(path, table.schema)
        writer.write_table(table, row_group_size=len(table))
    writer.close()


def test_chunked_features_equal_in_memory_features(tmp_path):
    v1 = clean.clean(toy.make_vendor("V0001", days=100), as_of="2026-12-31")
    v2 = clean.clean(toy.make_vendor("V0002", days=100, daily_in=150.0), as_of="2026-12-31")
    apps = pd.concat([toy.make_apps("V0001", ("2026-03-01", "2026-04-01")), toy.make_apps("V0002", ("2026-03-10",))],
                     ignore_index=True)
    _write_chunks(str(tmp_path / "c.parquet"), [v1, v2])
    chunked, rg_of, pf = Fe.build_in_chunks(str(tmp_path / "c.parquet"), apps)
    whole = Fe.build(pd.concat([v1, v2], ignore_index=True), apps)
    pd.testing.assert_frame_equal(chunked.reset_index(drop=True)[whole.columns], whole.reset_index(drop=True), check_dtype=False)
    assert Fe.leakage_test_chunked(pf, rg_of, apps, n=3) == 0


def test_a_vendor_split_over_two_row_groups_stops_the_run(tmp_path):
    v = clean.clean(toy.make_vendor("V0001", days=100), as_of="2026-12-31")
    half = len(v) // 2
    _write_chunks(str(tmp_path / "c.parquet"), [v.iloc[:half], v.iloc[half:]])
    with pytest.raises(SystemExit, match="more than one row group"):
        Fe.build_in_chunks(str(tmp_path / "c.parquet"), toy.make_apps("V0001", ("2026-03-01",)))


# ---------------------------------------------------------------- the command-line stage end to end
def test_main_writes_features_and_the_column_list(tmp_path, monkeypatch):
    syn, interim, out = tmp_path / "syn", tmp_path / "interim", tmp_path / "processed"
    syn.mkdir(), interim.mkdir()
    ids = ["V0001", "V0002", "V0003"]
    txs = pd.concat([clean.clean(toy.make_vendor(v, days=100), as_of="2026-12-31") for v in ids], ignore_index=True)
    txs.to_parquet(interim / "transactions_clean.parquet", index=False)
    pd.concat([toy.make_apps(v, ("2026-03-01", "2026-04-01")) for v in ids], ignore_index=True).to_parquet(
        syn / "loan_applications.parquet", index=False)
    toy.make_vendors_table(ids).to_parquet(syn / "vendors.parquet", index=False)
    monkeypatch.setattr(sys, "argv", ["features.py", "--clean", str(interim), "--dir", str(syn), "--out", str(out),
                                      "--report", str(tmp_path / "feature_report.md")])
    Fe.main()
    cols = json.load(open(out / "feature_columns.json"))
    table = pd.read_parquet(out / "features.parquet")
    assert len(table) == 6 and len(cols["features"]) == EXPECTED_N_FEATURES
    assert set(cols["meta"]) == set(Fe.META) and not set(cols["features"]) & set(cols["meta"])
    assert {"persona", "gender", "business_type"} <= set(table.columns)
    assert "Leakage test: PASS" in (tmp_path / "feature_report.md").read_text()