"""Read an M-Pesa statement (xlsx or csv; PDF only with a text layer) into the transactions schema used by src/clean.py.

    read_pdf_statement(path, password=None) -> DataFrame
    read_statement(path, password=None)     -> DataFrame   (dispatches on .pdf / .xlsx / .xls / .csv)

SUPPORTED INPUTS: Excel (.xlsx/.xls) and CSV statements. PDF only when it has a text layer. Real M-Pesa PDF statements
are scanned images with no text layer (checked on two statements), so read_pdf_statement CANNOT read them; it raises
NoTextLayerError, whose message asks the user for the Excel or CSV version. Reading images needs OCR, which is out of
scope (future work). The PDF reader is validated only on generated text PDFs (tests/test_pdf_statement.py).

Output columns, oldest first: the columns clean.read_real_statement returns (receipt_no, completion_time, details,
transaction_status, paid_in, withdrawn, balance, vendor_id="REAL_STATEMENT") plus counterparty_id, which
features.build_row needs and read_real_statement does not provide. Warnings (counts only) are in df.attrs["warnings"].

Assumed PDF layout for a text PDF (modelled on the Safaricom "M-PESA STATEMENT", not checked against an original with
a text layer): page 1 starts with customer details and a summary table, then a
"DETAILED STATEMENT" table with the columns Receipt No. | Completion Time | Details | Transaction Status | Paid In |
Withdrawn | Balance. Rows are newest first, details may wrap onto following lines (top-aligned cells), the column
header may repeat on every page, and each page may carry a header and a footer ("Page 1 of 9", disclaimer).
The reader works from word positions (pdfplumber), not from ruled lines, so it also reads statements without a grid.

A PDF without a text layer (scanned, or re-printed with "Microsoft Print to PDF", which turns text into shapes) cannot be
read without OCR. The reader raises NoTextLayerError for those and asks for the Excel or CSV version of the statement.

Privacy: nothing in this module prints or logs statement content. Digit runs of 9 or more characters (phone, ID and
account numbers, including partly starred ones such as 0722***123) are replaced by "*********" in details, and
counterparty_id is a short hash of the counterparty text (taken before masking, so two numbers stay distinct).
"""
import hashlib
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean  # noqa: E402

VENDOR_ID = "REAL_STATEMENT"
COLUMNS = ["receipt_no", "completion_time", "details", "transaction_status", "paid_in", "withdrawn", "balance",
           "vendor_id", "counterparty_id"]
MASK = "*********"
_DIGIT_RUN = re.compile(r"\+?[0-9*](?:[0-9*]| (?=[0-9*]))*")
_CP_SPLIT = re.compile(r"\b(?:to|from)\b", re.I)
_RECEIPT = re.compile(r"^(?=.*[A-Z])[A-Z0-9]{8,12}$")       # some real receipts are letters only
_AMOUNT = re.compile(r"^\(?[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?-?$")
_FOOTER = re.compile(r"^(page\s*\d+\s*(of\s*\d+)?|\d+\s*of\s*\d+|disclaimer\b.*)$", re.I)
_HASH_SALT = "mpesa-credit-scoring/counterparty"
NO_TEXT_MESSAGE = ("This PDF has no readable text: it is a scanned image (M-Pesa PDF statements usually are) or was "
                   "re-printed, and reading images (OCR) is not supported. Please ask for the Excel (.xlsx) or CSV version "
                   "of your M-Pesa statement and upload that instead.")


class StatementError(ValueError):
    """The statement cannot be read. The message is safe to show to the user (no statement content)."""


class PasswordError(StatementError):
    pass


class NoTextLayerError(StatementError):
    pass


# ------------------------------------------------------------------ privacy helpers
def mask_numbers(text: str) -> str:
    """Replace runs of 9+ digit/star characters (spaces inside allowed) that contain a digit by '*********'."""
    def sub(m):
        s = m.group(0)
        core = s.replace(" ", "").lstrip("+")
        return MASK if len(core) >= 9 and any(c.isdigit() for c in core) else s
    return _DIGIT_RUN.sub(sub, text or "")


def counterparty_text(details: str) -> str:
    """The part after the last 'to'/'from' ("Customer Transfer to 0722***123 - JANE" -> "0722***123 - JANE")."""
    parts = _CP_SPLIT.split(details or "")
    return parts[-1].strip(" -\t") if len(parts) > 1 else ""


def counterparty_hash(text: str) -> str:
    """Short stable id for a counterparty. '' when there is none."""
    t = re.sub(r"\s+", " ", (text or "").strip().upper())
    if not t:
        return ""
    return "CP_" + hashlib.sha256(f"{_HASH_SALT}|{t}".encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ shared finishing and validation
def order_same_second_rows(df: pd.DataFrame) -> tuple:
    """Reorder rows that share a completion time so the running balance follows on, where it can.

    A statement lists a Fuliza draw, a payment and its charge with the same second, and their order inside that second
    is not the order they happened in (on the author's statement, reordering only inside same-second groups removed 775
    of 804 balance breaks). Rows are only permuted inside a group of equal times, greedily: from the balance before the
    group, take the first remaining row that continues the chain, else keep file order. A group that already
    reconciles keeps its order. Expects oldest-first input. Returns (frame, number of groups changed)."""
    t = df.completion_time.to_numpy()
    if len(df) < 2 or not (t[1:] == t[:-1]).any():
        return df, 0
    bal = df.balance.to_numpy(dtype=float)
    delta = (df.paid_in - df.withdrawn).to_numpy(dtype=float)
    order, moved, i, n = [], 0, 0, len(df)
    while i < n:
        j = i + 1
        while j < n and t[j] == t[i]:
            j += 1
        group = list(range(i, j))
        if len(group) > 1:
            prev = bal[order[-1]] if order else None
            new = []
            while group:
                k = next((g for g in group if prev is not None and abs(prev + delta[g] - bal[g]) < 0.01), group[0])
                group.remove(k)
                new.append(k)
                prev = bal[k]
            moved += new != list(range(i, j))
            order += new
        else:
            order += group
        i = j
    return (df.iloc[order].reset_index(drop=True), moved) if moved else (df, 0)



def _finish(df: pd.DataFrame, warnings: list) -> pd.DataFrame:
    """Hash counterparties, mask details, mark failed rows, order the columns, and validate. Oldest first."""
    df = df.copy()
    df["details"] = df["details"].fillna("").astype(str)
    if "transaction_status" not in df:
        df["transaction_status"] = "Completed"
    df["transaction_status"] = df["transaction_status"].fillna("Completed").astype(str).str.strip()
    df["counterparty_id"] = df["details"].map(lambda s: counterparty_hash(counterparty_text(s)))
    df["details"] = df["details"].map(mask_numbers)
    # clean.py recognises a failed payment by a 'Failed - ' prefix in details (the generator's wording)
    failed = df["transaction_status"].str.lower().eq("failed") & ~df["details"].str.lower().str.startswith("failed")
    df.loc[failed, "details"] = "Failed - " + df.loc[failed, "details"]
    df["vendor_id"] = VENDOR_ID
    if len(df) > 1 and df.completion_time.iloc[0] > df.completion_time.iloc[-1]:
        df = df.iloc[::-1]                                        # newest first -> oldest first, ties keep their order
    df = df.sort_values("completion_time", kind="stable").reset_index(drop=True)[COLUMNS]
    if df.empty:
        raise StatementError("No transactions were found in the statement.")
    df, moved = order_same_second_rows(df)
    if moved:
        warnings.append({"code": "same_second_reordered", "count": moved,
                         "message": f"{moved} groups of transactions with the same time were put in running-balance order."})
    expected = df.balance.shift(1) + df.paid_in - df.withdrawn
    breaks = int(((expected - df.balance).abs() >= 0.01).sum())
    if breaks:
        warnings.append({"code": "balance_breaks", "count": breaks,
                         "message": f"{breaks} rows where the running balance does not follow from the previous row "
                                    "(kept; often failed or same-second transactions)."})
    dups = int(df.receipt_no.duplicated().sum())
    if dups:
        warnings.append({"code": "duplicate_receipts", "count": dups, "message": f"{dups} duplicate receipt numbers (kept)."})
    df.attrs["warnings"] = warnings
    return df


# ------------------------------------------------------------------ PDF
def _open_pdf(path: Path, password):
    import pdfplumber
    from pypdf import PdfReader
    try:
        reader = PdfReader(str(path))
        encrypted = reader.is_encrypted
    except Exception:
        raise StatementError("The file could not be opened as a PDF.") from None
    if encrypted:
        if not password:
            raise PasswordError("This statement is password-protected. Enter the statement password.")
        try:
            ok = reader.decrypt(password)
        except Exception:
            ok = 0
        if not ok:
            raise PasswordError("The statement password is not correct.")
    try:
        return pdfplumber.open(str(path), password=password or "")
    except Exception:
        raise StatementError("The PDF could not be read after opening it.") from None


def _lines(words, tol=3.0):
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1]["top"]) <= tol:
            lines[-1]["words"].append(w)
            lines[-1]["bottom"] = max(lines[-1]["bottom"], w["bottom"])
        else:
            lines.append({"top": w["top"], "bottom": w["bottom"], "words": [w]})
    for ln in lines:
        ln["words"].sort(key=lambda w: w["x0"])
        ln["text"] = " ".join(w["text"] for w in ln["words"])
    return lines


_HEADER_KEYS = {"receipt": "receipt_no", "completion": "completion_time", "details": "details",
                "transaction": "transaction_status", "status": "transaction_status", "paid": "paid_in",
                "withdrawn": "withdrawn", "withdrawal": "withdrawn", "balance": "balance"}


def _is_header(line) -> bool:
    t = line["text"].lower()
    return "receipt" in t and "details" in t


def _columns(line) -> dict:
    """{column: [x0, x1]} from a header line."""
    cols, last = {}, None
    for w in line["words"]:
        t = w["text"].lower().strip(".:")
        key = _HEADER_KEYS.get(t)
        if key is None and t == "time" and "completion_time" not in cols:
            key = "completion_time"
        if key is not None and (key not in cols or key == last):
            span = cols.setdefault(key, [w["x0"], w["x1"]])
            span[1] = max(span[1], w["x1"])
            last = key
        elif last is not None:                                  # "No.", "Time", "In", "Status" extend the column before
            cols[last][1] = max(cols[last][1], w["x1"])
    need = {"receipt_no", "completion_time", "details", "balance"}
    if not need <= set(cols) or not ({"paid_in", "withdrawn"} & set(cols)):
        raise StatementError("The transaction table header was found but some columns are missing.")
    return cols


def _parse_amount(s: str):
    neg = s.startswith("-") or s.endswith("-") or (s.startswith("(") and s.endswith(")"))
    v = float(re.sub(r"[^\d.]", "", s))
    return -v if neg else v


def _rows_from_pdf(pdf, warnings):
    rows, cols, current = [], None, None
    open_row = False
    for page in pdf.pages:
        lines = _lines(page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5))
        start = next((i for i, ln in enumerate(lines) if _is_header(ln)), None)
        if start is not None:
            cols = _columns(lines[start])
            lines = lines[start + 1:]
        elif cols is None:
            continue                                            # pages before the detailed table (summary)
        text_cols = sorted((c for c in ("receipt_no", "completion_time", "details", "transaction_status") if c in cols),
                           key=lambda c: cols[c][0])
        num_cols = [c for c in ("paid_in", "withdrawn", "balance") if c in cols]
        num_start = cols["transaction_status"][0] if "transaction_status" in cols else min(cols[c][0] for c in num_cols) - 20
        receipt_end = cols["completion_time"][0] - 1
        heights = [ln["bottom"] - ln["top"] for ln in lines] or [8.0]
        max_gap = max(6.0, 1.2 * float(np.median(heights)))
        page_start, prev_bottom = True, None
        for ln in lines:
            if _is_header(ln) or _FOOTER.match(ln["text"].strip()):
                open_row = False
                continue
            first = ln["words"][0]
            anchor = first["x0"] < receipt_end and _RECEIPT.match(first["text"])
            if anchor:
                current = {"receipt_no": first["text"], "completion_time": [], "details": [], "transaction_status": [],
                           "amounts": {}}
                rows.append(current)
                words = ln["words"][1:]
                open_row = True
            elif first["x0"] < receipt_end:                     # text in the receipt column but no receipt: not a row
                open_row = False
                continue
            elif open_row and current is not None and (page_start or prev_bottom is None or ln["top"] - prev_bottom <= max_gap):
                words = ln["words"]                             # wrapped continuation of the row above
            else:
                open_row = False
                continue
            for w in words:
                cx = (w["x0"] + w["x1"]) / 2
                if cx >= num_start and _AMOUNT.match(w["text"]):
                    if anchor:                                  # amounts only on the row's first line
                        c = min(num_cols, key=lambda c: abs(cx - (cols[c][0] + cols[c][1]) / 2))
                        current["amounts"].setdefault(c, []).append(_parse_amount(w["text"]))
                    continue
                c = max((c for c in text_cols if cols[c][0] <= w["x0"] + 3), key=lambda c: cols[c][0], default=None)
                if c is not None and c != "receipt_no":
                    current[c].append(w["text"])
            page_start, prev_bottom = False, ln["bottom"]
        page.close()                                            # free the parsed page; statements can run to 100+ pages
    return rows


TEXT_CHECK_PAGES = 1                       # page 1 of a statement always carries text (customer block, summary)


def _has_text(pdf) -> bool:
    """True when one of the first pages has characters. Only a few pages are checked: a re-printed statement draws every
    letter as a vector shape, and parsing all of them on a long statement takes minutes."""
    for page in pdf.pages[:TEXT_CHECK_PAGES]:
        if page.chars:
            return True
        page.close()
    return False


def read_pdf_statement(path, password=None) -> pd.DataFrame:
    """Read an M-Pesa statement PDF. Raises PasswordError, NoTextLayerError or StatementError with a safe message."""
    path = Path(path)
    if not path.exists():
        raise StatementError("The statement file was not found.")
    warnings = []
    with _open_pdf(path, password) as pdf:
        if not _has_text(pdf):
            raise NoTextLayerError(NO_TEXT_MESSAGE)
        rows = _rows_from_pdf(pdf, warnings)
    if not rows:
        raise StatementError("No transaction table (a header with 'Receipt No.' and 'Details') was found in the PDF.")
    recs, no_bal = [], 0
    for r in rows:
        a = r["amounts"]
        bal = a.get("balance", [np.nan])[-1]
        if np.isnan(bal):
            no_bal += 1
            continue
        paid_in = withdrawn = 0.0
        for v in a.get("paid_in", []):
            paid_in, withdrawn = (paid_in + v, withdrawn) if v >= 0 else (paid_in, withdrawn - v)
        for v in a.get("withdrawn", []):
            withdrawn += abs(v)
        recs.append({"receipt_no": r["receipt_no"], "completion_time": " ".join(r["completion_time"]),
                     "details": " ".join(r["details"]), "transaction_status": " ".join(r["transaction_status"]) or "Completed",
                     "paid_in": paid_in, "withdrawn": withdrawn, "balance": float(bal)})
    if no_bal:
        warnings.append({"code": "rows_without_balance", "count": no_bal, "message": f"{no_bal} rows had no balance and were skipped."})
    df = pd.DataFrame(recs, columns=["receipt_no", "completion_time", "details", "transaction_status", "paid_in", "withdrawn", "balance"])
    t = pd.to_datetime(df["completion_time"], errors="coerce", format="mixed")
    if len(t) and t.isna().mean() > 0.5:
        t = pd.to_datetime(df["completion_time"], errors="coerce", format="mixed", dayfirst=True)
    bad = int(t.isna().sum())
    if bad:
        warnings.append({"code": "unreadable_times", "count": bad, "message": f"{bad} rows with an unreadable time were skipped."})
    df["completion_time"] = t
    df = df[t.notna()]
    return _finish(df, warnings)


# ------------------------------------------------------------------ dispatcher
def read_statement(path, password=None) -> pd.DataFrame:
    """Read a statement by extension: .pdf (read_pdf_statement), .xlsx/.xls/.csv (clean.read_real_statement)."""
    path = Path(path)
    if not path.exists():
        raise StatementError("The statement file was not found.")
    ext = path.suffix.lower()
    if ext == ".pdf":
        return read_pdf_statement(path, password)
    if ext in (".xlsx", ".xls", ".csv"):
        try:
            df = clean.read_real_statement(str(path))
        except SystemExit as e:                                 # the reader stops with SystemExit; turn it into an error
            raise StatementError(str(e)) from None
        return _finish(df, list(df.attrs.get("warnings", [])))
    raise StatementError(f"Unsupported file type '{ext}'. Use the Excel (.xlsx) or CSV version of the M-Pesa statement.")
