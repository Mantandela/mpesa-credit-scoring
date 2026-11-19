"""Build the reference files that src/predict.py needs to score one new statement.

Writes two files into models/ (next to the trained models; built from synthetic data only, no personal data):
    models/reference.json            feature list, scorecard standardisation, pillar distributions, request defaults
    models/shap_background.parquet   200 training applications (raw features) used as the SHAP background

RERUN THIS SCRIPT whenever the model or the features change: after `python src/train_models.py`, after rebuilding
features (src/features.py) or the scorecard (src/scorecard.py). predict.py checks that the feature list in
reference.json equals the model's, but it cannot notice a stale distribution.

Contents of reference.json
- features: the model's feature list (asserted equal to data/processed/feature_columns.json)
- scorecard.stats: per scorecard feature, the median and std (ddof=0) that scorecard.pillar_scores standardises with,
  over ALL applications in features.parquet (the same population scorecard.py used), plus the mean (information only)
- feature_medians: median of every model feature over the same population (used to say "high" or "low" in reasons)
- pillar_distribution: 101 percentile points (0, 1, ..., 100) of each of the seven pillar scores over all applications
- requested_amount / requested_term_days: median, 1st and 99th percentile (self-check defaults and clipping range)
- background: how the SHAP background was drawn (TRAIN vendors from train_models.split_vendors, 200 rows, seed 42)

Run from the repo root:  python src/build_reference.py
"""
import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C  # noqa: E402
import scorecard as SC  # noqa: E402
from train_models import split_vendors  # noqa: E402

N_BACKGROUND = 200
BACKGROUND_SEED = 42
PERCENTILES = list(range(101))
REQUEST_COLUMNS = ("requested_amount", "requested_term_days")


def build(feat: pd.DataFrame, features: list, split_seed: int = 42, n_background: int = N_BACKGROUND,
          background_seed: int = BACKGROUND_SEED):
    """Return (reference dict, background DataFrame) from a features table with vendor_id and persona columns."""
    missing = [f for f in features if f not in feat.columns]
    if missing:
        raise ValueError(f"features missing from the table: {missing}")
    stats = SC.feature_stats(feat)
    ps = SC.pillar_scores(feat, stats=stats)
    # The stored statistics must reproduce the scorecard exactly on its own population
    assert np.allclose(ps.to_numpy(), SC.pillar_scores(feat).to_numpy(), rtol=0, atol=1e-12)
    ref = {
        "features": list(features),
        "n_applications": int(len(feat)),
        "scorecard": {"stats": stats, "clip": C.SCORE_CLIP,
                      "pillars": {k: dict(v) for k, v in C.SCORECARD_PILLARS.items()}},
        "feature_medians": {f: _num(feat[f].astype(float).median()) for f in features},
        "pillar_distribution": {"percentiles": PERCENTILES,
                                "values": {k: [float(v) for v in np.percentile(ps[k].to_numpy(), PERCENTILES)]
                                           for k in ps.columns}},
    }
    for c in REQUEST_COLUMNS:
        x = feat[c].astype(float)
        ref[c] = {"median": float(x.median()), "p01": float(x.quantile(0.01)), "p99": float(x.quantile(0.99))}
    assign = split_vendors(feat, split_seed)
    train = feat[feat.vendor_id.map(assign) == "train"]
    bg = train.sample(min(n_background, len(train)), random_state=background_seed)[features].reset_index(drop=True)
    ref["background"] = {"n": int(len(bg)), "seed": background_seed, "split": "train", "split_seed": split_seed,
                         "train_vendors": int(train.vendor_id.nunique())}
    return ref, bg


def _num(v):
    return None if pd.isna(v) else float(v)


def write(ref: dict, bg: pd.DataFrame, out_dir) -> tuple:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rp, bp = out_dir / "reference.json", out_dir / "shap_background.parquet"
    rp.write_text(json.dumps(ref, indent=1), encoding="utf-8")
    bg.to_parquet(bp, index=False)
    return rp, bp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="data/processed/features.parquet")
    ap.add_argument("--columns", default="data/processed/feature_columns.json")
    ap.add_argument("--model", default="models/logistic.joblib")
    ap.add_argument("--out", default="models")
    a = ap.parse_args()

    feat = pd.read_parquet(Path(a.features))
    F = json.loads(Path(a.columns).read_text())["features"]
    bundle = joblib.load(Path(a.model))
    assert list(bundle["features"]) == list(F), "the model's feature list differs from feature_columns.json; retrain or rebuild"
    seed = int(bundle.get("seed", 42))
    if seed != 42:
        print(f"note: the model was trained with seed {seed}; the background uses that seed's train vendors")
    ref, bg = build(feat, F, split_seed=seed)
    ref["model"] = {"path": Path(a.model).as_posix(), "seed": seed, "settings": bundle.get("settings")}
    rp, bp = write(ref, bg, a.out)
    print(f"{ref['n_applications']} applications, {len(F)} features, background {len(bg)} train rows")
    print(f"wrote {rp.as_posix()}\nwrote {bp.as_posix()}")


if __name__ == "__main__":
    main()
