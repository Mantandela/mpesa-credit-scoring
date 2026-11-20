"""All app logic, free of any UI code. Pages call these functions and only render the results.

Every function takes the database connection first (app/db.py: SQLite or PostgreSQL through SQLAlchemy Core). A
function that writes more than one row does so in ONE transaction.

Scoring goes through src/predict.py: the score, chance of default, tier, pillar ratings and reasons are evaluated at
the MEDIAN request (predict.py does this); the typed amount and term feed only the affordability check, as typed.

Privacy: an uploaded statement is read once, in memory, through predict.score_uploaded_file (one temporary file,
deleted in a `finally`). Nothing from the statement is stored, logged or put in an error message: the database keeps
only the result (score, ratings, reason phrases, request, derived monthly income, number of rows read), and lenders
receive only a summary snapshot.

Model files: APP_MODEL_PATH and APP_REFERENCE_PATH override models/logistic.joblib and models/reference.json.
"""
import json
import math
import os
import sys
import threading
from pathlib import Path

from sqlalchemy import delete, insert, select, update

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import predict as P  # noqa: E402
from pdf_statement import NoTextLayerError, PasswordError, StatementError  # noqa: E402

from app import auth, db  # noqa: E402
from app.db import applications, score_checks, users  # noqa: E402

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
SNAPSHOT_KEYS = ("score", "tier", "pd", "pillars", "reasons", "request", "affordability")
PROFILE_FLAGS = ("share_with_lenders", "save_results", "email_notifications")
REF_OFFSET = 100                     # application reference = "A-" + (row id + 100): A-101, A-102, ...

MSG_TYPE = "Upload an Excel (.xlsx, .xls) or CSV statement, or a PDF with selectable text."
MSG_SIZE = "The file is larger than 10 MB."
MSG_EMPTY = "The file is empty."
MSG_NO_TEXT_PDF = "This PDF has no selectable text. Please upload the Excel or CSV statement."
MSG_PDF_PASSWORD = "This PDF is password protected. Please upload the Excel or CSV statement."
MSG_UNREADABLE = "We could not read this statement. Please upload the Excel or CSV statement from M-Pesa."
MSG_NO_TRANSACTIONS = "We found no transactions we could use in this statement."
MSG_NO_MODEL = "Scoring is not available right now."


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
    """(amount, term) of the median request in reference.json: the form defaults and the request the score uses."""
    r = reference()
    return float(r["requested_amount"]["median"]), float(r["requested_term_days"]["median"])


def typical_amount_range() -> tuple:
    r = reference()["requested_amount"]
    return float(r["p01"]), float(r["p99"])


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


# ------------------------------------------------------------------ score check
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


def _summary(res: dict, amount: float, term: float, created) -> dict:
    aff = res["affordability"]
    ratio = aff["amount_to_avg_monthly_income_90"]
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
        "monthly_income": amount / ratio if ratio else None,
        "affordability_band": aff["band"],
        "outside_typical_range": "request_outside_training_range" in codes,
        "thin_history": "thin_history" in codes,
        "rows_read": int(res["inputs_used"]["transactions_used"]),
    }


def run_score_check(conn, user, file, amount, term, filename=None, now=None) -> dict:
    """Score an uploaded statement for a vendor and return the result summary.

    `file` is a Streamlit UploadedFile, a binary file object or bytes (then pass `filename`; only its extension is
    used). The statement is never stored; the summary is saved only if the user's save_results setting is on.
    Raises UserError with a fixed, friendly message for a rejected or unreadable file.
    """
    auth.require_role(user, "vendor")
    data, ext = _upload_bytes(file, filename)
    amount, term = _positive(amount, "the amount"), _positive(term, "the number of days")
    try:
        res = P.score_uploaded_file(data, "statement" + ext, amount, term,
                                    model_path=str(model_path()), reference_path=str(reference_path()))
    except NoTextLayerError:
        raise UserError(MSG_NO_TEXT_PDF) from None
    except PasswordError:
        raise UserError(MSG_PDF_PASSWORD) from None
    except StatementError:
        raise UserError(MSG_UNREADABLE) from None
    except FileNotFoundError:
        raise UserError(MSG_NO_MODEL) from None
    except ValueError as e:
        raise UserError(MSG_NO_TRANSACTIONS if "transactions" in str(e) else MSG_UNREADABLE) from None
    except Exception:       # noqa: BLE001 - any other reader failure: a fixed message, never the exception text
        raise UserError(MSG_UNREADABLE) from None
    finally:
        data = None
    created = db.utcnow(now)
    summary = _summary(res, amount, term, created)
    with db.transaction(conn):                     # the saved check and its audit row, together
        if user.get("save_results"):
            r = conn.execute(insert(score_checks).values(
                user_id=user["id"], created_at=created, score=summary["score"], pd=summary["pd"], tier=summary["tier"],
                pillars_json=json.dumps(summary["pillars"]), reasons_json=json.dumps(summary["reasons"]),
                data_notes_json=json.dumps(summary["data_notes"]), request_amount=amount, request_term=term,
                monthly_income=summary["monthly_income"], affordability_band=summary["affordability_band"],
                rows_read=summary["rows_read"]))
            summary["check_id"] = int(r.inserted_primary_key[0])
        db.audit(conn, "score_check", actor_id=user["id"],
                 target=f"check:{summary['check_id']}" if summary["check_id"] else "not_saved", now=now)
    return summary


def _check_from_row(row: dict) -> dict:
    return {"check_id": row["id"], "created_at": db.iso(row["created_at"]), "score": row["score"], "pd": row["pd"],
            "tier": row["tier"], "pillars": json.loads(row["pillars_json"]), "reasons": json.loads(row["reasons_json"]),
            "data_notes": json.loads(row["data_notes_json"]), "request_amount": row["request_amount"],
            "request_term": row["request_term"], "monthly_income": row["monthly_income"],
            "affordability_band": row["affordability_band"], "outside_typical_range": None, "thin_history": None,
            "rows_read": row["rows_read"]}


def latest_check(conn, user_id) -> dict | None:
    row = db.one(conn, select(score_checks).where(score_checks.c.user_id == user_id)
                 .order_by(score_checks.c.created_at.desc(), score_checks.c.id.desc()).limit(1))
    return _check_from_row(row) if row else None


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


def snapshot(summary: dict, amount=None, term=None) -> dict:
    """What a lender receives: score, tier, chance of default, pillar ratings, reasons, request and affordability.
    Nothing else (no statement, no transactions, no monthly income, no data notes)."""
    amount = float(summary["request_amount"] if amount is None else amount)
    term = float(summary["request_term"] if term is None else term)
    aff = affordability(amount, summary.get("monthly_income"))
    return {
        "score": int(summary["score"]),
        "tier": summary["tier"],
        "pd": float(summary["pd"]),
        "pillars": [{"name": p["name"], "rating": int(p["rating"]), "label": p["label"]} for p in summary["pillars"]],
        "reasons": [{"phrase": r["phrase"], "direction": r["direction"]} for r in summary["reasons"]],
        "request": {"amount": amount, "term_days": term},
        "affordability": {"band": aff["band"], "share_of_monthly_income": aff["share_of_monthly_income"]},
    }


def create_application(conn, vendor, lender_id, summary, amount=None, term=None, consent=False, now=None) -> dict:
    """Send the summary snapshot to one lender. Requires the vendor's consent.

    The reference is "A-" + (row id + 100), set in the same transaction as the insert: ids are unique, so two
    applications sent at the same moment can never get the same reference (no COUNT query that could race)."""
    auth.require_role(vendor, "vendor")
    if not consent:
        raise UserError("Tick the box to share this summary with the lender.")
    lender = db.one(conn, select(users.c.id, users.c.org_name).where(
        users.c.id == lender_id, users.c.role == "lender", users.c.is_active.is_(True)))
    if lender is None:
        raise UserError("Choose a lender.")
    snap = snapshot(summary, amount, term)
    created = db.utcnow(now)
    with db.transaction(conn):
        check_id = summary.get("check_id")
        if check_id is not None and conn.execute(select(score_checks.c.id).where(
                score_checks.c.id == check_id, score_checks.c.user_id == vendor["id"])).first() is None:
            check_id = None
        app_id = int(conn.execute(insert(applications).values(
            vendor_id=vendor["id"], lender_id=lender["id"], check_id=check_id, snapshot_json=json.dumps(snap),
            status="pending", created_at=created)).inserted_primary_key[0])
        ref = f"A-{REF_OFFSET + app_id}"
        conn.execute(update(applications).where(applications.c.id == app_id).values(ref=ref))
        db.audit(conn, "application_sent", actor_id=vendor["id"], target=ref, detail=f"lender:{lender['id']}", now=now)
    return {"id": app_id, "ref": ref, "lender": lender["org_name"], "status": "pending", "created_at": db.iso(created)}


def list_applications(conn, vendor_id) -> list:
    a = applications
    rows = db.all_rows(conn, select(a.c.id, a.c.ref, a.c.status, a.c.lender_note, a.c.created_at, a.c.decided_at,
                                    a.c.snapshot_json, users.c.org_name)
                       .join_from(a, users, users.c.id == a.c.lender_id)
                       .where(a.c.vendor_id == vendor_id).order_by(a.c.created_at.desc(), a.c.id.desc()))
    out = []
    for r in rows:
        snap = json.loads(r["snapshot_json"])
        out.append({"id": r["id"], "ref": r["ref"], "status": r["status"], "lender": r["org_name"],
                    "lender_note": r["lender_note"], "created_at": db.iso(r["created_at"]), "decided_at": db.iso(r["decided_at"]),
                    "request": snap["request"], "score": snap["score"], "tier": snap["tier"]})
    return out
