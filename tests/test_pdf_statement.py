"""Tests for src/pdf_statement.py: the PDF reader, the read_statement dispatcher and the xlsx/csv time fix in clean.py.

The PDFs are drawn with reportlab from a toy statement in the M-Pesa layout: customer block and summary table on page 1,
page header and footer on every page, the column header repeated per page, wrapped details, newest first, two pages.
Names and numbers in them are made up. Optional real-file test: set CREDIT_PDF (and CREDIT_PDF_PASSWORD if needed).
"""
import os
import re
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("reportlab")
pytest.importorskip("pdfplumber")
pytest.importorskip("pypdf")

import clean  # noqa: E402
import pdf_statement as PS  # noqa: E402
import toy  # noqa: E402

NAME, PHONE, OTHER_NAME = "JANE TESTER", "0712345678", "JOHN SAMPLE"
PASSWORD = "s3cret-pass"
PERSONAL = (NAME, PHONE, OTHER_NAME, "0798")


def statement_frame(days=24):
    """Toy statement with send-money wording that carries a phone number and a name."""
    df = toy.make_vendor(days=days)
    till = df.index[df.details.str.startswith("Merchant Payment from")]
    for k, i in enumerate(till[::4]):
        df.loc[i, "details"] = f"Funds received from 0798{k:06d} - {OTHER_NAME} AND SONS GENERAL SUPPLIES"
    return df


def make_pdf(df, path, wrap=26):
    """Draw df newest first in an M-Pesa-like layout. Returns the number of pages."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    W, H = A4
    X = {"receipt": 30, "time": 92, "details": 172, "status": 318}
    R = {"paid_in": 440, "withdrawn": 500, "balance": 565}          # right edges of the amount columns
    lh, bottom = 9, 70
    rows = df.sort_values("completion_time", ascending=False)
    pages = []                                                     # lay out first, so footers know the page count
    page, y = [], H - 260
    for r in rows.itertuples():
        lines = textwrap.wrap(r.details, wrap) or [""]
        need = lh * len(lines) + 3
        if y - need < bottom:
            pages.append(page)
            page, y = [], H - 110
        page.append((y, r, lines))
        y -= need
    pages.append(page)

    def header_row(c, y):
        c.setFont("Helvetica-Bold", 7)
        c.drawString(X["receipt"], y, "Receipt No.")
        c.drawString(X["time"], y, "Completion Time")
        c.drawString(X["details"], y, "Details")
        c.drawString(X["status"], y, "Transaction Status")
        c.drawRightString(R["paid_in"], y, "Paid In")
        c.drawRightString(R["withdrawn"], y, "Withdrawn")
        c.drawRightString(R["balance"], y, "Balance")
        c.setFont("Helvetica", 7)

    c = canvas.Canvas(str(path), pagesize=A4)
    for n, page in enumerate(pages, start=1):
        c.setFont("Helvetica-Bold", 11)
        c.drawString(30, H - 40, "M-PESA STATEMENT")
        c.setFont("Helvetica", 8)
        c.drawString(30, H - 54, f"Customer Name: {NAME}")
        if n == 1:
            c.drawString(30, H - 66, f"Mobile Number: {PHONE}")
            c.drawString(30, H - 78, "Statement Period: 01 Jan 2026 - 31 Jan 2026")
            c.setFont("Helvetica-Bold", 8)
            c.drawString(30, H - 105, "SUMMARY")
            c.drawString(30, H - 118, "TRANSACTION TYPE")
            c.drawRightString(300, H - 118, "PAID IN")
            c.drawRightString(380, H - 118, "PAID OUT")
            c.setFont("Helvetica", 8)
            for k, (t, a, b) in enumerate((("SEND MONEY", "0.00", "1,250.00"), ("RECEIVED MONEY", "12,400.00", "0.00"),
                                           ("AGENT WITHDRAWAL", "0.00", "1,500.00"), ("TOTAL:", "12,400.00", "2,750.00"))):
                c.drawString(30, H - 131 - 12 * k, t)
                c.drawRightString(300, H - 131 - 12 * k, a)
                c.drawRightString(380, H - 131 - 12 * k, b)
            c.setFont("Helvetica-Bold", 8)
            c.drawString(30, H - 200, "DETAILED STATEMENT")
            header_row(c, H - 240)
        else:
            header_row(c, H - 95)
        for y, r, lines in page:
            c.drawString(X["receipt"], y, r.receipt_no)
            c.drawString(X["time"], y, pd.Timestamp(r.completion_time).strftime("%Y-%m-%d %H:%M:%S"))
            for k, t in enumerate(lines):
                c.drawString(X["details"], y - lh * k, t)
            c.drawString(X["status"], y, r.transaction_status)
            if r.paid_in:
                c.drawRightString(R["paid_in"], y, f"{r.paid_in:,.2f}")
            if r.withdrawn:
                c.drawRightString(R["withdrawn"], y, f"-{r.withdrawn:,.2f}")
            c.drawRightString(R["balance"], y, f"{r.balance:,.2f}")
        c.setFont("Helvetica", 6)
        c.drawString(30, 40, "Disclaimer: This record is produced for your information only and is not valid for any legal purpose.")
        c.drawCentredString(W / 2, 28, f"Page {n} of {len(pages)}")
        c.showPage()
    c.save()
    return len(pages)


def encrypt_copy(src, dst, password=PASSWORD):
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter(clone_from=PdfReader(str(src)))
    w.encrypt(user_password=password, algorithm="AES-128")
    with open(dst, "wb") as f:
        w.write(f)


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory):
    d = tmp_path_factory.mktemp("pdf")
    df = statement_frame()
    plain, locked = d / "statement.pdf", d / "statement_locked.pdf"
    n_pages = make_pdf(df, plain)
    encrypt_copy(plain, locked)
    return {"df": df, "plain": plain, "locked": locked, "pages": n_pages, "dir": d}


# ---------------------------------------------------------------- round trip
def test_the_test_pdf_is_realistic(pdfs):
    assert pdfs["pages"] == 2
    assert pdfs["df"].details.map(lambda s: len(s) > 26).any()        # some details wrap


def test_round_trip_matches_the_statement(pdfs):
    got = PS.read_pdf_statement(pdfs["plain"])
    want = pdfs["df"].sort_values("completion_time").reset_index(drop=True)
    assert list(got.columns) == PS.COLUMNS
    assert len(got) == len(want)
    assert got.completion_time.is_monotonic_increasing
    assert (got.receipt_no.to_numpy() == want.receipt_no.to_numpy()).all()
    assert (got.completion_time.to_numpy() == want.completion_time.to_numpy()).all()
    for c in ("paid_in", "withdrawn", "balance"):
        np.testing.assert_allclose(got[c].to_numpy(), want[c].to_numpy(), atol=1e-9)
    assert (got.vendor_id == "REAL_STATEMENT").all()
    assert not [w for w in got.attrs["warnings"] if w["code"] == "balance_breaks"]


def test_wrapped_details_are_joined_and_classified_like_the_original(pdfs):
    got = PS.read_pdf_statement(pdfs["plain"])
    want = pdfs["df"].sort_values("completion_time").reset_index(drop=True)
    long = want.details.str.len() > 26
    assert got.loc[long & ~want.details.str.contains(r"\d{9}"), "details"].tolist() == \
        want.loc[long & ~want.details.str.contains(r"\d{9}"), "details"].tolist()
    a, b = clean.classify_details(got.details).txn_type, clean.classify_details(want.details).txn_type
    assert (a.to_numpy() == b.to_numpy()).all()


def test_phone_numbers_are_masked_and_counterparties_hashed(pdfs):
    got = PS.read_pdf_statement(pdfs["plain"])
    assert not got.details.str.contains(r"\d{9,}").any()
    assert got.details.str.contains(re.escape(PS.MASK)).any()
    sent = got[got.details.str.startswith("Funds received from")]
    assert sent.counterparty_id.str.match(r"^CP_[0-9a-f]{10}$").all()
    assert sent.counterparty_id.nunique() == len(sent)               # different numbers stay different


def test_summary_table_header_and_footer_are_not_rows(pdfs):
    got = PS.read_pdf_statement(pdfs["plain"])
    joined = " ".join(got.details)
    for junk in ("SUMMARY", "TOTAL", "Disclaimer", "Page 1", "Customer Name", "M-PESA STATEMENT"):
        assert junk not in joined


def test_oldest_first_pdf_reads_the_same(pdfs, tmp_path):
    from reportlab.lib.pagesizes import A4  # noqa: F401  (make_pdf draws newest first; reverse the input to test the flip)
    a = PS.read_pdf_statement(pdfs["plain"])
    df = pdfs["df"].copy()
    df["completion_time"] = df.completion_time.max() - (df.completion_time - df.completion_time.min())  # reversed times
    p = tmp_path / "rev.pdf"
    make_pdf(df, p)
    b = PS.read_pdf_statement(p)
    assert b.completion_time.is_monotonic_increasing and len(a) == len(b)


# ---------------------------------------------------------------- passwords and errors
def test_password_protected_pdf(pdfs):
    a = PS.read_pdf_statement(pdfs["plain"])
    b = PS.read_pdf_statement(pdfs["locked"], password=PASSWORD)
    pd.testing.assert_frame_equal(a, b)


def test_missing_or_wrong_password_raises(pdfs):
    with pytest.raises(PS.PasswordError, match="password-protected"):
        PS.read_pdf_statement(pdfs["locked"])
    with pytest.raises(PS.PasswordError, match="not correct") as e:
        PS.read_pdf_statement(pdfs["locked"], password="wrong")
    assert "wrong" not in str(e.value)


def test_pdf_without_text_raises_a_clear_error(tmp_path):
    from reportlab.pdfgen import canvas
    p = tmp_path / "image_only.pdf"
    c = canvas.Canvas(str(p))
    c.rect(50, 50, 300, 300, fill=1)
    c.showPage()
    c.save()
    with pytest.raises(PS.NoTextLayerError, match="no readable text"):
        PS.read_pdf_statement(p)
    # the message tells the user what to do: ask for the Excel or CSV version (through the dispatcher too)
    with pytest.raises(PS.NoTextLayerError) as e:
        PS.read_statement(p)
    msg = str(e.value)
    assert "Please ask for the Excel (.xlsx) or CSV version of your M-Pesa statement" in msg
    assert "scanned image" in msg and "OCR" in msg and "not supported" in msg


def test_pdf_without_a_transaction_table_raises(tmp_path):
    from reportlab.pdfgen import canvas
    p = tmp_path / "letter.pdf"
    c = canvas.Canvas(str(p))
    c.drawString(72, 700, "Dear customer, this is not a statement.")
    c.showPage()
    c.save()
    with pytest.raises(PS.StatementError, match="No transaction table"):
        PS.read_pdf_statement(p)


def test_nothing_personal_is_printed(pdfs, capsys):
    PS.read_pdf_statement(pdfs["plain"])
    PS.read_pdf_statement(pdfs["locked"], password=PASSWORD)
    for bad in (None, "wrong"):
        with pytest.raises(PS.PasswordError):
            PS.read_pdf_statement(pdfs["locked"], password=bad)
    out = capsys.readouterr()
    text = out.out + out.err
    for s in PERSONAL + (PASSWORD,):
        assert s not in text


def test_balance_breaks_are_counted_not_dropped(tmp_path):
    df = statement_frame(days=10)
    df.loc[4, "balance"] += 100.0
    p = tmp_path / "broken.pdf"
    make_pdf(df, p)
    got = PS.read_pdf_statement(p)
    assert len(got) == len(df)
    w = next(w for w in got.attrs["warnings"] if w["code"] == "balance_breaks")
    assert w["count"] == 2


# ---------------------------------------------------------------- dispatcher and helpers
def _sheet(df):
    return df.sort_values("completion_time", ascending=False).rename(columns={
        "receipt_no": "Receipt No.", "completion_time": "Completion Time", "details": "Details",
        "transaction_status": "Transaction Status", "paid_in": "Paid In", "withdrawn": "Withdrawn", "balance": "Balance"})[
        ["Receipt No.", "Completion Time", "Details", "Transaction Status", "Paid In", "Withdrawn", "Balance"]]


def test_read_statement_dispatches_and_matches_the_pdf_schema(pdfs, tmp_path):
    csv = tmp_path / "s.csv"
    _sheet(pdfs["df"]).to_csv(csv, index=False)
    a, b = PS.read_statement(pdfs["plain"]), PS.read_statement(csv)
    assert list(a.columns) == list(b.columns) == PS.COLUMNS
    assert dict(a.dtypes.astype(str)) == dict(b.dtypes.astype(str))
    pd.testing.assert_frame_equal(a[["receipt_no", "completion_time", "paid_in", "withdrawn", "balance"]],
                                  b[["receipt_no", "completion_time", "paid_in", "withdrawn", "balance"]])
    # same columns as clean.read_real_statement, plus counterparty_id
    base = clean.read_real_statement(str(csv))
    assert [c for c in PS.COLUMNS if c != "counterparty_id"] == list(base.columns)
    (tmp_path / "s.txt").write_text("x")
    with pytest.raises(PS.StatementError, match="Unsupported"):
        PS.read_statement(tmp_path / "s.txt")
    with pytest.raises(PS.StatementError, match="not found"):
        PS.read_statement(tmp_path / "missing.pdf")


def test_letter_only_receipts_are_read(tmp_path):
    df = statement_frame(days=8)
    df.loc[[2, 5], "receipt_no"] = ["TCJABCDEFG", "SKLMNOPQRS"]   # real statements have a few receipts without digits
    p = tmp_path / "letters.pdf"
    make_pdf(df, p)
    got = PS.read_pdf_statement(p)
    assert len(got) == len(df) and {"TCJABCDEFG", "SKLMNOPQRS"} <= set(got.receipt_no)


def test_mask_numbers():
    assert PS.mask_numbers("Customer Transfer to 0712345678 - X") == f"Customer Transfer to {PS.MASK} - X"
    assert PS.mask_numbers("to 0722***123 NAME") == f"to {PS.MASK} NAME"
    assert PS.mask_numbers("to 0722 123 456 NAME") == f"to {PS.MASK} NAME"
    assert PS.mask_numbers("Pay Bill to 888880 - KPLC Acc. 1234") == "Pay Bill to 888880 - KPLC Acc. 1234"
    assert PS.counterparty_hash("") == "" and PS.counterparty_hash(" a  b ") == PS.counterparty_hash("A B")


# ---------------------------------------------------------------- the real statement (opt-in, never committed)
def test_real_pdf_statement_if_provided():
    path = os.environ.get("CREDIT_PDF")
    if not path:
        pytest.skip("set CREDIT_PDF to a real statement PDF to run this test")
    try:
        df = PS.read_pdf_statement(Path(path), password=os.environ.get("CREDIT_PDF_PASSWORD"))
    except PS.NoTextLayerError:
        pytest.skip("this PDF has no text layer (scanned or re-printed); only the original M-Pesa PDF can be read")
    assert len(df) > 0 and list(df.columns) == PS.COLUMNS
    assert df.completion_time.is_monotonic_increasing
    assert not df.details.str.contains(r"\d{9,}").any()
