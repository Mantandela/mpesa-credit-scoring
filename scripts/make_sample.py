"""Cut a small sample out of the full generated data so it can be pushed to GitHub and used by the tests.

Run from the repo root, after the pipeline has produced the full data (generator, clean, features, scorecard):
    python scripts/make_sample.py                       40 vendors, spread over the five personas
    python scripts/make_sample.py --n-vendors 60        a larger sample
    python scripts/make_sample.py --seed 7              a different draw of vendors

Reads   data/synthetic/ (vendors, loan_applications, transactions),
        data/interim/transactions_clean.parquet,
        data/processed/ (features.parquet, feature_columns.json)
Writes  data/sample/synthetic/, data/sample/interim/, data/sample/processed/  (same file names, same layout)

The sample keeps every vendor's whole statement and all of their applications, so the features and labels in it are exactly
the rows of the full run. Nothing is recomputed, which means the sample's default rate is only roughly the full 17%.
Files are written with zstd compression to keep them small. Nothing in data/ other than data/sample/ is changed.
"""
import argparse
import json
import os

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def pick_vendors(vendors, n, seed):
    """Choose n vendors with every persona represented, in proportion to its share (at least 3 each when possible)."""
    rng = np.random.default_rng(seed)
    n = min(n, len(vendors))
    counts = vendors.persona.value_counts()
    quota = (counts / counts.sum() * n).round().astype(int).clip(lower=min(3, n // len(counts)))
    chosen = []
    for persona, k in quota.items():
        ids = vendors.vendor_id[vendors.persona == persona].to_numpy()
        chosen.extend(rng.choice(ids, size=min(k, len(ids)), replace=False))
    return sorted(chosen)


def read_vendors_from_file(path, ids, columns=None):
    """Read only the rows of the chosen vendors, one row group at a time (the full file is hundreds of MB)."""
    pf = pq.ParquetFile(path)
    keep, ids = [], set(ids)
    for i in range(pf.num_row_groups):
        chunk = pf.read_row_group(i, columns=columns).to_pandas()
        chunk = chunk[chunk.vendor_id.isin(ids)]
        if len(chunk):
            keep.append(chunk)
    return pd.concat(keep, ignore_index=True)


def write(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), path, compression="zstd", compression_level=9,
                   row_group_size=max(len(df), 1))              # one row group: every vendor sits whole in it
    return os.path.getsize(path) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data", help="folder with synthetic/, interim/ and processed/")
    ap.add_argument("--out", default="data/sample")
    ap.add_argument("--n-vendors", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()

    def src(*p):
        return os.path.join(a.src, *p)

    vendors = pd.read_parquet(src("synthetic", "vendors.parquet"))
    ids = pick_vendors(vendors, a.n_vendors, a.seed)
    apps = pd.read_parquet(src("synthetic", "loan_applications.parquet"))
    apps = apps[apps.vendor_id.isin(ids)]
    feats = pd.read_parquet(src("processed", "features.parquet"))
    feats = feats[feats.vendor_id.isin(ids)]
    tx = read_vendors_from_file(src("synthetic", "transactions.parquet"), ids)
    ctx = read_vendors_from_file(src("interim", "transactions_clean.parquet"), ids)
    for name, d in (("transactions", tx), ("clean transactions", ctx)):
        d.sort_values(["vendor_id", "completion_time"], kind="stable", inplace=True)
        d.reset_index(drop=True, inplace=True)
    assert len(tx) == len(ctx), "raw and clean transactions have different row counts for the chosen vendors"
    assert set(feats.application_id) == set(apps.application_id), "features and applications disagree"

    sizes = {"synthetic/vendors.parquet": write(vendors[vendors.vendor_id.isin(ids)], os.path.join(a.out, "synthetic", "vendors.parquet")),
             "synthetic/loan_applications.parquet": write(apps, os.path.join(a.out, "synthetic", "loan_applications.parquet")),
             "synthetic/transactions.parquet": write(tx, os.path.join(a.out, "synthetic", "transactions.parquet")),
             "interim/transactions_clean.parquet": write(ctx, os.path.join(a.out, "interim", "transactions_clean.parquet")),
             "processed/features.parquet": write(feats, os.path.join(a.out, "processed", "features.parquet"))}
    os.makedirs(os.path.join(a.out, "processed"), exist_ok=True)
    with open(src("processed", "feature_columns.json")) as f:
        cols = json.load(f)
    with open(os.path.join(a.out, "processed", "feature_columns.json"), "w") as f:
        json.dump(cols, f, indent=2)

    print(f"sample: {len(ids)} vendors, {len(apps)} applications, {len(tx):,} transaction lines")
    print("vendors per persona:", vendors[vendors.vendor_id.isin(ids)].persona.value_counts().to_dict())
    if "defaulted" in feats:
        print(f"default rate in the sample: {feats.defaulted.mean():.1%} (full run is about 17%; a small sample varies)")
    for k, v in sizes.items():
        print(f"  {k:40s} {v:6.1f} MB")
    print(f"  total {sum(sizes.values()):.1f} MB, written to {a.out}")


if __name__ == "__main__":
    main()