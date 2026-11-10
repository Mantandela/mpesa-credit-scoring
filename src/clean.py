"""Stage 2: cleaning (docs/data_dictionary.md, "Transaction type taxonomy" and "Validation rules").

Reads data/synthetic/transactions, works out `txn_type` from the `details` text only (never from txn_type_true),
flags rows that break the validation rules, and writes data/interim/transactions_clean.

Run from the repo root:
    python src/clean.py                              clean data/synthetic
    python src/clean.py --dir data/test              clean another folder
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


def report(tx: pd.DataFrame) -> str:
    n = len(tx)
    L = [f"# Cleaning report", "", f"{n:,} lines, {tx.vendor_id.nunique()} vendors", ""]
    L += ["## Rows per txn_type", "", "| txn_type | rows | share |", "|---|---|---|"]
    vc = tx.txn_type.value_counts()
    L += [f"| {k} | {v:,} | {v / n:.1%} |" for k, v in vc.items()]
    L += ["", "## Validation flags", "", "| flag | rows |", "|---|---|"]
    L += [f"| {f} | {int(tx[f].sum()):,} |" for f in FLAGS]
    L += [f"| is_failed (status Failed) | {int(tx.is_failed.sum()):,} |",
          f"| fuliza_funded payments | {int(tx.fuliza_funded.sum()):,} |"]
    if "txn_type_true" in tx:
        known = tx.txn_type_true.notna()
        ok = (tx.txn_type == tx.txn_type_true) & known
        L += ["", "## Check against txn_type_true (synthetic data only)", "",
              f"Agreement: {ok[known].mean():.4%} of {int(known.sum()):,} rows"]
        bad = tx[known & ~ok]
        if len(bad):
            c = bad.groupby(["txn_type_true", "txn_type"]).size().sort_values(ascending=False).head(10)
            L += ["", "Disagreements (true, parsed, rows):", ""] + [f"- {a} parsed as {b}: {v:,}" for (a, b), v in c.items()]
    return "\n".join(L) + "\n"


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
    a = ap.parse_args()

    if a.wording:
        wording_check(a.wording)
        return

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