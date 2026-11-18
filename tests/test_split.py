"""Unit test for the vendor-level split (src/train_models.py). Run from the repo root:  python -m pytest tests"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import train_models as T


def _toy(n_vendors=200, seed=0):
    rng = np.random.default_rng(seed)
    personas = rng.choice(["stable", "growing", "seasonal", "new", "struggling"], n_vendors)
    rows = []
    for i in range(n_vendors):
        for k in range(rng.integers(1, 5)):                       # up to four applications per vendor
            rows.append({"vendor_id": f"V{i:04d}", "application_id": f"A{i:04d}_{k}", "persona": personas[i]})
    return pd.DataFrame(rows)


def test_no_vendor_appears_in_two_splits():
    feat = _toy()
    feat["split"] = feat.vendor_id.map(T.split_vendors(feat, 42))
    assert not (feat.groupby("vendor_id").split.nunique() > 1).any()


def test_split_covers_every_vendor_with_roughly_70_15_15():
    feat = _toy()
    assign = T.split_vendors(feat, 42)
    assert set(assign) == set(feat.vendor_id)
    share = pd.Series(assign).value_counts(normalize=True)
    assert abs(share["train"] - 0.70) < 0.05 and abs(share["val"] - 0.15) < 0.05 and abs(share["test"] - 0.15) < 0.05


def test_split_is_reproducible_and_changes_with_the_seed():
    feat = _toy()
    assert T.split_vendors(feat, 42) == T.split_vendors(feat, 42)
    assert T.split_vendors(feat, 42) != T.split_vendors(feat, 7)


def test_every_persona_is_in_the_training_split():
    feat = _toy()
    feat["split"] = feat.vendor_id.map(T.split_vendors(feat, 42))
    assert set(feat[feat.split == "train"].persona) == set(feat.persona)