"""Tests for stage 2, src/clean.py: classification of `details`, the validation flags, and chunked cleaning."""
import numpy as np
import pandas as pd
import pytest

import clean
import toy


# ---------------------------------------------------------------- classification (wording from docs/data_dictionary.md)
WORDING = [
    ("Merchant Payment from CP_0412", "TILL_PAYMENT_IN"),
    ("Funds received from - CP_0412", "SEND_MONEY_IN"),
    ("Customer Transfer to - CP_0412", "SEND_MONEY_OUT"),
    ("Merchant Payment to 123456 - CP_0412", "BUY_GOODS_OUT"),
    ("Pay Bill to 888880 - CP_0412 Acc. 1234", "PAYBILL_OUT"),
    ("Airtime Purchase", "AIRTIME_OUT"),
    ("Customer Withdrawal At Agent - AG01", "WITHDRAW_AGENT"),
    ("Deposit of Funds at Agent - AG01", "DEPOSIT_AGENT"),
    ("OverDraft of Credit Party", "FULIZA_DRAW"),
    ("OD Loan Repayment to 232323 - M-PESA Overdraw", "FULIZA_REPAY"),
    ("Customer Transfer of Funds Charge", "FEE"),
    ("Customer Withdrawal Charge", "FEE"),
    ("Pay Bill Charge", "FEE"),
    ("Reversal - Customer Transfer to - CP_0412", "REVERSAL"),
]


@pytest.mark.parametrize("details,expected", WORDING)
def test_each_wording_gets_its_type(details, expected):
    assert clean.classify_details(pd.Series([details])).txn_type.iloc[0] == expected


def test_ids_and_numbers_do_not_change_the_type():
    a = clean.classify_details(pd.Series(["Merchant Payment from CP_0001", "Merchant Payment from CP_9f3a2"]))
    assert set(a.txn_type) == {"TILL_PAYMENT_IN"}


def test_failed_prefix_keeps_the_type_and_sets_is_failed():
    r = clean.classify_details(pd.Series(["Failed - Customer Transfer to - CP_0001"]))
    assert r.txn_type.iloc[0] == "SEND_MONEY_OUT" and bool(r.is_failed.iloc[0])


def test_payment_funded_by_fuliza_is_marked_but_the_draw_and_fees_are_not():
    r = clean.classify_details(pd.Series(["Customer Transfer Fuliza MPesa to - CP_0001", "OverDraft of Credit Party",
                                          "Customer Transfer Fuliza MPesa Charge"]))
    assert r.txn_type.tolist() == ["SEND_MONEY_OUT", "FULIZA_DRAW", "FEE"]
    assert r.fuliza_funded.tolist() == [True, False, False]


def test_unknown_wording_is_kept_and_flagged_by_direction():
    raw = toy.make_vendor(days=20)
    extra = raw.iloc[[0, 1]].copy()
    extra["details"] = "Some New Product Wording"
    extra["paid_in"], extra["withdrawn"] = [50.0, 0.0], [0.0, 60.0]
    extra["completion_time"] = raw.completion_time.max() + pd.to_timedelta([1, 2], unit="h")
    extra["receipt_no"] = ["X1", "X2"]
    out = clean.clean(pd.concat([raw, extra], ignore_index=True), as_of="2026-12-31")
    new = out[out.details == "Some New Product Wording"]
    assert sorted(new.txn_type) == ["OTHER_IN", "OTHER_OUT"] and new.flag_unknown_wording.all()


# ---------------------------------------------------------------- a clean statement
def test_clean_statement_raises_no_flag_and_matches_the_truth(clean_vendor):
    assert not clean_vendor[clean.FLAGS].any().any()
    assert (clean_vendor.txn_type == clean_vendor.txn_type_true).all()


def test_no_rows_are_deleted_and_columns_are_added(raw_vendor, clean_vendor):
    assert len(clean_vendor) == len(raw_vendor)
    assert {"txn_type", "direction", "is_failed", "fuliza_funded"} <= set(clean_vendor.columns)


def test_direction_follows_the_amounts_and_failed_rows_have_none():
    raw = toy.make_vendor(days=10)
    fail = raw.iloc[[0]].copy()
    fail["details"], fail["transaction_status"] = "Failed - Customer Transfer to - CP_0001", "Failed"
    fail["paid_in"] = fail["withdrawn"] = 0.0
    fail["receipt_no"] = "FAIL1"
    fail["completion_time"] = raw.completion_time.max() + pd.Timedelta(hours=1)
    fail["balance"] = raw.balance.iloc[-1]
    out = clean.clean(pd.concat([raw, fail], ignore_index=True), as_of="2026-12-31")
    assert out.loc[out.receipt_no == "FAIL1", "direction"].iloc[0] == "none"
    assert out.loc[out.receipt_no == "FAIL1", "is_failed"].iloc[0]
    assert not out.flag_balance_break.any()                              # a failed row leaves the balance unchanged
    assert set(out.direction) <= {"in", "out", "none"}


def test_newest_first_input_is_sorted_oldest_first_without_flags(raw_vendor):
    out = clean.clean(raw_vendor.iloc[::-1].reset_index(drop=True), as_of="2026-12-31")
    assert out.completion_time.is_monotonic_increasing
    assert not out[clean.FLAGS].any().any()


# ---------------------------------------------------------------- each validation rule fires (and only when it should)
def _flags_after(mutate, as_of="2026-12-31"):
    raw = toy.make_vendor(days=60)
    mutate(raw)
    return clean.clean(raw, as_of=as_of)


def test_rule1_both_amounts():
    def m(df): df.loc[10, ["paid_in", "withdrawn"]] = [100.0, 50.0]
    assert _flags_after(m).flag_both_amounts.sum() == 1


def test_rule2_balance_break():
    def m(df): df.loc[20, "balance"] += 5.0
    out = _flags_after(m)
    assert out.flag_balance_break.sum() >= 1
    assert out.flag_balance_break.iloc[20]


def test_rule3_duplicate_receipt_flags_the_second_occurrence_only():
    def m(df): df.loc[7, "receipt_no"] = df.loc[3, "receipt_no"]
    out = _flags_after(m)
    assert out.flag_duplicate_receipt.sum() == 1 and out.flag_duplicate_receipt.iloc[7]


def test_rule4_time_not_increasing():
    def m(df): df.loc[9, "completion_time"] = df.loc[8, "completion_time"]
    assert _flags_after(m).flag_time_not_increasing.sum() == 1


def test_rule5_negative_values():
    def m(df): df.loc[15, "balance"] = -1.0
    assert _flags_after(m).flag_negative.sum() == 1


def test_future_dates_depend_on_the_as_of_date():
    raw = toy.make_vendor(days=60)
    cutoff = raw.completion_time.iloc[30]
    out = clean.clean(raw, as_of=cutoff)
    assert out.flag_future_date.sum() == (raw.completion_time > cutoff).sum() > 0


def test_cleaning_does_not_use_the_truth_column(raw_vendor):
    wrong = raw_vendor.copy()
    wrong["txn_type_true"] = "AIRTIME_OUT"
    out = clean.clean(wrong, as_of="2026-12-31")
    assert (out.txn_type == clean.clean(raw_vendor, as_of="2026-12-31").txn_type).all()


# ---------------------------------------------------------------- report
def test_report_counts_rows_and_agreement(clean_vendor):
    text = clean.report(clean_vendor)
    assert f"{len(clean_vendor):,} lines" in text and "Agreement: 100.0000%" in text and "flag_balance_break" in text


# ---------------------------------------------------------------- chunked cleaning (whole vendors per row group)
def _write_chunks(path, frames):
    import pyarrow as pa
    import pyarrow.parquet as pq
    writer = None
    for f in frames:
        table = pa.Table.from_pandas(f, preserve_index=False)
        writer = writer or pq.ParquetWriter(path, table.schema)
        writer.write_table(table, row_group_size=len(table))
    writer.close()


def test_chunked_cleaning_keeps_one_vendor_per_row_group_and_all_rows(tmp_path):
    import pyarrow.parquet as pq
    v1, v2 = toy.make_vendor("V0001", days=50), toy.make_vendor("V0002", days=70)
    _write_chunks(str(tmp_path / "tx.parquet"), [v1, v2])
    stats, out_path = clean.clean_file_in_chunks(str(tmp_path / "tx.parquet"), str(tmp_path / "out"), as_of="2026-12-31")
    pf = pq.ParquetFile(out_path)
    assert pf.num_row_groups == 2 and stats["n"] == len(v1) + len(v2) == pf.metadata.num_rows
    owners = [set(pf.read_row_group(i, columns=["vendor_id"]).to_pandas().vendor_id) for i in range(2)]
    assert owners == [{"V0001"}, {"V0002"}]
    assert stats["global_duplicate_receipts"] == 0 and sum(stats["flags"].values()) == 0


def test_chunked_cleaning_finds_a_receipt_repeated_across_chunks(tmp_path):
    v1, v2 = toy.make_vendor("V0001", days=30), toy.make_vendor("V0002", days=30)
    v2.loc[0, "receipt_no"] = v1.loc[0, "receipt_no"]
    _write_chunks(str(tmp_path / "tx.parquet"), [v1, v2])
    stats, _ = clean.clean_file_in_chunks(str(tmp_path / "tx.parquet"), str(tmp_path / "out"), as_of="2026-12-31")
    assert stats["global_duplicate_receipts"] == 1


# ---------------------------------------------------------------- real statement reader
def test_real_statement_reader_finds_header_parses_numbers_and_orders_oldest_first(tmp_path):
    pytest.importorskip("openpyxl")
    rows = [["MPESA FULL STATEMENT", None, None, None, None, None, None],
            ["Customer Name: Test", None, None, None, None, None, None],
            ["Receipt No", "Completion Time", "Details", "Transaction Status", "Paid in", "Withdrawn", "Balance"],
            ["R2", "2026-03-02 10:00:00", "Merchant Payment from CP_1", "Completed", "1,200.00", "", "2,200.00"],
            ["R1", "2026-03-01 09:00:00", "Funds received from - CP_2", "Completed", "1,000.00", "", "1,000.00"]]
    path = str(tmp_path / "statement.xlsx")
    pd.DataFrame(rows).to_excel(path, header=False, index=False)
    df = clean.read_real_statement(path)
    assert df.receipt_no.tolist() == ["R1", "R2"]                       # newest-first file becomes oldest first
    assert df.paid_in.tolist() == [1000.0, 1200.0] and df.balance.tolist() == [1000.0, 2200.0]
    assert (df.vendor_id == "REAL_STATEMENT").all()