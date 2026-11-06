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


def flag(ok, text):
    print(("PASS  " if ok else "FAIL  ") + text)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/synthetic")
    a = ap.parse_args()
    tx, ve, ap_ = load(a.dir, "transactions"), load(a.dir, "vendors"), load(a.dir, "loan_applications")
    tx["completion_time"] = pd.to_datetime(tx["completion_time"])
    tx = tx.sort_values(["vendor_id", "completion_time"], kind="stable")
    print(f"{len(tx):,} lines, {tx.vendor_id.nunique()} vendors, {len(ap_)} applications\n")

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
    rate = ap_.defaulted.mean()
    flag(0.14 <= rate <= 0.19, f"overall defaulted rate {rate:.1%} (target 14% to 19%, anchor 16.6%)")
    print(f"      late_or_default rate {ap_.late_or_default.mean():.1%} (stress run should be near 61%)")
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
    months = ve.set_index("vendor_id").months_of_history
    fz_pm = fz / months.reindex(fz.index)
    lastinf = ins.groupby(["vendor_id", "month"]).paid_in.sum()
    vs = pd.DataFrame({"persona": ve.set_index("vendor_id").persona, "tx_per_active_day": per_day, "active_days_pm": act,
                       "near_zero_days_pm": near0, "median_ticket": ticket, "till_share": till, "fuliza_draws_pm": fz_pm})
    order = ["stable", "growing", "seasonal", "new", "struggling"]
    print(vs.groupby("persona").median(numeric_only=True).reindex(order).round(2).to_string())
    pa = ap_.merge(ve[["vendor_id", "persona"]], on="vendor_id")
    print("\ndefault rate by persona:")
    print(pa.groupby("persona").defaulted.mean().reindex(order).round(3).to_string())
    r = pa.groupby("persona").defaulted.mean()
    flag(r.idxmax() == "struggling" and (r["stable"] + r["growing"]) / 2 < (r["seasonal"] + r["new"]) / 2 < r["struggling"],
         "default rate: struggling highest, stable and growing below seasonal and new (exceptions allowed, small samples)")
    print(f"      applications per persona: {pa.persona.value_counts().reindex(order).to_dict()}")

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