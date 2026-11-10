"""Export the synthetic parquet tables to CSV so they can be opened in Excel or VS Code.

Run from the repo root:
    python scripts/export_csv.py                     vendors + loan_applications in full,
                                                     transactions for one vendor per persona
    python scripts/export_csv.py --vendor V00007     transactions for one named vendor
    python scripts/export_csv.py --full              ALSO write every transaction line
                                                     (millions of rows: too big for Excel, fine for VS Code or pandas)

Output goes to data/exports/ (add it to .gitignore). The parquet files are not changed.
"""
import argparse
import os
import pandas as pd


def load(d, name):
    p = os.path.join(d, name + ".parquet")
    if os.path.exists(p):
        return pd.read_parquet(p)
    p = os.path.join(d, name + ".csv")
    if os.path.exists(p):
        return pd.read_csv(p)
    raise SystemExit(f"{name} not found in {d}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/synthetic")
    ap.add_argument("--out", default="data/exports")
    ap.add_argument("--vendor", help="export transactions of this vendor_id only")
    ap.add_argument("--full", action="store_true", help="also write all transaction lines")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    ve = load(a.dir, "vendors")
    ap_ = load(a.dir, "loan_applications")
    tx = load(a.dir, "transactions")
    tx = tx.sort_values(["vendor_id", "completion_time"], kind="stable")

    ve.to_csv(os.path.join(a.out, "vendors.csv"), index=False)
    ap_.to_csv(os.path.join(a.out, "loan_applications.csv"), index=False)
    print(f"vendors.csv ({len(ve)} rows), loan_applications.csv ({len(ap_)} rows)")

    if a.vendor:
        ids = [a.vendor]
        if a.vendor not in set(ve.vendor_id):
            raise SystemExit(f"{a.vendor} not found. Example ids: {list(ve.vendor_id[:5])}")
        name = f"transactions_{a.vendor}.csv"
    else:
        # one vendor per persona: the one with the median number of lines in that persona
        n = tx.groupby("vendor_id").size().rename("n")
        v = ve.merge(n, left_on="vendor_id", right_index=True)
        ids = []
        for _, g in v.groupby("persona"):
            g = g.sort_values("n")
            ids.append(g.iloc[len(g) // 2].vendor_id)
        name = "transactions_sample.csv"
    sample = tx[tx.vendor_id.isin(ids)].merge(ve[["vendor_id", "persona"]], on="vendor_id")
    sample.to_csv(os.path.join(a.out, name), index=False)
    print(f"{name} ({len(sample):,} rows, vendors: {', '.join(ids)})")

    if a.full:
        tx.to_csv(os.path.join(a.out, "transactions_full.csv"), index=False)
        print(f"transactions_full.csv ({len(tx):,} rows). Too large for Excel, open it in VS Code or pandas.")
    print(f"\nFiles are in {a.out}")


if __name__ == "__main__":
    main()