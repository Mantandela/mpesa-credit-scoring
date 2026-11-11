"""Checks on the synthetic data (docs/personas.md, "Checks after the first run", and docs/data_dictionary.md rules).

Run from the repo root:  python src/check_synthetic.py            (reads data/synthetic/)
                         python src/check_synthetic.py --dir some/folder
Prints PASS or FAIL for each rule and a per-persona summary. Nothing is written.
"""
import argparse
import os
import numpy as np
import pandas as pd


def load(d, name):
    for ext, fn in ((".parquet", pd.read_parquet), (".csv", pd.read_csv)):
        p = os.path.join(d, name + ext)
        if os.path.exists(p):
            return fn(p)
    raise SystemExit(f"{name} not found in {d}")


def load_transactions(d, groups):
    """Large files are written in chunks of 50 vendors. Read only the first `groups` chunks (0 = all)."""
    p = os.path.join(d, "transactions.parquet")
    if os.path.exists(p):
        try:
            import pyarrow.parquet as pq
            pf = pq.ParquetFile(p)
            n = pf.num_row_groups
            if groups and n > groups:
                return pf.read_row_groups(list(range(groups))).to_pandas(), n
            return pf.read().to_pandas(), n
        except ImportError:
            pass
    return load(d, "transactions"), 1


def flag(ok, text):
    print(("PASS  " if ok else "FAIL  ") + text)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/synthetic")
    ap.add_argument("--groups", type=int, default=6,
                    help="check the first N chunks of 50 vendors (default 6 = 300 vendors, 0 = everything). "
                         "The full file is also checked row by row by src/clean.py")
    a = ap.parse_args()
    tx, n_groups = load_transactions(a.dir, a.groups)
    ve, ap_ = load(a.dir, "vendors"), load(a.dir, "loan_applications")
    tx["completion_time"] = pd.to_datetime(tx["completion_time"])
    tx = tx.sort_values(["vendor_id", "completion_time"], kind="stable")
    n_all_vendors, n_all_apps = len(ve), len(ap_)
    seen = tx.vendor_id.unique()
    ve, ap_ = ve[ve.vendor_id.isin(seen)], ap_[ap_.vendor_id.isin(seen)]
    note = f" (checked the first {len(seen)} of {n_all_vendors} vendors)" if len(seen) < n_all_vendors else ""
    print(f"{len(tx):,} lines, {tx.vendor_id.nunique()} vendors, {n_all_apps} applications{note}\n")

    print("-- Data dictionary rules")
    flag(((tx.paid_in > 0) & (tx.withdrawn > 0)).sum() == 0, "each row has paid_in or withdrawn, not both")
    prev = tx.groupby("vendor_id")["balance"].shift(1)
    first = prev.isna()
    chk = (prev + tx.paid_in - tx.withdrawn - tx.balance).abs()
    flag((chk[~first] < 0.01).all(), f"balance(t) = balance(t-1) + paid_in - withdrawn  (bad rows: {(chk[~first] >= 0.01).sum()})")
    flag(tx.receipt_no.is_unique, "receipt_no is unique")
    dt_ = tx.groupby("vendor_id")["completion_time"].diff().dropna()
    flag((dt_ > pd.Timedelta(0)).all(), "completion_time strictly increasing within a vendor")
    flag((tx[["paid_in", "withdrawn", "balance"]] >= 0).all().all(), "paid_in, withdrawn and balance never negative")
    draws = tx[tx.txn_type_true == "FULIZA_DRAW"].paid_in
    flag((draws <= 1000).all() and (draws >= 50).all(), f"Fuliza draws between 50 and 1,000 (median {draws.median():.0f}, mean {draws.mean():.0f})")
    # outcome window: every application must have OBS_WINDOW_DAYS of statement after it. Outcomes are made later by scorecard.py
    # measured to the designed end of each statement (start_date + statement_days - 1). A vendor with no activity in its last few
    # days has an earlier LAST TRANSACTION, but the statement period still covers the window.
    end = pd.to_datetime(ve.set_index("vendor_id").start_date) + pd.to_timedelta(ve.set_index("vendor_id").statement_days - 1, unit="D")
    gap = (ap_.vendor_id.map(end) - pd.to_datetime(ap_.application_date)).dt.days
    flag((gap >= 90).all(), f"every application has at least 90 days of statement after it (shortest {gap.min()} days)")
    quiet = ((ap_.vendor_id.map(tx.groupby("vendor_id").completion_time.max()) - pd.to_datetime(ap_.application_date)).dt.days < 90).sum()
    if quiet:
        print(f"      {quiet} application(s) have a last transaction less than 90 days after it (vendor quiet at the end; fine)")
    flag(abs(ap_.hidden_shock.mean()) < 0.35 and 0.7 < ap_.hidden_shock.std() < 1.3,
         f"hidden_shock looks standard normal (mean {ap_.hidden_shock.mean():.2f}, sd {ap_.hidden_shock.std():.2f})")
    flag(not {"defaulted", "late_or_default", "days_past_due"} & set(ap_.columns), "no outcome columns yet (made by scorecard.py)")
    print(f"      failed rows {(tx.transaction_status == 'Failed').sum()}, reversals {(tx.txn_type_true == 'REVERSAL').sum()}")

    print("\n-- Per persona")
    tx = tx.merge(ve[["vendor_id", "persona"]], on="vendor_id")
    tx["day"] = tx.completion_time.dt.normalize()
    tx["month"] = tx.completion_time.dt.to_period("M")
    ins = tx[tx.txn_type_true.isin(["TILL_PAYMENT_IN", "SEND_MONEY_IN"])]
    per_day = ins.groupby(["vendor_id", "day"]).size().groupby("vendor_id").median()
    act = tx.groupby(["vendor_id", "month"]).day.nunique().groupby("vendor_id").median()
    eod = tx.groupby(["vendor_id", "day"]).balance.last()
    near0 = (eod < 100).groupby("vendor_id").mean() * 30          # near-zero days per month (of active days)
    ticket = ins.groupby("vendor_id").paid_in.median()
    till = (ins.txn_type_true == "TILL_PAYMENT_IN").groupby(ins.vendor_id).mean()
    fz = tx[tx.txn_type_true == "FULIZA_DRAW"].groupby("vendor_id").size().reindex(ve.vendor_id).fillna(0)
    months = ve.set_index("vendor_id").statement_days / 30.0
    fz_pm = fz / months.reindex(fz.index)
    lastinf = ins.groupby(["vendor_id", "month"]).paid_in.sum()
    vs = pd.DataFrame({"persona": ve.set_index("vendor_id").persona, "tx_per_active_day": per_day, "active_days_pm": act,
                       "near_zero_days_pm": near0, "median_ticket": ticket, "till_share": till, "fuliza_draws_pm": fz_pm})
    order = ["stable", "growing", "seasonal", "new", "struggling"]
    print(vs.groupby("persona").median(numeric_only=True).reindex(order).round(2).to_string())
    pa = ap_.merge(ve[["vendor_id", "persona"]], on="vendor_id")
    print(f"\napplications per persona: {pa.persona.value_counts().reindex(order).to_dict()}")
    print("default and late rates by persona are in docs/scorecard_report.md (after scorecard.py)")

    # Fuliza repayment speed: days from a draw to the next repayment line
    lags = []
    for vid, g in tx[tx.txn_type_true.isin(["FULIZA_DRAW", "FULIZA_REPAY"])].groupby("vendor_id"):
        d = g[g.txn_type_true == "FULIZA_DRAW"].completion_time.values
        r_ = g[g.txn_type_true == "FULIZA_REPAY"].completion_time.values
        idx = np.searchsorted(r_, d)
        ok = idx < len(r_)
        lags.extend((r_[idx[ok]] - d[ok]) / np.timedelta64(1, "D"))
    if lags:
        print(f"\nFuliza draw to next repayment: median {np.median(lags):.1f} days, 90th pct {np.percentile(lags, 90):.1f} "
              f"(own statement: 0.5 and 2.3)")
    tot_d = draws.sum()
    tot_r = tx[tx.txn_type_true == "FULIZA_REPAY"].withdrawn.sum()
    print(f"Fuliza repaid / drawn: {tot_r / tot_d:.0%} (own statement: 103%; lower here if loans were still open at the end)")
    pay = tx[tx.txn_type_true.isin(["SEND_MONEY_OUT", "BUY_GOODS_OUT", "PAYBILL_OUT", "AIRTIME_OUT"]) & (tx.transaction_status == "Completed")]
    print(f"Payments funded by Fuliza: {pay.details.str.contains('Fuliza').mean():.0%} by count (own statement: 75%, heavy user)")


if __name__ == "__main__":
    main()