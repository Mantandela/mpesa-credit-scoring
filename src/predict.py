"""Score one M-Pesa statement: probability of default, 300-850 score, risk tier, seven pillar ratings and the top reasons.

    score_statement(statement, requested_amount=None, requested_term_days=None, application_date=None,
                    model_path="models/logistic.joblib", reference_path="models/reference.json", password=None) -> dict

`statement` is a raw transactions DataFrame (generator schema, or the table from pdf_statement.read_statement) or a
path to a .pdf/.xlsx/.xls/.csv statement. The pipeline is the training pipeline for one application:
clean.clean -> transactions before application_date -> features.build_row -> logistic model -> scoring.pd_to_score.

Needs models/logistic.joblib (src/train_models.py) and models/reference.json + models/shap_background.parquet
(src/build_reference.py). All outcomes the model learned from are SIMULATED; see docs/scoring_function.md.

Nothing here prints or logs transaction details, names or phone numbers. The CLI prints only the result JSON.

CLI (repo root):  python src/predict.py <statement file> --amount 5000 --term 14 [--date 2026-03-15] [--ask-password]
"""
import argparse
import json
import math
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean  # noqa: E402
import config as C  # noqa: E402
import features as Fe  # noqa: E402
import feature_labels as FL  # noqa: E402
import scorecard as SC  # noqa: E402
from pdf_statement import counterparty_hash, counterparty_text, read_statement  # noqa: E402
from scoring import pd_to_score, risk_tier  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
THIN_HISTORY_DAYS = max(Fe.WINDOWS)          # the features look back 90 days
N_REASONS = 5
RATING_LABELS = ((25, "Weak"), (50, "Fair"), (75, "Good"), (101, "Strong"))
REQUIRED = ("completion_time", "details", "paid_in", "withdrawn", "balance")


def _resolve(p) -> Path:
    p = Path(p)
    if not p.is_absolute() and not p.exists() and (ROOT / p).exists():
        return ROOT / p
    return p


@lru_cache(maxsize=4)
def _load(model_path: str, reference_path: str, model_mtime: float, ref_mtime: float):
    """Model, reference and SHAP explainer, cached per file version (keys include the modification times)."""
    import shap
    bundle = joblib.load(model_path)
    ref = json.loads(Path(reference_path).read_text(encoding="utf-8"))
    F = list(bundle["features"])
    if ref["features"] != F:
        raise ValueError("models/reference.json does not match the model's features. Rerun python src/build_reference.py.")
    pipe = bundle["model"]
    prep, lr = pipe[:-1], pipe.named_steps["m"]
    bg_path = Path(reference_path).with_name("shap_background.parquet")
    bg = pd.read_parquet(bg_path)[F]
    bg_t = prep.transform(bg)
    explainer = shap.LinearExplainer(lr, shap.maskers.Independent(bg_t, max_samples=len(bg_t)))
    ind = pipe.named_steps["imp"].indicator_
    names = F + ([f"{F[i]}{FL.MISSING_FLAG_SUFFIX}" for i in ind.features_] if ind is not None else [])
    return bundle, ref, explainer, names


def _models(model_path, reference_path):
    mp, rp = _resolve(model_path), _resolve(reference_path)
    for p, what in ((mp, "model"), (rp, "reference file")):
        if not p.exists():
            raise FileNotFoundError(f"{what} not found: {p.as_posix()}. Train the model and run python src/build_reference.py.")
    return _load(str(mp), str(rp), mp.stat().st_mtime, rp.stat().st_mtime)


def warm_up(model_path="models/logistic.joblib", reference_path="models/reference.json") -> None:
    """Load the model, reference and SHAP explainer once (importing shap takes a few seconds). Call at UI start-up."""
    _models(model_path, reference_path)


def _prepare(statement, password) -> tuple:
    """Raw transactions frame plus any reader warnings."""
    if isinstance(statement, (str, Path)):
        tx = read_statement(statement, password)
    elif isinstance(statement, pd.DataFrame):
        tx = statement.copy()
    else:
        raise TypeError("statement must be a DataFrame or a path to a .pdf, .xlsx, .xls or .csv file")
    warnings = list(tx.attrs.get("warnings", []))
    if tx.empty:
        raise ValueError("The statement has no transactions.")
    missing = [c for c in REQUIRED if c not in tx.columns]
    if missing:
        raise ValueError(f"The statement is missing columns: {missing}")
    if "vendor_id" not in tx:
        tx["vendor_id"] = "UPLOADED"
    if tx.vendor_id.nunique() > 1:
        raise ValueError("The statement holds more than one vendor. Score one vendor at a time.")
    if "receipt_no" not in tx:
        tx["receipt_no"] = [f"R{i:07d}" for i in range(len(tx))]
    if "counterparty_id" not in tx:
        tx["counterparty_id"] = tx["details"].fillna("").astype(str).map(lambda s: counterparty_hash(counterparty_text(s)))
    for c in ("paid_in", "withdrawn", "balance"):
        tx[c] = pd.to_numeric(tx[c], errors="coerce")
    tx["paid_in"] = tx["paid_in"].fillna(0.0)
    tx["withdrawn"] = tx["withdrawn"].fillna(0.0)
    tx["completion_time"] = pd.to_datetime(tx["completion_time"], errors="coerce", format="mixed")
    unreadable = tx["completion_time"].isna() | tx["balance"].isna()
    if unreadable.any():                                      # never drop rows silently
        warnings.append({"code": "unparsed_rows", "count": int(unreadable.sum()),
                         "message": f"{int(unreadable.sum())} rows had an unreadable time or balance and were skipped."})
        tx = tx[~unreadable]
    if tx.empty:
        raise ValueError("The statement has no transactions with a readable time and balance.")
    return tx, warnings


def _clip(name, value, rng, warnings):
    lo, hi = rng["p01"], rng["p99"]
    if value is None:
        return float(rng["median"])
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"{name} must be a number")
    if v < lo or v > hi:
        c = min(max(v, lo), hi)
        warnings.append({"code": f"{name}_clipped", "message": f"{name} {v:g} is outside the range seen in training "
                         f"({lo:g} to {hi:g}); scored as {c:g}.", "entered": v, "used": c})
        return c
    return v


def _rating(score: float, dist: list) -> int:
    """Percentile of a pillar score (higher = riskier) in the reference distribution, flipped so higher = better."""
    q = np.asarray(dist)
    pct = 100.0 * ((q < score).sum() + 0.5 * (q == score).sum()) / len(q)
    return int(round(100 - pct))


def _rating_label(r: int) -> str:
    return next(lbl for upper, lbl in RATING_LABELS if r < upper)


def _num(v):
    if v is None:
        return None
    v = float(v)
    return None if math.isnan(v) else v


def score_statement(statement, requested_amount=None, requested_term_days=None, application_date=None,
                    model_path="models/logistic.joblib", reference_path="models/reference.json", password=None) -> dict:
    bundle, ref, explainer, names = _models(model_path, reference_path)
    F = list(bundle["features"])
    tx, warnings = _prepare(statement, password)

    cleaned = clean.clean(tx)
    if application_date is None:
        cut = cleaned.completion_time.max().normalize() + pd.Timedelta(days=1)
    else:
        cut = pd.Timestamp(application_date).normalize()
    used = cleaned[cleaned.completion_time < cut]
    if used.empty or used.is_failed.all():
        raise ValueError(f"No usable transactions before the application date {cut.date().isoformat()}.")

    amount = _clip("requested_amount", requested_amount, ref["requested_amount"], warnings)
    term = _clip("requested_term_days", requested_term_days, ref["requested_term_days"], warnings)
    app = SimpleNamespace(application_date=cut, requested_amount=amount, requested_term_days=term)
    row = Fe.build_row(used, app)
    X = pd.DataFrame([row]).reindex(columns=F).astype(float)

    pipe = bundle["model"]
    p = float(pipe.predict_proba(X)[0, 1])
    logit = float(pipe.decision_function(X)[0])

    # Pillar ratings against the reference population
    ps = SC.pillar_scores(X, stats=ref["scorecard"]["stats"]).iloc[0]
    pillar_ratings = []
    for k in C.SCORECARD_PILLARS:
        r = _rating(float(ps[k]), ref["pillar_distribution"]["values"][k])
        pillar_ratings.append({"pillar": k, "rating": r, "label": _rating_label(r), "pillar_score": float(ps[k])})

    # SHAP on the transformed matrix of the final logistic regression
    Xt = pipe[:-1].transform(X)
    sv = np.asarray(explainer.shap_values(Xt)).reshape(-1)
    base = float(np.asarray(explainer.expected_value).reshape(-1)[0])
    raw ={n: (row.get(n, np.nan) if i < len(F) else float(np.isnan(X.iloc[0][FL.base_feature(n)])))
           for i, n in enumerate(names)}
    med = ref.get("feature_medians", {})
    top = []
    for i in np.argsort(-np.abs(sv), kind="stable")[:N_REASONS]:      # ties keep feature order (deterministic)
        n = names[i]
        v = _num(raw[n])
        top.append({"feature": n, "label": FL.label(n), "value": v,
                    "direction": "raises risk" if sv[i] > 0 else "lowers risk", "shap_value": float(sv[i]),
                    "sentence": FL.reason_sentence(n, float(sv[i]), v, med.get(FL.base_feature(n)))})

    history = float(row.get("history_days", 0.0))
    if history < THIN_HISTORY_DAYS:
        warnings.append({"code": "thin_history", "message": f"Only {history:.0f} days of history before the application date; "
                         f"the score is less reliable below {THIN_HISTORY_DAYS} days."})
    counts = {f: int(used[f].sum()) for f in clean.FLAGS if int(used[f].sum())}
    if counts:
        warnings.append({"code": "integrity_flags", "message": "Rows that broke a statement check (counts only).", "counts": counts})
    ignored = int((cleaned.completion_time >= cut).sum())

    return {
        "probability_of_default": p,
        "score": int(pd_to_score(p)),
        "tier": risk_tier(p),
        "pillar_ratings": pillar_ratings,
        "top_reasons": top,
        "inputs_used": {"requested_amount": amount, "requested_term_days": term, "application_date": cut.date().isoformat(),
                        "history_days": history, "transactions_used": int(len(used)), "transactions_after_date_ignored": ignored},
        "warnings": warnings,
        "explanation": {"base_value": base, "logit": logit, "shap_values": {n: float(v) for n, v in zip(names, sv)}},
        "model_info": {"model": "logistic", "seed": bundle.get("seed"), "n_features": len(F),
                       "settings": bundle.get("settings"), "labels": "simulated"},
    }


def main():
    ap = argparse.ArgumentParser(description="Score one M-Pesa statement. Prints JSON only.")
    ap.add_argument("statement", help=".pdf, .xlsx, .xls or .csv")
    ap.add_argument("--amount", type=float, default=None, help="requested loan amount in KES (default: training median)")
    ap.add_argument("--term", type=float, default=None, help="requested term in days (default: training median)")
    ap.add_argument("--date", default=None, help="application date YYYY-MM-DD (default: the day after the last transaction)")
    ap.add_argument("--model", default="models/logistic.joblib")
    ap.add_argument("--reference", default="models/reference.json")
    ap.add_argument("--ask-password", action="store_true", help="prompt for the PDF password (not echoed)")
    ap.add_argument("--full", action="store_true", help="include all SHAP values in the output")
    a = ap.parse_args()
    pw = None
    if a.ask_password:
        import getpass
        pw = getpass.getpass("Statement password: ")
    try:
        out = score_statement(a.statement, a.amount, a.term, a.date, a.model, a.reference, password=pw)
    except (ValueError, FileNotFoundError) as e:
        print(json.dumps({"error": str(e)}, indent=2))
        raise SystemExit(1)
    if not a.full:
        out["explanation"].pop("shap_values")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
