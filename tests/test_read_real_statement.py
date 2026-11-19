"""Regression tests for clean.read_real_statement (mixed timestamp formats, skipped-row accounting) and for putting
same-second rows in running-balance order (pdf_statement.order_same_second_rows, used by read_statement).

Background: under pandas 3, a sheet that mixed 'YYYY-MM-DD HH:MM:SS' and 'YYYY-MM-DD HH:MM:SS.ffffff' lost every row
in the minority format without a message (the author's statement kept 476 of 3,099 transactions).
"""
import warnings

import numpy as np
import pandas as pd
import pytest

import clean
import pdf_statement as PS
import toy

SHEET_COLUMNS = ["Receipt No.", "Completion Time", "Details", "Transaction Status", "Paid In", "Withdrawn", "Balance"]


def _sheet(df, fmt="%Y-%m-%d %H:%M:%S"):
    """A toy statement as an M-Pesa sheet: newest first, every cell as text, withdrawals negative."""
    s = df.sort_values("completion_time", ascending=False)
    return pd.DataFrame({
        "Receipt No.": s.receipt_no, "Completion Time": s.completion_time.dt.strftime(fmt),
        "Details": s.details, "Transaction Status": s.transaction_status,
        "Paid In": s.paid_in.map(lambda v: f"{v:,.2f}" if v else ""),
        "Withdrawn": s.withdrawn.map(lambda v: f"-{v:,.2f}" if v else ""),
        "Balance": s.balance.map(lambda v: f"{v:,.2f}")}).reset_index(drop=True)


def _mixed(sheet):
    out = sheet.copy()
    i = np.arange(len(out))
    zero, frac = i % 3 == 1, (i % 3 == 2) & (i % 2 == 0)          # disjoint sets; the rest keep plain HH:MM:SS
    out.loc[zero, "Completion Time"] = out.loc[zero, "Completion Time"] + ".000000"
    out.loc[frac, "Completion Time"] = out.loc[frac, "Completion Time"] + ".250000"   # non-zero fractions too
    return out


def _write(sheet, path, preamble=True):
    rows = []
    if preamble:
        rows += [["MPESA FULL STATEMENT"] + [""] * 6, ["Customer Name: Test"] + [""] * 6]
    rows += [SHEET_COLUMNS] + sheet.astype(str).values.tolist()
    frame = pd.DataFrame(rows)
    if str(path).endswith(".csv"):
        frame.to_csv(path, header=False, index=False)
    else:
        frame.to_excel(path, header=False, index=False)
    return str(path)


def _read(path):
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)          # a clean file must not warn
        return clean.read_real_statement(path)


# ---------------------------------------------------------------- mixed timestamp formats
@pytest.mark.parametrize("ext", [".csv", ".xlsx"])
def test_mixed_time_formats_lose_no_row(tmp_path, ext):
    if ext == ".xlsx":
        pytest.importorskip("openpyxl")
    df = toy.make_vendor(days=40)
    sheet = _mixed(_sheet(df))
    assert sheet["Completion Time"].str.contains(r"\.\d{6}$").any() and (~sheet["Completion Time"].str.contains(r"\.")).any()
    got = _read(_write(sheet, tmp_path / f"mixed{ext}"))
    want = df.sort_values("completion_time").reset_index(drop=True)
    assert len(got) == len(want)
    assert got.receipt_no.tolist() == want.receipt_no.tolist()
    expected_times = pd.to_datetime(sheet.set_index("Receipt No.").loc[want.receipt_no, "Completion Time"], format="ISO8601")
    assert (got.completion_time.to_numpy() == expected_times.to_numpy()).all()       # fractions kept, nothing shifted
    for c in ("paid_in", "withdrawn", "balance"):
        np.testing.assert_allclose(got[c].to_numpy(), want[c].to_numpy())
    assert not [w for w in got.attrs["warnings"] if w["code"] in ("unparsed_rows", "unparsed_amounts")]


@pytest.mark.parametrize("first", ["plain", "fraction"])
def test_mostly_fractional_times_are_not_read_day_first(tmp_path, first):
    """When most cells carry .ffffff, the old day-first fallback read '2026-01-03' as 1 March. Days <= 12 are the trap."""
    df = toy.make_vendor(days=40)
    sheet = _sheet(df)
    frac = np.arange(len(sheet)) % 5 != 0                       # 80% fractional
    if first == "plain":
        frac[0] = False
    else:
        frac[0] = True
    sheet.loc[frac, "Completion Time"] = sheet.loc[frac, "Completion Time"] + ".000000"
    got = _read(_write(sheet, tmp_path / "frac.csv"))
    want = df.sort_values("completion_time").reset_index(drop=True)
    assert len(got) == len(want)
    assert (got.completion_time.to_numpy() == want.completion_time.to_numpy()).all()
    assert got.completion_time.is_monotonic_increasing


def test_day_first_statements_still_read_day_first(tmp_path):
    """The original fallback: a sheet in DD/MM/YYYY with days above 12 must still be read day-first."""
    df = toy.make_vendor(start="2026-01-13", days=15)
    got = _read(_write(_sheet(df, fmt="%d/%m/%Y %H:%M:%S"), tmp_path / "dmy.csv"))
    want = df.sort_values("completion_time").reset_index(drop=True)
    assert (got.completion_time.to_numpy() == want.completion_time.to_numpy()).all()


def test_single_format_output_is_unchanged(tmp_path):
    """The path every earlier statement took: one format, so the new retry never runs and the output is as before."""
    df = toy.make_vendor(days=40)
    got = _read(_write(_sheet(df), tmp_path / "plain.csv"))
    want = df.sort_values("completion_time").reset_index(drop=True)
    assert list(got.columns) == ["receipt_no", "completion_time", "details", "transaction_status", "paid_in", "withdrawn",
                                 "balance", "vendor_id"]
    assert got.receipt_no.tolist() == want.receipt_no.tolist()
    assert (got.completion_time.to_numpy() == want.completion_time.to_numpy()).all()
    assert got.attrs["warnings"] == []


# ---------------------------------------------------------------- never drop rows silently
def test_page_clutter_is_accounted_for(tmp_path):
    df = toy.make_vendor(days=20)
    sheet = _sheet(df)
    rows = []
    for i, r in enumerate(sheet.astype(str).values.tolist()):
        rows.append(r)
        if i % 10 == 9:                                       # page break: blank row, footer text, repeated header
            rows += [[""] * 7, ["Disclaimer: for information only."] + [""] * 6, SHEET_COLUMNS]
    p = _write(pd.DataFrame(rows, columns=SHEET_COLUMNS), tmp_path / "pages.csv")
    got = _read(p)
    assert len(got) == len(df)
    info = next(w for w in got.attrs["warnings"] if w["code"] == "skipped_non_transaction_rows")
    pages = len(sheet) // 10
    assert info["breakdown"] == {"header_repeats": pages, "blank": pages, "text_only": pages}


def test_unparseable_timestamp_warns_with_the_count(tmp_path):
    df = toy.make_vendor(days=20)
    sheet = _sheet(df)
    sheet.loc[3, "Completion Time"] = "31/02/2026 25:61"      # impossible date and time
    sheet.loc[7, "Completion Time"] = "yesterday"
    with pytest.warns(UserWarning, match="2 rows look like transactions"):
        got = clean.read_real_statement(_write(sheet, tmp_path / "bad.csv"))
    assert len(got) == len(df) - 2
    w = next(w for w in got.attrs["warnings"] if w["code"] == "unparsed_rows")
    assert w["count"] == 2
    assert "31/02" not in w["message"] and "yesterday" not in w["message"]          # counts only, no content


def test_missing_balance_warns(tmp_path):
    sheet = _sheet(toy.make_vendor(days=10))
    sheet.loc[2, "Balance"] = ""
    with pytest.warns(UserWarning, match="1 rows look like transactions"):
        got = clean.read_real_statement(_write(sheet, tmp_path / "nobal.csv"))
    assert next(w for w in got.attrs["warnings"] if w["code"] == "unparsed_rows")["count"] == 1


def test_unreadable_amount_warns(tmp_path):
    sheet = _sheet(toy.make_vendor(days=10))
    i = sheet.index[sheet["Paid In"] != ""][0]
    sheet.loc[i, "Paid In"] = "1.2O0"                         # letter O instead of zero
    with pytest.warns(UserWarning, match="not a number"):
        got = clean.read_real_statement(_write(sheet, tmp_path / "amt.csv"))
    assert next(w for w in got.attrs["warnings"] if w["code"] == "unparsed_amounts")["count"] == 1


def test_read_statement_passes_the_counts_on(tmp_path):
    sheet = _sheet(toy.make_vendor(days=10))
    sheet.loc[1, "Completion Time"] = "not a time"
    with pytest.warns(UserWarning):
        got = PS.read_statement(_write(sheet, tmp_path / "s.csv"))
    assert "unparsed_rows" in [w["code"] for w in got.attrs["warnings"]]


# ---------------------------------------------------------------- same-second rows
def _same_second_statement():
    """Toy statement where every fee shares the second of its withdrawal and is listed BEFORE it, as statements do."""
    df = toy.make_vendor(days=60)
    fee = df.details.eq("Customer Withdrawal Charge")
    df.loc[fee, "completion_time"] = df.loc[fee, "completion_time"] - pd.Timedelta(minutes=1)
    df = toy.recompute_balance(df)                            # true order: withdrawal, then fee (same second)
    true = df.copy()
    idx = list(df.index)
    for i in df.index[fee]:                                   # list the fee before its withdrawal
        a, b = idx.index(i - 1), idx.index(i)
        idx[a], idx[b] = idx[b], idx[a]
    return true, df.loc[idx].reset_index(drop=True)


def _breaks(d):
    return int((((d.balance.shift(1) + d.paid_in - d.withdrawn) - d.balance).abs() >= 0.01).sum())


def test_same_second_rows_are_put_in_balance_order():
    true, listed = _same_second_statement()
    assert _breaks(true) == 0 and _breaks(listed) > 0
    fixed, moved = PS.order_same_second_rows(listed)
    assert moved == int(true.details.eq("Customer Withdrawal Charge").sum())
    assert _breaks(fixed) == 0
    assert fixed.receipt_no.tolist() == true.receipt_no.tolist()
    assert sorted(fixed.receipt_no) == sorted(listed.receipt_no)                     # a permutation, nothing lost


def test_rows_already_in_order_are_left_alone():
    true, _ = _same_second_statement()
    fixed, moved = PS.order_same_second_rows(true)
    assert moved == 0 and fixed is true
    plain = toy.make_vendor(days=30)                          # no shared seconds at all
    assert PS.order_same_second_rows(plain)[0] is plain
