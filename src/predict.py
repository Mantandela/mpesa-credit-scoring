"""Score one M-Pesa statement: probability of default, 300-850 score, risk tier, seven pillar ratings and the top reasons.

    score_statement(statement, requested_amount=None, requested_term_days=None, application_date=None,
                    model_path="models/logistic.joblib", reference_path="models/reference.json", password=None) -> dict

    score_uploaded_file(file_bytes_or_path, filename, requested_amount=None, requested_term_days=None, password=None)

`statement` is a raw transactions DataFrame (generator schema, or the table from pdf_statement.read_statement) or a
path to an .xlsx/.xls/.csv statement (or a PDF with a text layer; real M-Pesa PDFs are scanned images and cannot be
read). The pipeline is the training pipeline for one application:
clean.clean -> transactions before application_date -> features.build_row -> logistic model -> scoring.pd_to_score.

The score, pillar ratings and reasons are worked out at the MEDIAN request from reference.json, whatever amount and
term the caller passes: the trained model's coefficients on the request fields are not monotone, so scoring the
caller's request could show a larger loan as less risky. The requested amount and term feed only the separate
`affordability` block (ratios to income and a comfortable / stretched / heavy band, monotone by construction), as
typed: no clipping, only amounts and terms <= 0 are rejected.

Needs models/logistic.joblib (src/train_models.py) and models/reference.json + models/shap_background.parquet
(src/build_reference.py). All outcomes the model learned from are SIMULATED; see docs/scoring_function.md.

Nothing here prints or logs transaction details, names or phone numbers. The CLI prints only the result JSON.

CLI (repo root):  python src/predict.py <statement file> --amount 5000 --term 14 [--date 2026-03-15] [--ask-password]
"""
import argparse
import gc
import json
import math
import os
import sys
import tempfile
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
from pdf_statement import StatementError, counterparty_hash, counterparty_text, read_statement  # noqa: E402
from scoring import pd_to_score, risk_tier  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
THIN_HISTORY_DAYS = max(Fe.WINDOWS)          # the features look back 90 days
N_REASONS = 5
RATING_LABELS = ((25, "Weak"), (50, "Fair"), (75, "Good"), (101, "Strong"))
REQUIRED = ("completion_time", "details", "paid_in", "withdrawn", "balance")
AFFORDABILITY_BANDS = ("comfortable", "stretched", "heavy")       # up to p50, up to p85, above p85
BAND_NOTES = {
    "comfortable": "Compared with your income, this loan is no larger than for a typical applicant.",
    "stretched": "Compared with your income, this loan is larger than for a typical applicant.",
    "heavy": "Compared with your income, this loan is larger than for 85% of applicants.",
    "unknown": "No customer income in the last 90 days, so affordability cannot be judged.",
}
UPLOAD_TYPES = (".xlsx", ".xls", ".csv", ".pdf")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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
        raise TypeError("statement must be a DataFrame or a path to an .xlsx, .xls or .csv file (or a text PDF)")
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


def _request(name, value, rng, outside: dict) -> float:
    """The request exactly as typed (the training median when not given). No clipping: the model never sees it, it
    feeds only the affordability block. Must be a positive number; a value outside the 1st-99th percentile of the
    simulated requests is recorded in `outside` for an information warning."""
    if value is None:
        return float(rng["median"])
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.") from None
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"{name} must be a number greater than 0.")
    if v < rng["p01"] or v > rng["p99"]:
        outside[name] = {"entered": v, "p01": float(rng["p01"]), "p99": float(rng["p99"])}
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


# ------------------------------------------------------------------ low-level steps (also used by the tests)
def _used_transactions(statement, application_date=None, password=None) -> tuple:
    """Cleaned transactions before the application date: (used, cut, rows_after_date_ignored, warnings)."""
    tx, warnings = _prepare(statement, password)
    cleaned = clean.clean(tx)
    if application_date is None:
        cut = cleaned.completion_time.max().normalize() + pd.Timedelta(days=1)
    else:
        cut = pd.Timestamp(application_date).normalize()
    used = cleaned[cleaned.completion_time < cut]
    if used.empty or used.is_failed.all():
        raise ValueError(f"No usable transactions before the application date {cut.date().isoformat()}.")
    return used, cut, int((cleaned.completion_time >= cut).sum()), warnings


def _feature_frame(used, cut, amount, term, features) -> tuple:
    """features.build_row for one request: (row dict, one-row frame in the model's column order)."""
    app = SimpleNamespace(application_date=cut, requested_amount=float(amount), requested_term_days=float(term))
    row = Fe.build_row(used, app)
    return row, pd.DataFrame([row]).reindex(columns=features).astype(float)


def _probability(features_row: pd.DataFrame, model) -> float:
    """Probability of default from the trained pipeline for a one-row feature frame, for any request in the row."""
    return float(model.predict_proba(features_row)[0, 1])


def _affordability(row: dict, amount: float, term: float, ref: dict) -> dict:
    """Affordability of the request the caller gave, from the vendor's income (the same ratios as features.build_row).
    The band uses fixed cutoffs on amount_to_avg_monthly_income_90, so a larger amount never gives a better band."""
    bands = ref.get("affordability_bands")
    if bands is None:
        raise ValueError("models/reference.json has no affordability_bands. Rerun python src/build_reference.py.")
    obs90 = min(float(THIN_HISTORY_DAYS), float(row.get("history_days", 0.0)))
    r30 = Fe._div(amount, row.get("income_total_30", np.nan))
    r90 = Fe._div(amount, row.get("income_total_90", np.nan) * 30.0 / obs90 if obs90 else np.nan)
    if math.isnan(r90):
        band = "unknown"
    else:
        band = next(b for b, upper in zip(AFFORDABILITY_BANDS, (bands["p50"], bands["p85"], math.inf)) if r90 <= upper)
    return {"requested_amount": amount, "requested_term_days": term, "estimated_repayment": amount,
            "amount_to_income_30": _num(r30), "amount_to_avg_monthly_income_90": _num(r90), "band": band,
            "band_cutoffs": {"comfortable_up_to": bands["p50"], "stretched_up_to": bands["p85"]},
            "note": BAND_NOTES[band]}


# ------------------------------------------------------------------ scoring
def score_statement(statement, requested_amount=None, requested_term_days=None, application_date=None,
                    model_path="models/logistic.joblib", reference_path="models/reference.json", password=None) -> dict:
    bundle, ref, explainer, names = _models(model_path, reference_path)
    F = list(bundle["features"])
    # The request the caller gave is used, as typed, for the affordability block only. The score is worked out at the
    # median request, because the trained model's coefficients on the request fields are not monotone (a larger
    # request could lower the predicted risk). Checked before the statement is read.
    outside = {}
    amount = _request("requested_amount", requested_amount, ref["requested_amount"], outside)
    term = _request("requested_term_days", requested_term_days, ref["requested_term_days"], outside)
    used, cut, ignored, warnings = _used_transactions(statement, application_date, password)
    if outside:
        what = " and ".join("amount" if k == "requested_amount" else "term" for k in outside)
        warnings.append({"code": "request_outside_training_range", "fields": outside,
                         "message": f"The requested {what} is outside the range of the simulated loan requests "
                                    "(1st to 99th percentile). The affordability block uses it as entered; the band is "
                                    "relative to simulated requests. The score does not use the request."})
    med_amount, med_term = float(ref["requested_amount"]["median"]), float(ref["requested_term_days"]["median"])
    row, X = _feature_frame(used, cut, med_amount, med_term, F)
    warnings.append({"code": "score_at_median_request",
                     "message": f"The score is worked out for a typical loan (KES {med_amount:,.0f} for {med_term:g} days), "
                                "so it does not depend on the loan you ask for. See 'affordability' for your request."})

    pipe = bundle["model"]
    p = _probability(X, pipe)
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
    x0 = X.iloc[0]
    values = {n: (float(x0[n]) if i < len(F) else float(np.isnan(x0[FL.base_feature(n)]))) for i, n in enumerate(names)}
    # Neutral (no-data) items never count as reasons; one reason per family; contradictions keep the larger SHAP
    top, data_notes = FL.select_reasons(dict(zip(names, (float(s) for s in sv))), values,
                                        ref.get("feature_medians", {}), N_REASONS)

    history = float(row.get("history_days", 0.0))
    if history < THIN_HISTORY_DAYS:
        warnings.append({"code": "thin_history", "message": f"Only {history:.0f} days of history before the application date; "
                         f"the score is less reliable below {THIN_HISTORY_DAYS} days."})
    counts = {f: int(used[f].sum()) for f in clean.FLAGS if int(used[f].sum())}
    if counts:
        warnings.append({"code": "integrity_flags", "message": "Rows that broke a statement check (counts only).", "counts": counts})

    return {
        "probability_of_default": p,
        "score": int(pd_to_score(p)),
        "tier": risk_tier(p),
        "pillar_ratings": pillar_ratings,
        "top_reasons": top,
        "data_notes": data_notes,
        "affordability": _affordability(row, amount, term, ref),
        "inputs_used": {"requested_amount": amount, "requested_term_days": term,
                        "scored_at": {"requested_amount": med_amount, "requested_term_days": med_term},
                        "application_date": cut.date().isoformat(), "history_days": history,
                        "transactions_used": int(len(used)), "transactions_after_date_ignored": ignored},
        "warnings": warnings,
        "explanation": {"base_value": base, "logit": logit, "shap_values": {n: float(v) for n, v in zip(names, sv)}},
        "model_info": {"model": "logistic", "seed": bundle.get("seed"), "n_features": len(F),
                       "settings": bundle.get("settings"), "labels": "simulated"},
    }


# ------------------------------------------------------------------ uploads
def _delete(path: Path) -> None:
    """Delete a temporary upload. On Windows a reader can hold the file until garbage collection, so retry once."""
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        gc.collect()
        path.unlink(missing_ok=True)          # raises if the file still cannot be deleted: never leave it silently


def score_uploaded_file(file_bytes_or_path, filename, requested_amount=None, requested_term_days=None, password=None,
                        application_date=None, model_path="models/logistic.joblib",
                        reference_path="models/reference.json") -> dict:
    """Score an uploaded statement and return the score_statement result.

    file_bytes_or_path: the file's bytes, a binary file object (e.g. a web upload), or a path. `filename` gives the type
    (.xlsx, .xls, .csv or a PDF with a text layer); only its extension is used. The content is read into memory and
    written to ONE temporary file (random name, in the system temp folder) because the readers work from a path; that
    file is deleted in a `finally`, after success and after any error. The upload is never written anywhere else,
    logged or cached, and the result holds no statement content (no details, names, phone numbers or counterparties).
    """
    ext = Path(str(filename)).suffix.lower()
    if ext not in UPLOAD_TYPES:
        raise StatementError("Unsupported file type. Upload the Excel (.xlsx) or CSV version of your M-Pesa statement.")
    if isinstance(file_bytes_or_path, (str, os.PathLike)):
        data = Path(file_bytes_or_path).read_bytes()
    elif hasattr(file_bytes_or_path, "read"):
        data = file_bytes_or_path.read()
    else:
        data = file_bytes_or_path
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("file_bytes_or_path must be bytes, a binary file object or a path")
    if len(data) == 0:
        raise StatementError("The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise StatementError(f"The uploaded file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    fd, name = tempfile.mkstemp(prefix="statement_", suffix=ext)
    tmp = Path(name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        return score_statement(tmp, requested_amount, requested_term_days, application_date,
                               model_path=model_path, reference_path=reference_path, password=password)
    finally:
        _delete(tmp)


def main():
    ap = argparse.ArgumentParser(description="Score one M-Pesa statement. Prints JSON only.")
    ap.add_argument("statement", help=".xlsx, .xls or .csv (a PDF only if it has a text layer; M-Pesa PDFs are scanned)")
    ap.add_argument("--amount", type=float, default=None,
                    help="requested loan amount in KES, for the affordability block only (default: training median)")
    ap.add_argument("--term", type=float, default=None,
                    help="requested term in days, for the affordability block only (default: training median)")
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
