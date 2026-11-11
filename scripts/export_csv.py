"""Export the generated data to CSV so it can be opened in Excel or VS Code.

Run from the repo root, any time after the generator (the later files appear once their stage has run):
    python scripts/export_csv.py                     everything available, with a small transaction sample
    python scripts/export_csv.py --vendor V00007     transactions of one named vendor instead of the sample
    python scripts/export_csv.py --full              ALSO write every transaction line
                                                     (millions of rows: too big for Excel, fine for VS Code or pandas)

What is written to data/exports/ (add it to .gitignore). The parquet files are not changed.
  after generator.py : vendors.csv, loan_applications.csv, transactions_sample.csv (one median vendor per persona)
  after clean.py     : transactions_clean_sample.csv (same vendors, with the classified type and flags)
  after features.py  : features.csv (52 features, no outcomes yet)
  after scorecard.py : loan_applications_with_outcomes.csv and features_with_labels.csv (defaulted, fuliza_late, repayment_status, ...)
"""
import argparse
import os
import pandas as pd

OUTCOME_COLS = ["scorecard_score", "scorecard_p", "defaulted", "fuliza_n_draws", "fuliza_late", "fuliza_max_lag_days",
                "window_complete", "repayment_status", "late_or_default"]


def load(d, name):
    for ext, fn in ((".parquet", pd.read_parquet), (".csv", pd.read_csv)):
        p = os.path.join(d, name + ext)
        if os.path.exists(p):
            return fn(p)
    raise SystemExit(f"{name} not found in {d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/synthetic")
    ap.add_argument("--clean-dir", default="data/interim")
    ap.add_argument("--features-dir", default="data/processed")
    ap.add_argument("--out", default="data/exports")
    ap.add_argument("--vendor", help="export transactions of this vendor_id only")
    ap.add_argument("--full", action="store_true", help="also write all transaction lines")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    ve = load(a.dir, "vendors")
    ap_ = load(a.dir, "loan_applications")
    path = os.path.join(a.dir, "transactions.parquet")
    parquet = os.path.exists(path)

    ve.to_csv(os.path.join(a.out, "vendors.csv"), index=False)
    ap_.to_csv(os.path.join(a.out, "loan_applications.csv"), index=False)
    print(f"vendors.csv ({len(ve)} rows), loan_applications.csv ({len(ap_)} rows)")

    # ---- transactions: one median vendor per persona, or the vendor asked for
    if a.vendor:
        ids = [a.vendor]
        if a.vendor not in set(ve.vendor_id):
            raise SystemExit(f"{a.vendor} not found. Example ids: {list(ve.vendor_id[:5])}")
        name = f"transactions_{a.vendor}.csv"
    else:
        vid_col = pd.read_parquet(path, columns=["vendor_id"]) if parquet else load(a.dir, "transactions")[["vendor_id"]]
        n = vid_col.groupby("vendor_id").size().rename("n")
        v = ve.merge(n, left_on="vendor_id", right_index=True)
        ids = []
        for _, g in v.groupby("persona"):
            g = g.sort_values("n")
            ids.append(g.iloc[len(g) // 2].vendor_id)
        name = "transactions_sample.csv"
    tx = pd.read_parquet(path, filters=[("vendor_id", "in", ids)]) if parquet else load(a.dir, "transactions")
    tx = tx[tx.vendor_id.isin(ids)].sort_values(["vendor_id", "completion_time"], kind="stable")
    tx.merge(ve[["vendor_id", "persona"]], on="vendor_id").to_csv(os.path.join(a.out, name), index=False)
    print(f"{name} ({len(tx):,} rows, vendors: {', '.join(ids)})")

    if a.full:
        out_path, total = os.path.join(a.out, "transactions_full.csv"), 0
        if parquet:                                   # one chunk at a time so memory stays small
            import pyarrow.parquet as pq
            pf = pq.ParquetFile(path)
            for i in range(pf.num_row_groups):
                chunk = pf.read_row_group(i).to_pandas()
                chunk.to_csv(out_path, mode="w" if i == 0 else "a", header=(i == 0), index=False)
                total += len(chunk)
        else:
            full = load(a.dir, "transactions")
            full.to_csv(out_path, index=False)
            total = len(full)
        print(f"transactions_full.csv ({total:,} rows). Too large for Excel, open it in VS Code or pandas.")

    # ---- cleaned transactions (after clean.py)
    cpath = os.path.join(a.clean_dir, "transactions_clean.parquet")
    if os.path.exists(cpath):
        ct = pd.read_parquet(cpath, filters=[("vendor_id", "in", ids)])
        ct = ct.sort_values(["vendor_id", "completion_time"], kind="stable")
        ct.to_csv(os.path.join(a.out, "transactions_clean_sample.csv"), index=False)
        print(f"transactions_clean_sample.csv ({len(ct):,} rows)")
    else:
        print("transactions_clean_sample.csv skipped (run clean.py first)")

    # ---- features and outcomes (after features.py and scorecard.py)
    fpath = os.path.join(a.features_dir, "features.parquet")
    if os.path.exists(fpath):
        f = pd.read_parquet(fpath)
        has_labels = "defaulted" in f.columns
        if has_labels:
            f.to_csv(os.path.join(a.out, "features_with_labels.csv"), index=False)
            keep = ["application_id"] + [c for c in OUTCOME_COLS if c in f.columns]
            ap_.merge(f[keep], on="application_id", how="left").to_csv(
                os.path.join(a.out, "loan_applications_with_outcomes.csv"), index=False)
            print(f"features_with_labels.csv ({len(f):,} rows, {f.shape[1]} columns), "
                  f"loan_applications_with_outcomes.csv ({len(ap_):,} rows)")
        else:
            f.to_csv(os.path.join(a.out, "features.csv"), index=False)
            print(f"features.csv ({len(f):,} rows). Outcomes appear after python src/scorecard.py")
    else:
        print("features and outcome files skipped (run features.py and scorecard.py first)")
    print(f"\nFiles are in {a.out}")


if __name__ == "__main__":
    main()