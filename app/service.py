"""All app logic, free of any UI code. Pages call these functions and only render the results.

Every function takes the database connection first (app/db.py: SQLite or PostgreSQL through SQLAlchemy Core). A
function that writes more than one row does so in ONE transaction.

Two separate flows:
- Check score (run_score_check): score an uploaded statement at the MEDIAN request (predict.py does this) and add
  the estimated eligibility (src/eligibility.py, a prototype policy). No amount or term is asked for.
- Apply (submit_application): uses the vendor's SAVED score check (at most APPLY_CHECK_MAX_AGE_DAYS old); there is no
  second upload. The check's estimated limit decides whether anything is sent, and the lender receives a summary
  snapshot built from that check (never recomputed, never the statement). The application row stores the check id.

Privacy: an uploaded statement is read once, in memory, through predict.score_uploaded_file (one temporary file,
deleted in a `finally`). Nothing from the statement is stored, logged or put in an error message: the database keeps
only results (score, ratings, reason phrases, request, derived monthly income, eligibility amounts, rows read), and
the audit log keeps actions, ids and fixed reason codes (never amounts, file names or statement content).

Model files: APP_MODEL_PATH and APP_REFERENCE_PATH override models/logistic.joblib and models/reference.json.
"""
import json
import math
import os
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import SQLAlchemyError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import eligibility as EL  # noqa: E402
import predict as P  # noqa: E402
from pdf_statement import NoTextLayerError, PasswordError, StatementError  # noqa: E402

from app import auth, db  # noqa: E402
from app.db import applications, repayments, score_checks, users  # noqa: E402

ALLOWED_EXTENSIONS = (".xlsx", ".xls", ".csv", ".pdf")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PILLAR_NAMES = {
    "A_income_stability": "Income stability",
    "B_cash_flow_buffer": "Cash flow buffer",
    "C_borrowing_distress": "Borrowing distress",
    "D_affordability": "Affordability",
    "E_obligations": "Obligations",
    "F_history_growth": "History and growth",
    "G_network": "Network",
}
SNAPSHOT_KEYS = ("score", "tier", "pd", "pillars", "reasons", "data_notes", "request", "affordability", "eligibility")
PROFILE_FLAGS = ("share_with_lenders", "save_results", "email_notifications")
REF_OFFSET = 100                     # application reference = "A-" + (row id + 100): A-101, A-102, ...

# submit_application outcomes, and the fixed reason codes written to the audit log for a refusal
OUTCOME_SENT = "sent"
OUTCOME_NOT_ELIGIBLE = "not eligible"
OUTCOME_NO_INCOME = "not enough income data"
OUTCOME_ABOVE_LIMIT = "above limit"
REFUSAL_CODES = {OUTCOME_NOT_ELIGIBLE: "not_eligible", OUTCOME_NO_INCOME: "no_income_data", OUTCOME_ABOVE_LIMIT: "above_limit"}

MSG_TYPE = "Upload an Excel (.xlsx, .xls) or CSV statement, or a PDF with selectable text."
MSG_SIZE = "The file is larger than 10 MB."
MSG_EMPTY = "The file is empty."
MSG_NO_TEXT_PDF = "This PDF has no selectable text. Please upload the Excel or CSV statement."
MSG_PDF_PASSWORD = "This PDF is password protected. Please upload the Excel or CSV statement."
MSG_UNREADABLE = "We could not read this statement. Please upload the Excel or CSV statement from M-Pesa."
MSG_TOO_SHORT = "This statement is too short or has no transactions we can use. Please upload a longer statement."
MSG_NO_MODEL = "The scoring engine is still starting. Try again in a moment."
# fixed reason codes of a rejected upload (audit log "upload_rejected"); never the file name or its content.
# MSG_NO_MODEL is not here: the engine was not ready, the upload itself was not at fault.
UPLOAD_REJECT_CODES = {MSG_TYPE: "file_type", MSG_SIZE: "too_large", MSG_EMPTY: "empty", MSG_NO_TEXT_PDF: "pdf_no_text",
                       MSG_PDF_PASSWORD: "pdf_password", MSG_UNREADABLE: "unreadable", MSG_TOO_SHORT: "too_short"}
MSG_DB_SAVE = "Could not save your result. Please try again."
MSG_DB_APPLY = "Could not send your application. Please try again."
MSG_CONSENT = "Tick the box to share this summary with the lender."
# Apply uses a saved score check no older than this (one place to change it)
APPLY_CHECK_MAX_AGE_DAYS = 30
MSG_CHECK_AGAIN = "Check your score again to apply."
MSG_CHECK_UNAVAILABLE = "This score check is not available. Check your score again to apply."
MSG_CHECK_EXPIRED = (f"Your last score check is more than {APPLY_CHECK_MAX_AGE_DAYS} days old. "
                     "Check your score again to apply.")
MSG_DUPLICATE = "You already have a pending application to this lender with this score check."
DB_ERRORS = (SQLAlchemyError, db.DatabaseUnavailable)


class UserError(ValueError):
    """A problem the user can fix. The message is fixed text: it never holds statement content."""


# ------------------------------------------------------------------ reference values
def model_path() -> Path:
    return Path(os.environ.get("APP_MODEL_PATH") or ROOT / "models" / "logistic.joblib")


def reference_path() -> Path:
    return Path(os.environ.get("APP_REFERENCE_PATH") or ROOT / "models" / "reference.json")


_REF = {}


def reference() -> dict:
    p = reference_path()
    if not p.exists():
        raise UserError(MSG_NO_MODEL)
    key = (str(p), p.stat().st_mtime)
    if key not in _REF:
        _REF.clear()
        _REF[key] = json.loads(p.read_text(encoding="utf-8"))
    return _REF[key]


def median_request() -> tuple:
    """(amount, term) of the median request in reference.json: the Apply form defaults and the request the score uses."""
    r = reference()
    return float(r["requested_amount"]["median"]), float(r["requested_term_days"]["median"])


def typical_amount_range() -> tuple:
    r = reference()["requested_amount"]
    return float(r["p01"]), float(r["p99"])


def cutoffs() -> EL.Cutoffs:
    """The affordability band cutoffs of the reference file (never hard-coded)."""
    return EL.cutoffs_from_reference(reference())


def warm_up() -> None:
    """Load the model and the SHAP explainer (a few seconds) in a background thread; errors are ignored here and
    reported when the user scores."""
    def _run():
        try:
            P.warm_up(str(model_path()), str(reference_path()))
        except Exception:      # noqa: BLE001 - missing model files are reported on the Score page
            pass
    threading.Thread(target=_run, daemon=True).start()


# ------------------------------------------------------------------ affordability (no re-scoring)
def affordability_band(amount, monthly_income, ref: dict | None = None) -> str:
    """'comfortable' / 'stretched' / 'heavy' from amount / monthly income and the cutoffs in reference.json
    (ratio <= p50, <= p85, above); 'unknown' without income. Same rule as predict._affordability."""
    if monthly_income is None or not math.isfinite(float(monthly_income)) or float(monthly_income) <= 0:
        return "unknown"
    b = (ref or reference())["affordability_bands"]
    ratio = float(amount) / float(monthly_income)
    return "comfortable" if ratio <= b["p50"] else "stretched" if ratio <= b["p85"] else "heavy"


def affordability(amount, monthly_income, ref: dict | None = None) -> dict:
    """The loan check for one amount: share of monthly income, band, and whether the amount is outside the range of
    simulated requests. Recomputed from monthly income only; the score is never touched."""
    ref = ref or reference()
    ok = monthly_income is not None and math.isfinite(float(monthly_income)) and float(monthly_income) > 0
    lo, hi = float(ref["requested_amount"]["p01"]), float(ref["requested_amount"]["p99"])
    return {"amount": float(amount), "share_of_monthly_income": float(amount) / float(monthly_income) if ok else None,
            "band": affordability_band(amount, monthly_income, ref), "outside_typical_range": not lo <= float(amount) <= hi}


# ------------------------------------------------------------------ accounts
def register_vendor(conn, name, email, password, confirm, now=None) -> dict:
    """Self-registration (vendors only). Returns the new user."""
    auth.check_new_password(password, confirm)
    with db.transaction(conn):                      # the user and its audit row, together
        uid = auth.create_user(conn, email, name, password, "vendor", now=now)
        db.audit(conn, "register", actor_id=uid, target=f"user:{uid}", now=now)
    return auth.get_user(conn, uid)


ORG_MIN, ORG_MAX = 2, 80
ORG_MISSING = "Enter your organisation name."
ORG_LENGTH = f"Use {ORG_MIN} to {ORG_MAX} characters for the organisation name."
ORG_TAKEN = "This organisation already has a lender account."


def normalise_org(org_name) -> str:
    """Trimmed, with runs of spaces collapsed to one ("  Umoja   SACCO " -> "Umoja SACCO")."""
    return " ".join((org_name or "").split())


def org_taken(conn, org: str) -> bool:
    """True if a lender account already has this organisation name (case-insensitive, after normalise_org)."""
    org = normalise_org(org)
    return db.one(conn, select(users.c.id).where(users.c.role == "lender",
                                                 func.lower(users.c.org_name) == org.lower())) is not None


def register_lender(conn, name, email, org_name, password, confirm, now=None) -> dict:
    """Self-registration of a lender: always role "lender", active at once (no role parameter, so it can never create
    an admin). A lender account IS the organisation, so the name must be new: one lender account per organisation."""
    auth.check_new_password(password, confirm)
    org = normalise_org(org_name)
    if not org:
        raise auth.AuthError(ORG_MISSING)
    if not ORG_MIN <= len(org) <= ORG_MAX:
        raise auth.AuthError(ORG_LENGTH)
    with db.transaction(conn):                      # the check, the user and its audit row, together
        if org_taken(conn, org):
            raise auth.AuthError(ORG_TAKEN)
        uid = auth.create_user(conn, email, name, password, "lender", org_name=org, now=now)
        db.audit(conn, "lender_registered", actor_id=uid, target=f"user:{uid}", now=now)
    return auth.get_user(conn, uid)


def authenticate(conn, email, password, now=None) -> dict:
    """Sign in; writes a sign_in or sign_in_failed audit row (with the user id if the email exists, never the
    password or the typed email)."""
    try:
        user = auth.authenticate(conn, email, password, now=now)
    except auth.AuthError as e:
        db.audit(conn, "sign_in_failed", actor_id=auth.find_user_id(conn, email),
                 detail="locked" if str(e) == auth.ACCOUNT_LOCKED else None, now=now)
        raise
    db.audit(conn, "sign_in", actor_id=user["id"], now=now)
    return user


def update_profile_flags(conn, user_id, **flags) -> dict:
    unknown = set(flags) - set(PROFILE_FLAGS)
    if unknown:
        raise ValueError(f"unknown profile flags: {sorted(unknown)}")
    if flags:
        with db.transaction(conn):
            conn.execute(update(users).where(users.c.id == user_id).values(**{k: bool(v) for k, v in flags.items()}))
    return auth.get_user(conn, user_id)


def change_password(conn, user, current, new, confirm) -> None:
    with db.transaction(conn):
        auth.change_password(conn, user["id"], current, new, confirm)
        db.audit(conn, "password_changed", actor_id=user["id"])


# ------------------------------------------------------------------ scoring an upload (shared by both flows)
def _upload_bytes(file, filename) -> tuple:
    name = filename if filename is not None else getattr(file, "name", "")
    ext = Path(str(name)).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise UserError(MSG_TYPE)
    size = getattr(file, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise UserError(MSG_SIZE)
    if isinstance(file, (bytes, bytearray, memoryview)):
        data = bytes(file)
    elif hasattr(file, "getvalue"):
        data = file.getvalue()
    elif hasattr(file, "read"):
        data = file.read()
    else:
        raise UserError(MSG_TYPE)
    if len(data) > MAX_UPLOAD_BYTES:
        raise UserError(MSG_SIZE)
    if not data:
        raise UserError(MSG_EMPTY)
    return data, ext


def _positive(value, what) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise UserError(f"Enter a number for {what}.") from None
    if not math.isfinite(v) or v <= 0:
        raise UserError(f"Enter a number above 0 for {what}.")
    return v


def _phrase(label: str) -> str:
    return label[:1].upper() + label[1:]


def _score_upload(file, filename, amount=None, term=None) -> tuple:
    """Read the upload (in memory; one temporary file deleted in a finally inside predict) and score it.
    amount/term None = the median request. Returns (predict result, amount used, term used).
    Raises UserError with a fixed message for anything the user can fix; never the exception text."""
    data, ext = _upload_bytes(file, filename)
    if amount is None or term is None:
        amount, term = median_request()
    if not model_path().exists():
        raise UserError(MSG_NO_MODEL)
    try:
        res = P.score_uploaded_file(data, "statement" + ext, amount, term,
                                    model_path=str(model_path()), reference_path=str(reference_path()))
    except NoTextLayerError:
        raise UserError(MSG_NO_TEXT_PDF) from None
    except PasswordError:
        raise UserError(MSG_PDF_PASSWORD) from None
    except StatementError:
        raise UserError(MSG_UNREADABLE) from None
    except (FileNotFoundError, ImportError, MemoryError):   # model or reference files, or shap still loading
        raise UserError(MSG_NO_MODEL) from None
    except ValueError as e:
        # predict.py: "The statement has no transactions...", "No usable transactions before the application date"
        raise UserError(MSG_TOO_SHORT if "transactions" in str(e) else MSG_UNREADABLE) from None
    except Exception:       # noqa: BLE001 - any other reader failure: a fixed message, never the exception text
        raise UserError(MSG_UNREADABLE) from None
    finally:
        data = None
    return res, float(amount), float(term)


def _score_or_audit(conn, user, file, filename, amount=None, term=None, now=None) -> tuple:
    """_score_upload, and an "upload_rejected" audit row with a fixed reason code when the statement is refused.
    The UserError is raised again unchanged; losing the audit row never hides it."""
    try:
        return _score_upload(file, filename, amount, term)
    except UserError as e:
        code = UPLOAD_REJECT_CODES.get(str(e))
        if code is not None:
            try:
                db.audit(conn, "upload_rejected", actor_id=user["id"], detail=code, now=now)
            except DB_ERRORS:
                pass
        raise


def _summary(res: dict, amount: float, term: float, created) -> dict:
    """What the app keeps of a score result (no statement content), with the estimated eligibility."""
    aff = res["affordability"]
    ratio = aff["amount_to_avg_monthly_income_90"]
    monthly = amount / ratio if ratio else None
    codes = [w["code"] for w in res["warnings"]]
    return {
        "check_id": None,
        "created_at": db.iso(created),
        "score": int(res["score"]),
        "pd": float(res["probability_of_default"]),
        "tier": res["tier"],
        "pillars": [{"key": p["pillar"], "name": PILLAR_NAMES[p["pillar"]], "rating": int(p["rating"]), "label": p["label"]}
                    for p in res["pillar_ratings"]],
        "reasons": [{"phrase": _phrase(r["label"]), "direction": "Raises risk" if r["direction"] == "raises risk" else "Lowers risk"}
                    for r in res["top_reasons"]],
        "data_notes": [n["label"] for n in res["data_notes"]],
        "request_amount": amount,
        "request_term": term,
        "monthly_income": monthly,
        "affordability_band": aff["band"],
        "outside_typical_range": "request_outside_training_range" in codes,
        "thin_history": "thin_history" in codes,
        "rows_read": int(res["inputs_used"]["transactions_used"]),
        "eligibility": EL.eligibility(res["tier"], monthly, cutoffs()),
    }


# ------------------------------------------------------------------ check score
def run_score_check(conn, user, file, filename=None, now=None) -> dict:
    """Score an uploaded statement for a vendor (at the median request) and return the summary with the estimated
    eligibility. `file` is a Streamlit UploadedFile, a binary file object or bytes (then pass `filename`; only its
    extension is used). The statement is never stored; the summary is saved only if save_results is on."""
    auth.require_role(user, "vendor")
    res, amount, term = _score_or_audit(conn, user, file, filename, now=now)
    created = db.utcnow(now)
    summary = _summary(res, amount, term, created)
    summary["save_error"] = None
    el = summary["eligibility"]
    try:
        with db.transaction(conn):                 # the saved check and its audit row, together
            if user.get("save_results"):
                r = conn.execute(insert(score_checks).values(
                    user_id=user["id"], created_at=created, score=summary["score"], pd=summary["pd"],
                    tier=summary["tier"], pillars_json=json.dumps(summary["pillars"]),
                    reasons_json=json.dumps(summary["reasons"]), data_notes_json=json.dumps(summary["data_notes"]),
                    request_amount=amount, request_term=term, monthly_income=summary["monthly_income"],
                    affordability_band=summary["affordability_band"], rows_read=summary["rows_read"],
                    max_amount=el["max_amount"], comfortable_amount=el["comfortable_amount"]))
                summary["check_id"] = int(r.inserted_primary_key[0])
            db.audit(conn, "score_check", actor_id=user["id"],
                     target=f"check:{summary['check_id']}" if summary["check_id"] else "not_saved", now=now)
    except DB_ERRORS:
        # the score was computed: keep it for this session and say it could not be saved (the transaction rolled back)
        summary["check_id"] = None
        summary["save_error"] = MSG_DB_SAVE
    return summary


def _eligibility_from_row(row: dict) -> dict:
    if row["monthly_income"] is None or row["max_amount"] is None:
        return {"status": "unknown", "max_amount": None, "comfortable_amount": None}
    mx = int(row["max_amount"])
    return {"status": "eligible" if mx > 0 else "not_eligible", "max_amount": mx,
            "comfortable_amount": int(row["comfortable_amount"] or 0)}


def _check_from_row(row: dict) -> dict:
    return {"check_id": row["id"], "created_at": db.iso(row["created_at"]), "score": row["score"], "pd": row["pd"],
            "tier": row["tier"], "pillars": json.loads(row["pillars_json"]), "reasons": json.loads(row["reasons_json"]),
            "data_notes": json.loads(row["data_notes_json"]), "request_amount": row["request_amount"],
            "request_term": row["request_term"], "monthly_income": row["monthly_income"],
            "affordability_band": row["affordability_band"], "outside_typical_range": None, "thin_history": None,
            "rows_read": row["rows_read"], "eligibility": _eligibility_from_row(row)}


def recent_checks(conn, user_id, limit: int | None = 5) -> list:
    """The saved checks of a vendor, newest first: at most `limit` (None = all). The one checks query of a page: Home
    and Result take the latest 5 (the score card and its chart), History takes all of them."""
    stmt = (select(score_checks).where(score_checks.c.user_id == user_id)
            .order_by(score_checks.c.created_at.desc(), score_checks.c.id.desc()))
    if limit is not None:
        stmt = stmt.limit(limit)
    return [_check_from_row(r) for r in db.all_rows(conn, stmt)]


def latest_check(conn, user_id) -> dict | None:
    checks = recent_checks(conn, user_id, limit=1)
    return checks[0] if checks else None


def score_history(conn, user_id) -> list:
    """[(created_at ISO string, score)] of the saved checks, oldest first."""
    rows = db.all_rows(conn, select(score_checks.c.created_at, score_checks.c.score)
                       .where(score_checks.c.user_id == user_id).order_by(score_checks.c.created_at, score_checks.c.id))
    return [(db.iso(r["created_at"]), r["score"]) for r in rows]


def delete_saved_results(conn, user, now=None) -> int:
    """Delete all saved score checks of the user. Applications keep their own snapshot (check_id becomes NULL)."""
    with db.transaction(conn):
        conn.execute(update(applications).where(applications.c.check_id.in_(
            select(score_checks.c.id).where(score_checks.c.user_id == user["id"]))).values(check_id=None))
        n = conn.execute(delete(score_checks).where(score_checks.c.user_id == user["id"])).rowcount
        db.audit(conn, "delete_saved_results", actor_id=user["id"], target=f"user:{user['id']}", detail=f"checks={n}",
                 now=now)
    return int(n)


# ------------------------------------------------------------------ lenders and applications
def list_lenders(conn) -> list:
    return db.all_rows(conn, select(users.c.id, users.c.org_name)
                       .where(users.c.role == "lender", users.c.is_active.is_(True)).order_by(users.c.org_name, users.c.id))


def snapshot(summary: dict) -> dict:
    """What a lender receives, from ONE scoring of the statement: score, tier, chance of default, pillar ratings,
    reasons, data notes, the requested amount and term, the affordability band of that amount and the estimated
    eligibility. Nothing else (no statement, no transactions, no monthly income)."""
    el = summary["eligibility"]
    return {
        "score": int(summary["score"]),
        "tier": summary["tier"],
        "pd": float(summary["pd"]),
        "pillars": [{"name": p["name"], "rating": int(p["rating"]), "label": p["label"]} for p in summary["pillars"]],
        "reasons": [{"phrase": r["phrase"], "direction": r["direction"]} for r in summary["reasons"]],
        "data_notes": list(summary["data_notes"]),
        "request": {"amount": float(summary["request_amount"]), "term_days": float(summary["request_term"])},
        "affordability": {"band": summary["affordability_band"]},
        "eligibility": {"max_amount": el["max_amount"], "comfortable_amount": el["comfortable_amount"]},
    }


def _insert_application(conn, vendor, lender, snap: dict, now=None, check_id: int | None = None) -> dict:
    """Store an application bound to the score check it was made from. The reference is "A-" + (row id + 100), set in
    the same transaction as the insert: ids are unique, so two applications sent at the same moment can never share
    a reference. Audit row "application_submitted": the application id and the score check id only."""
    created = db.utcnow(now)
    with db.transaction(conn):
        app_id = int(conn.execute(insert(applications).values(
            vendor_id=vendor["id"], lender_id=lender["id"], check_id=check_id, snapshot_json=json.dumps(snap),
            status="pending", created_at=created)).inserted_primary_key[0])
        ref = f"A-{REF_OFFSET + app_id}"
        conn.execute(update(applications).where(applications.c.id == app_id).values(ref=ref))
        db.audit(conn, "application_submitted", actor_id=vendor["id"], target=f"application:{app_id}",
                 detail=f"check:{check_id}" if check_id is not None else "check:none", now=now)
    return {"id": app_id, "ref": ref, "lender": lender["org_name"], "status": "pending", "created_at": db.iso(created),
            "check_id": check_id}


def _own_check(conn, user, check_id) -> dict | None:
    """The saved check `check_id` if it belongs to this vendor, else None (also for a bad or forged id)."""
    try:
        check_id = int(check_id)
    except (TypeError, ValueError):
        return None
    row = db.one(conn, select(score_checks).where(score_checks.c.id == check_id, score_checks.c.user_id == user["id"]))
    return _check_from_row(row) if row else None


def check_expired(check: dict, now=None) -> bool:
    """True when the check is more than APPLY_CHECK_MAX_AGE_DAYS old."""
    created = datetime.fromisoformat(check["created_at"])
    return db.utcnow(now) - created > timedelta(days=APPLY_CHECK_MAX_AGE_DAYS)


def check_for_apply(conn, user, now=None) -> tuple:
    """(the latest saved check to apply with, None) or (None, why): why is "not_saved" (no saved check and saving is
    switched off), "none" (no saved check) or "expired" (the latest is too old)."""
    auth.require_role(user, "vendor")
    check = latest_check(conn, user["id"])
    if check is None:
        return None, ("not_saved" if not user.get("save_results") else "none")
    if check_expired(check, now):
        return None, "expired"
    return check, None


def submit_application(conn, user, lender_id, check_id, amount, term, consent, now=None) -> dict:
    """Apply for a loan with one of the vendor's SAVED score checks. There is no upload and nothing is re-scored.

    Server-side rules, in this order: vendor only; consent; an active lender; amount and term above 0; the check
    belongs to this vendor (a forged or unknown id gets the same "not available" message); it is at most
    APPLY_CHECK_MAX_AGE_DAYS old; the check's estimated eligibility allows the amount; and no application from this
    vendor to this lender with this check is still pending.

    Returns {"outcome", "result" (the check), "max_amount", "application"}:
      "sent"                    stored, bound to the check (applications.check_id), snapshot built from the check
      "not eligible"            nothing sent
      "not enough income data"  nothing sent
      "above limit"             nothing sent; max_amount says how much the vendor can apply for
    Raises UserError for everything else (consent, lender, amount, check unavailable or expired, duplicate)."""
    auth.require_role(user, "vendor")
    if not consent:
        raise UserError(MSG_CONSENT)
    lender = db.one(conn, select(users.c.id, users.c.org_name).where(
        users.c.id == lender_id, users.c.role == "lender", users.c.is_active.is_(True)))
    if lender is None:
        raise UserError("Choose a lender.")
    amount, term = _positive(amount, "the amount"), _positive(term, "the number of days")
    check = _own_check(conn, user, check_id)
    if check is None:
        raise UserError(MSG_CHECK_UNAVAILABLE)
    if check_expired(check, now):
        raise UserError(MSG_CHECK_EXPIRED)
    el = check["eligibility"]
    out = {"outcome": None, "result": check, "max_amount": el["max_amount"], "application": None}
    if el["status"] == "not_eligible":
        out["outcome"] = OUTCOME_NOT_ELIGIBLE
    elif el["status"] == "unknown":
        out["outcome"] = OUTCOME_NO_INCOME
    elif amount > el["max_amount"]:
        out["outcome"] = OUTCOME_ABOVE_LIMIT
    if out["outcome"] is not None:
        try:
            db.audit(conn, "application_refused", actor_id=user["id"], detail=REFUSAL_CODES[out["outcome"]], now=now)
        except DB_ERRORS:
            pass                                   # the refusal stands; only its audit row is lost
        return out
    # the snapshot is the saved check as it is, with this request (the band is read from the check's monthly income)
    snap = snapshot(dict(check, request_amount=amount, request_term=term,
                         affordability_band=affordability_band(amount, check["monthly_income"])))
    a = applications
    try:
        with db.transaction(conn):                 # the duplicate check and the insert, together
            dup = conn.execute(select(a.c.id).where(a.c.vendor_id == user["id"], a.c.lender_id == lender["id"],
                                                    a.c.check_id == check["check_id"], a.c.status == "pending")
                               .limit(1)).first()
            if dup is not None:
                raise UserError(MSG_DUPLICATE)
            out["application"] = _insert_application(conn, user, lender, snap, now, check_id=check["check_id"])
    except DB_ERRORS:
        raise UserError(MSG_DB_APPLY) from None    # nothing was stored (one transaction)
    out["outcome"] = OUTCOME_SENT
    return out


# ------------------------------------------------------------------ repayments (shared rules; writes are in staff_service)
REPAYING, ON_TIME, LATE, DEFAULTED = db.REPAYMENT_STATUSES
TERMINAL_STATUSES = (ON_TIME, LATE, DEFAULTED)
REPAYMENT_LABEL = {REPAYING: "Repaying", ON_TIME: "Repaid on time", LATE: "Repaid late", DEFAULTED: "Defaulted"}
NAIROBI = timezone(timedelta(hours=3))
CLOCK = time.time                     # the real clock; tests replace it (or pass `now`) to control "today"


def now_utc(now: float | None = None) -> datetime:
    """The current time (UTC), from `now` (seconds since the epoch) or CLOCK."""
    return db.utcnow(CLOCK() if now is None else now)


def today(now: float | None = None) -> date:
    """Today's date in Nairobi."""
    return now_utc(now).astimezone(NAIROBI).date()


def due_date(decided_at: datetime | str, term_days) -> date:
    """The due date of an approved loan: the decision date (Nairobi) plus the repay-within days of the request."""
    d = datetime.fromisoformat(decided_at) if isinstance(decided_at, str) else decided_at
    return d.astimezone(NAIROBI).date() + timedelta(days=math.ceil(float(term_days)))


def repayment_view(app_status: str, decided_at, term_days, repay_status=None, stored_due=None, recorded_at=None,
                   now: float | None = None) -> dict | None:
    """The repayment of one application for display, or None when it is not approved. No row yet = "repaying"."""
    if app_status != "approved" or decided_at is None:
        return None
    due = stored_due or due_date(decided_at, term_days)
    if isinstance(due, str):
        due = date.fromisoformat(due)
    status = repay_status or REPAYING
    return {"status": status, "label": REPAYMENT_LABEL[status], "due_date": due.isoformat(),
            "days_left": (due - today(now)).days, "recorded_at": db.iso(recorded_at) if isinstance(recorded_at, datetime)
            else recorded_at, "terminal": status in TERMINAL_STATUSES}


def list_applications(conn, vendor_id, now: float | None = None) -> list:
    """The vendor's applications, newest first (ONE query), with the repayment status and due date of approved ones.
    Never the lender's repayment note."""
    a, r = applications, repayments
    rows = db.all_rows(conn, select(a.c.id, a.c.ref, a.c.status, a.c.lender_note, a.c.created_at, a.c.decided_at,
                                    a.c.snapshot_json, users.c.org_name, r.c.status.label("repay_status"),
                                    r.c.due_date, r.c.recorded_at)
                       .join_from(a, users, users.c.id == a.c.lender_id).outerjoin(r, r.c.application_id == a.c.id)
                       .where(a.c.vendor_id == vendor_id).order_by(a.c.created_at.desc(), a.c.id.desc()))
    out = []
    for row in rows:
        snap = json.loads(row["snapshot_json"])
        out.append({"id": row["id"], "ref": row["ref"], "status": row["status"], "lender": row["org_name"],
                    "lender_note": row["lender_note"], "created_at": db.iso(row["created_at"]),
                    "decided_at": db.iso(row["decided_at"]), "request": snap["request"], "score": snap["score"],
                    "tier": snap["tier"],
                    "repayment": repayment_view(row["status"], row["decided_at"], snap["request"]["term_days"],
                                                row["repay_status"], row["due_date"], row["recorded_at"], now)})
    return out
