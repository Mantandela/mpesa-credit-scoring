"""Stage 2: cleaning (docs/data_dictionary.md, "Transaction type taxonomy" and "Validation rules").

Reads data/synthetic/transactions, works out `txn_type` from the `details` text only (never from txn_type_true),
flags rows that break the validation rules, and writes data/interim/transactions_clean.

Run from the repo root:
    python src/clean.py                              clean data/synthetic
    python src/clean.py --dir data/test              clean another folder
    python src/clean.py --statement data/private/statement.xlsx
                                                     clean a REAL statement. Reads the Excel file, finds the header,
                                                     writes data/private/statement_clean.parquet and
                                                     data/private/cleaning_report_statement.md (git-ignored)
    python src/clean.py --wording my_details.txt     classify detail strings from a text file (one per line)
                                                     and print counts only. For checking real statement wording locally.

The cleaner does NOT delete rows. It adds columns, so later stages choose what to drop:
    txn_type, direction, is_failed, fuliza_funded and one flag_* column per rule.
txn_type_true is kept only so accuracy can be checked. It must never be a model input.
"""
import argparse
import os
import re
import numpy as np
import pandas as pd

# ---------------------------------------------------------------- classification rules
# Applied to details after lower-casing and removing spaces, ids and digits. First match wins.
# The wording follows the generator and the author's own statement (data_dictionary.md section 1).
RULES = [
    ("REVERSAL",      r"^reversal"),
    ("FULIZA_DRAW",   r"^overdraft(?!charge)|overdraftofcreditparty|fuliza(draw|disburse)"),
    ("FULIZA_REPAY",  r"odloanrepayment|overdraft.*repay|fuliza.*repay|repayment.*overdraw"),
    ("FEE",           r"charge|fee"),
    ("OTHER_LOAN",    r"m-?shwari|kcbm-?pesa|loandisburse|loanreceived|loanrepayment|^loan"),
    ("TILL_PAYMENT_IN", r"(merchantpayment|customerpayment|businesspayment|payment)from|buygoods.*from|received.*till"),
    ("SEND_MONEY_IN", r"fundsreceivedfrom|receivedfrom|customertransferfrom"),
    ("SEND_MONEY_OUT", r"customertransfer(fuliza\w*)?to|sentto|sendmoney"),
    ("PAYBILL_OUT",   r"paybill|billpayment"),
    ("BUY_GOODS_OUT", r"merchantpayment(?!.*from)|customerpaymenttosmallbusiness|buygoods|till"),
    ("AIRTIME_OUT",   r"airtime|bundle"),
    ("WITHDRAW_AGENT", r"withdraw|cashout"),
    ("DEPOSIT_AGENT", r"depositoffunds|depositatagent|cashin|^deposit"),
]
INFLOW_TYPES = {"TILL_PAYMENT_IN", "SEND_MONEY_IN", "DEPOSIT_AGENT", "FULIZA_DRAW"}


def normalise(s: pd.Series) -> pd.Series:
    """lower-case, drop failed prefix marker later, hashed ids, digits and spaces so only wording is left"""
    s = s.fillna("").astype(str).str.lower()
    s = s.str.replace(r"cp_[0-9a-f]+", "cp", regex=True)
    s = s.str.replace(r"\s+", "", regex=True).str.replace(r"\d+", "", regex=True)
    return s


def classify_one(norm: str) -> str:
    if norm.startswith("failed-"):
        norm = norm[len("failed-"):]
    for name, rx in RULES:
        if re.search(rx, norm):
            return name
    return "UNKNOWN"


def classify_details(details: pd.Series) -> pd.DataFrame:
    """Returns txn_type, is_failed and fuliza_funded for a Series of details strings. Works on unique wordings only."""
    norm = normalise(details)
    codes, uniques = pd.factorize(norm)
    mapped = np.array([classify_one(u) for u in uniques], dtype=object)
    out = pd.DataFrame(index=details.index)
    out["txn_type"] = mapped[codes]
    out["is_failed"] = norm.str.startswith("failed-").values
    fl = norm.str.contains("fuliza", regex=False).values
    out["fuliza_funded"] = fl & ~out["txn_type"].isin(["FULIZA_DRAW", "FULIZA_REPAY", "FEE"]).values
    return out


# ---------------------------------------------------------------- loading and saving
def load(d, name):
    for ext, fn in ((".parquet", pd.read_parquet), (".csv", pd.read_csv)):
        p = os.path.join(d, name + ext)
        if os.path.exists(p):
            return fn(p)
    raise SystemExit(f"{name} not found in {d}")


def read_real_statement(path) -> pd.DataFrame:
    """Reads a real M-Pesa statement (xlsx, xls or csv) into the same columns as the synthetic transactions table.
    Finds the header row (the line with Receipt and Details), maps the column names, strips commas from numbers
    and puts the rows oldest first (real statements are usually newest first, which would scramble rows that
    share a second). All rows get vendor_id REAL_STATEMENT."""
    if path.lower().endswith((".xlsx", ".xls")):
        raw = pd.read_excel(path, header=None, dtype=str)
    else:
        raw = pd.read_csv(path, header=None, dtype=str, on_bad_lines="skip", engine="python")
    for i in range(min(len(raw), 60)):
        vals = " ".join(str(v).lower() for v in raw.iloc[i].values)
        if "receipt" in vals and "details" in vals:
            raw.columns = [str(c).strip().lower() for c in raw.iloc[i].values]
            raw = raw.iloc[i + 1:].reset_index(drop=True)
            break
    else:
        raise SystemExit("Could not find the header row (a line with 'Receipt' and 'Details') in the first 60 rows.")
    cols = {}
    for c in raw.columns:
        if "receipt" in c: cols[c] = "receipt_no"
        elif "completion" in c or c.startswith("time"): cols[c] = "completion_time"
        elif "detail" in c: cols[c] = "details"
        elif "status" in c: cols[c] = "transaction_status"
        elif "paid" in c: cols[c] = "paid_in"
        elif "withdraw" in c: cols[c] = "withdrawn"
        elif "balance" in c: cols[c] = "balance"
    df = raw.rename(columns=cols)[list(dict.fromkeys(cols.values()))].copy()
    missing = {"receipt_no", "completion_time", "details", "paid_in", "withdrawn", "balance"} - set(df.columns)
    if missing:
        raise SystemExit(f"Columns not found: {sorted(missing)}. Found: {list(df.columns)}")
    if "transaction_status" not in df:
        df["transaction_status"] = "Completed"
    for c in ("paid_in", "withdrawn", "balance"):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(r"[,\s]", "", regex=True), errors="coerce")
    df["paid_in"] = df["paid_in"].fillna(0.0)
    df["withdrawn"] = df["withdrawn"].fillna(0.0).abs()
    t = pd.to_datetime(df["completion_time"], errors="coerce")
    if t.isna().mean() > 0.5:
        t = pd.to_datetime(df["completion_time"], errors="coerce", dayfirst=True)
    df["completion_time"] = t
    df = df.dropna(subset=["completion_time", "balance"]).reset_index(drop=True)
    if len(df) > 1 and df.completion_time.iloc[0] > df.completion_time.iloc[-1]:
        df = df.iloc[::-1].reset_index(drop=True)          # newest first -> oldest first
    df["vendor_id"] = "REAL_STATEMENT"
    return df


def save(df, folder, name):
    os.makedirs(folder, exist_ok=True)
    try:
        p = os.path.join(folder, name + ".parquet")
        df.to_parquet(p, index=False)
    except Exception:
        p = os.path.join(folder, name + ".csv")
        df.to_csv(p, index=False)
    return p


# ---------------------------------------------------------------- cleaning
def clean(tx: pd.DataFrame, as_of=None) -> pd.DataFrame:
    tx = tx.copy()
    tx["completion_time"] = pd.to_datetime(tx["completion_time"])
    tx["_orig_order"] = np.arange(len(tx))
    # Real statements are often newest first. Sort oldest first inside each vendor, keeping file order for ties.
    tx = tx.sort_values(["vendor_id", "completion_time", "_orig_order"], kind="stable").reset_index(drop=True)

    tx = tx.join(classify_details(tx["details"]))
    tx["direction"] = np.where(tx.is_failed, "none", np.where(tx.paid_in > 0, "in", np.where(tx.withdrawn > 0, "out", "none")))

    # Wording the rules do not know: still keep the row, tag the direction so counts stay honest.
    unk = tx.txn_type == "UNKNOWN"
    tx.loc[unk & (tx.direction == "in"), "txn_type"] = "OTHER_IN"
    tx.loc[unk & (tx.direction == "out"), "txn_type"] = "OTHER_OUT"

    # Validation rules (data_dictionary.md)
    tx["flag_both_amounts"] = (tx.paid_in > 0) & (tx.withdrawn > 0)                                   # rule 1
    prev = tx.groupby("vendor_id")["balance"].shift(1)
    tx["flag_balance_break"] = prev.notna() & ((prev + tx.paid_in - tx.withdrawn - tx.balance).abs() >= 0.01)   # rule 2
    tx["flag_duplicate_receipt"] = tx.duplicated("receipt_no", keep="first")                          # rule 3
    dt = tx.groupby("vendor_id")["completion_time"].diff()
    tx["flag_time_not_increasing"] = dt.notna() & (dt <= pd.Timedelta(0))                             # rule 4
    limit = pd.Timestamp(as_of) if as_of else pd.Timestamp.now()
    tx["flag_future_date"] = tx.completion_time > limit
    tx["flag_negative"] = (tx.paid_in < 0) | (tx.withdrawn < 0) | (tx.balance < 0)                    # rule 5
    tx["flag_unknown_wording"] = tx.txn_type.isin(["OTHER_IN", "OTHER_OUT"])
    return tx.drop(columns="_orig_order")


FLAGS = ["flag_both_amounts", "flag_balance_break", "flag_duplicate_receipt", "flag_time_not_increasing",
         "flag_future_date", "flag_negative", "flag_unknown_wording"]


def collect_stats(tx: pd.DataFrame) -> dict:
    """Counts only. Can be added together across chunks, so the report never needs the whole table in memory."""
    s = {"n": len(tx), "vendors": int(tx.vendor_id.nunique()),
         "types": tx.txn_type.value_counts().to_dict(),
         "flags": {f: int(tx[f].sum()) for f in FLAGS},
         "failed": int(tx.is_failed.sum()), "fuliza_funded": int(tx.fuliza_funded.sum()),
         "has_truth": "txn_type_true" in tx, "known": 0, "agree": 0, "disagree": {}}
    if s["has_truth"]:
        known = tx.txn_type_true.notna()
        ok = (tx.txn_type == tx.txn_type_true) & known
        s["known"], s["agree"] = int(known.sum()), int(ok.sum())
        bad = tx[known & ~ok]
        if len(bad):
            s["disagree"] = {f"{a}|{b}": int(v) for (a, b), v in bad.groupby(["txn_type_true", "txn_type"]).size().items()}
    return s


def merge_stats(a: dict, b: dict) -> dict:
    if a is None:
        return b
    out = {"n": a["n"] + b["n"], "vendors": a["vendors"] + b["vendors"], "has_truth": a["has_truth"] and b["has_truth"],
           "failed": a["failed"] + b["failed"], "fuliza_funded": a["fuliza_funded"] + b["fuliza_funded"],
           "known": a["known"] + b["known"], "agree": a["agree"] + b["agree"]}
    for key in ("types", "flags", "disagree"):
        d = dict(a[key])
        for k, v in b[key].items():
            d[k] = d.get(k, 0) + v
        out[key] = d
    return out


def report_from_stats(s: dict) -> str:
    n = s["n"]
    L = ["# Cleaning report", "", f"{n:,} lines, {s['vendors']} vendors", ""]
    L += ["## Rows per txn_type", "", "| txn_type | rows | share |", "|---|---|---|"]
    L += [f"| {k} | {v:,} | {v / n:.1%} |" for k, v in sorted(s["types"].items(), key=lambda kv: -kv[1])]
    L += ["", "## Validation flags", "", "| flag | rows |", "|---|---|"]
    L += [f"| {f} | {s['flags'][f]:,} |" for f in FLAGS]
    if "global_duplicate_receipts" in s:
        L += [f"| duplicate receipt_no across the whole file | {s['global_duplicate_receipts']:,} |"]
    L += [f"| is_failed (status Failed) | {s['failed']:,} |", f"| fuliza_funded payments | {s['fuliza_funded']:,} |"]
    if s["has_truth"]:
        L += ["", "## Check against txn_type_true (synthetic data only)", "",
              f"Agreement: {s['agree'] / max(s['known'], 1):.4%} of {s['known']:,} rows"]
        if s["disagree"]:
            top = sorted(s["disagree"].items(), key=lambda kv: -kv[1])[:10]
            L += ["", "Disagreements (true, parsed, rows):", ""] + [f"- {k.split('|')[0]} parsed as {k.split('|')[1]}: {v:,}" for k, v in top]
    return "\n".join(L) + "\n"


def report(tx: pd.DataFrame) -> str:
    return report_from_stats(collect_stats(tx))


def clean_file_in_chunks(path: str, out_dir: str, as_of=None):
    """Clean a parquet file written in chunks of whole vendors (the generator does this), one row group at a time.
    Returns (stats, output path). Memory stays at one chunk. receipt_no is also checked for duplicates across chunks."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(path)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "transactions_clean.parquet")
    writer, stats, hashes = None, None, []
    for i in range(pf.num_row_groups):
        c = clean(pf.read_row_group(i).to_pandas(), as_of)
        stats = merge_stats(stats, collect_stats(c))
        hashes.append(pd.util.hash_array(c.receipt_no.to_numpy(dtype=object)))
        table = pa.Table.from_pandas(c, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(out_path, table.schema)
        writer.write_table(table, row_group_size=max(len(table), 1))
        print(f"  cleaned chunk {i + 1}/{pf.num_row_groups}", flush=True)
    writer.close()
    allh = np.concatenate(hashes)
    stats["global_duplicate_receipts"] = int(len(allh) - len(np.unique(allh)))
    return stats, out_path


def wording_check(path):
    with open(path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    s = pd.Series(lines)
    res = classify_details(s)
    print(f"{len(s):,} detail strings classified. Counts only, nothing else printed.\n")
    print(res.txn_type.value_counts().to_string())
    unk = (res.txn_type == "UNKNOWN").sum()
    print(f"\nUNKNOWN: {unk} ({unk / len(s):.1%}). Target: below 2%. Share the wording pattern (not names or numbers) so a rule can be added.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/synthetic")
    ap.add_argument("--out", default="data/interim")
    ap.add_argument("--report", default="docs/cleaning_report.md")
    ap.add_argument("--as-of", default=None, help="date after which a row counts as future (default: today)")
    ap.add_argument("--wording", help="text file with one details string per line; prints counts only")
    ap.add_argument("--statement", help="a real statement (xlsx or csv). Output goes to data/private/, never to data/interim/")
    a = ap.parse_args()

    if a.wording:
        wording_check(a.wording)
        return

    if a.statement:
        # real data: keep every output inside the git-ignored private folder
        a.out = "data/private"
        a.report = "data/private/cleaning_report_statement.md"
        tx = clean(read_real_statement(a.statement), a.as_of)
        p = save(tx, a.out, "statement_clean")
        txt = report(tx)
    else:
        src = os.path.join(a.dir, "transactions.parquet")
        chunked = False
        if os.path.exists(src):
            try:
                import pyarrow.parquet as pq
                chunked = pq.ParquetFile(src).num_row_groups > 1
            except ImportError:
                pass
        if chunked:                                   # large file written in chunks: one chunk in memory at a time
            stats, p = clean_file_in_chunks(src, a.out, a.as_of)
            txt = report_from_stats(stats)
        else:
            tx = clean(load(a.dir, "transactions"), a.as_of)
            p = save(tx, a.out, "transactions_clean")
            txt = report(tx)
    os.makedirs(os.path.dirname(a.report) or ".", exist_ok=True)
    with open(a.report, "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)
    print(f"wrote {p}\nwrote {a.report}")


if __name__ == "__main__":
    main()