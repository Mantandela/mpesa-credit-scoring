"""Lender and admin logic, free of any UI code (the vendor logic is in app/service.py).

Every function takes the database connection and the SIGNED-IN user, and checks that user's role first
(auth.require_role), so a page or a call from another role gets auth.AccessDenied and nothing else, whatever the UI
shows or hides.

Lenders. A lender account IS the organisation: applications.lender_id is the id of the lender user, and users.org_name
holds the organisation's name (the vendor's Apply screen lists one row per active lender account). A lender reads and
decides only rows WHERE applications.lender_id = their own id; anything else is "not available", never "someone
else's". A lender sees the application snapshot the vendor shared (score summary, request, eligibility) and the vendor's
name, never the statement or the vendor's other checks. Lenders only approve or decline; the decision is final.

Admins. An admin sees counts, accounts (email, role, organisation of lenders, status) and the audit log as plain
language. An admin never reads notes or vendor names on screen, and cannot decide applications or record repayments.
The one exception is the outcomes export (export_outcomes): for future retraining it holds the snapshot score, PD,
tier and request of loans with a recorded final outcome, and nothing that identifies a person.

Repayments. A lender records what happened to a loan THEY approved: repaid on time, repaid late or defaulted (see
docs/repayment_outcomes.md). The outcome is final: only repaying -> a final status is allowed, and a default can be
recorded only after the due date. Every change writes an audit row; a refused attempt writes one generic audit line.

Audit rows hold actions, ids and references only (never notes, amounts, names or emails).
"""
import csv
import io
import json
import math
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import Text, and_, case, cast, func, insert, literal, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased

from app import auth, db, service
from app.db import applications, audit_log, repayments, score_checks, users

NOT_AVAILABLE = "This application is not available."
ALREADY_DECIDED = "This application has already been decided. The decision is final."
NOTE_MAX = 500
STAFF_ROLES = ("lender", "admin")
AUDIT_PAGE_SIZE = 50
PASSWORD_BYTES = 15                       # secrets.token_urlsafe(15): 20 characters, about 120 bits


class DecisionError(ValueError):
    """The decision could not be recorded (the message is fixed text, safe to show)."""


# ------------------------------------------------------------------ lender
def _snapshot_row(r: dict) -> dict:
    snap = json.loads(r["snapshot_json"])
    rep_ = service.repayment_view(r["status"], r["decided_at"], snap["request"]["term_days"], r["repay_status"],
                                  r["due_date"], r["recorded_at"])
    if rep_ is not None:
        rep_["note"] = r["repay_note"]                       # the lender's own note (escaped when shown)
    return {"id": r["id"], "ref": r["ref"], "vendor": r["vendor_name"], "status": r["status"],
            "created_at": db.iso(r["created_at"]), "decided_at": db.iso(r["decided_at"]),
            "request": snap["request"], "score": snap["score"], "tier": snap["tier"], "pd": snap["pd"],
            "eligibility": snap["eligibility"], "snapshot": snap, "lender_note": r["lender_note"], "repayment": rep_}


def _lender_select():
    a, r = applications, repayments
    return (select(a.c.id, a.c.ref, a.c.status, a.c.lender_note, a.c.created_at, a.c.decided_at, a.c.snapshot_json,
                   users.c.name.label("vendor_name"), r.c.status.label("repay_status"), r.c.due_date, r.c.recorded_at,
                   r.c.note.label("repay_note"))
            .join_from(a, users, users.c.id == a.c.vendor_id).outerjoin(r, r.c.application_id == a.c.id))


def lender_applications(conn, user) -> list:
    """The applications addressed to this lender, newest first (ONE query). Each row holds the shared snapshot and the
    vendor's name only."""
    auth.require_role(user, "lender")
    a = applications
    rows = db.all_rows(conn, _lender_select().where(a.c.lender_id == user["id"])
                       .order_by(a.c.created_at.desc(), a.c.id.desc()))
    return [_snapshot_row(r) for r in rows]


def lender_application(conn, user, app_id) -> dict:
    """One application addressed to this lender, or AccessDenied (also for an id that does not exist, so a lender
    cannot learn which references belong to other organisations)."""
    auth.require_role(user, "lender")
    try:
        app_id = int(app_id)
    except (TypeError, ValueError):
        raise auth.AccessDenied(NOT_AVAILABLE) from None
    a = applications
    row = db.one(conn, _lender_select().where(a.c.id == app_id, a.c.lender_id == user["id"]))
    if row is None:
        raise auth.AccessDenied(NOT_AVAILABLE)
    return _snapshot_row(row)


def decide_application(conn, user, app_id, decision: str, note: str | None = None, now=None) -> dict:
    """Approve or decline: ONE conditional UPDATE (only while the application is pending and addressed to this lender)
    and its audit row, in one transaction. A double click or a second tab finds the row already decided and is
    refused with DecisionError; nothing changes. Returns the decided application."""
    auth.require_role(user, "lender")
    if decision not in ("approved", "declined"):
        raise ValueError("decision must be 'approved' or 'declined'")
    note = (note or "").strip() or None
    if note is not None and len(note) > NOTE_MAX:
        raise DecisionError(f"Keep the note under {NOTE_MAX} characters.")
    current = lender_application(conn, user, app_id)            # AccessDenied for another organisation's application
    a = applications
    with db.transaction(conn):
        ref = conn.execute(update(a).where(a.c.id == current["id"], a.c.lender_id == user["id"], a.c.status == "pending")
                           .values(status=decision, lender_note=note, decided_at=db.utcnow(now))
                           .returning(a.c.ref)).scalar_one_or_none()
        if ref is not None:
            db.audit(conn, f"application_{decision}", actor_id=user["id"], target=ref, now=now)
    if ref is None:
        raise DecisionError(ALREADY_DECIDED)
    return lender_application(conn, user, current["id"])


# ------------------------------------------------------------------ lender: repayments
REPAY_REFUSED = "This outcome cannot be recorded."
ALREADY_RECORDED = "The outcome of this loan is already recorded. It cannot be changed."
NOT_APPROVED = "Only approved loans have a repayment to record."
TOO_EARLY_DEFAULT = "A default can be recorded only after the due date."
TOO_EARLY = "An outcome can be recorded only after the loan was approved."
CHOOSE_OUTCOME = "Choose Repaid on time, Repaid late or Defaulted."


class RepaymentError(ValueError):
    """The outcome could not be recorded (fixed text, safe to show)."""


def repayment_counts(apps: list) -> dict:
    """{status: n} over the approved applications in `apps` (lender_applications rows)."""
    out = {s: 0 for s in db.REPAYMENT_STATUSES}
    for a in apps:
        if a.get("repayment"):
            out[a["repayment"]["status"]] += 1
    return out


def record_repayment(conn, user, app_id, status: str, note: str | None = None, now=None) -> dict:
    """Record the final outcome of a loan THIS lender approved: repaid on time, repaid late or defaulted.

    Allowed only from "repaying" (no row yet, or a row still "repaying"), so a final outcome, defaulted included, can
    never change. Repaid on time or late: on or after the approval. Defaulted: only after the due date. One
    transaction: the row (inserted, or updated only WHERE status = 'repaying') and its audit row (actor, reference,
    old -> new status; never the note). Two lenders or tabs recording at once: the unique application_id makes the
    second one fail and it is refused. Any refusal raises (RepaymentError, or AccessDenied for the wrong role or
    organisation) and writes ONE generic audit line ("repayment_refused", the actor only). `now` (seconds since the
    epoch) controls the clock in tests; otherwise service.CLOCK."""
    try:
        auth.require_role(user, "lender")
        if status not in service.TERMINAL_STATUSES:
            raise RepaymentError(CHOOSE_OUTCOME)
        note = (note or "").strip() or None
        if note is not None and len(note) > db.REPAYMENT_NOTE_MAX:
            raise RepaymentError(f"Keep the note under {db.REPAYMENT_NOTE_MAX} characters.")
        a = lender_application(conn, user, app_id)              # AccessDenied: another organisation's application
        if a["status"] != "approved" or a["repayment"] is None:
            raise RepaymentError(NOT_APPROVED)
        current = a["repayment"]
        if current["terminal"]:
            raise RepaymentError(ALREADY_RECORDED)
        t = service.now_utc(now)
        decided = datetime.fromisoformat(a["decided_at"])
        if t < decided:
            raise RepaymentError(TOO_EARLY)
        due = date.fromisoformat(current["due_date"])
        if status == service.DEFAULTED and service.today(now) <= due:
            raise RepaymentError(TOO_EARLY_DEFAULT)
        r = repayments
        try:
            with db.transaction(conn):
                done = conn.execute(update(r).where(r.c.application_id == a["id"], r.c.status == service.REPAYING)
                                    .values(status=status, recorded_by=user["id"], recorded_at=t, note=note)
                                    .returning(r.c.id)).scalar_one_or_none()
                if done is None:
                    conn.execute(insert(r).values(application_id=a["id"], due_date=due, status=status,
                                                  recorded_by=user["id"], recorded_at=t, note=note, created_at=t))
                db.audit(conn, "repayment_recorded", actor_id=user["id"], target=a["ref"],
                         detail=f"{current['status']}->{status}", now=now)
        except IntegrityError:                                  # recorded by someone else a moment ago
            raise RepaymentError(ALREADY_RECORDED) from None
    except (RepaymentError, auth.AccessDenied):
        try:
            db.audit(conn, "repayment_refused", actor_id=(user or {}).get("id"), now=now)
        except service.DB_ERRORS:
            pass
        raise
    return lender_application(conn, user, a["id"])


# ------------------------------------------------------------------ admin: overview
TIER_ORDER = ("Low risk", "Moderate risk", "High risk", "Very high risk")
MODEL_NAMES = {"logistic": "Logistic regression", "random_forest": "Random forest", "xgboost": "XGBoost"}


def admin_overview(conn, user, now=None) -> dict:
    """Counts the app records (two queries): score checks run and uploads rejected in the last 7 days (audit rows, so
    checks with saving switched off count too), applications sent and decided (all time), and the share of saved checks
    per risk tier over the last 30 days (the stored tier of each check)."""
    auth.require_role(user, "admin")
    t = db.utcnow(now)

    def last_week(action):
        return (select(func.count()).select_from(audit_log)
                .where(audit_log.c.action == action, audit_log.c.ts >= t - timedelta(days=7)).scalar_subquery())
    sent = select(func.count()).select_from(applications).scalar_subquery()
    decided = (select(func.count()).select_from(applications)
               .where(applications.c.status.in_(("approved", "declined"))).scalar_subquery())
    counts = db.one(conn, select(last_week("score_check").label("scores_7d"), sent.label("applications"),
                                 decided.label("decided"), last_week("upload_rejected").label("rejected_7d")))
    tiers = db.all_rows(conn, select(score_checks.c.tier, func.count().label("n"))
                        .where(score_checks.c.created_at >= t - timedelta(days=30)).group_by(score_checks.c.tier))
    by_tier = {name: 0 for name in TIER_ORDER}
    for r in tiers:
        by_tier[r["tier"]] = by_tier.get(r["tier"], 0) + int(r["n"])
    a, r = applications, repayments
    outcome = func.coalesce(r.c.status, literal(service.REPAYING))
    by_outcome = db.all_rows(conn, select(outcome.label("status"), func.count().label("n"))
                             .select_from(a).outerjoin(r, r.c.application_id == a.c.id)
                             .where(a.c.status == "approved").group_by(outcome))
    outcomes = {s: 0 for s in db.REPAYMENT_STATUSES}
    for row in by_outcome:
        outcomes[row["status"]] = int(row["n"])
    stem = service.model_path().stem
    return {"scores_7d": int(counts["scores_7d"]), "applications": int(counts["applications"]),
            "outcomes": outcomes, "outcomes_recorded": sum(outcomes[s] for s in service.TERMINAL_STATUSES),
            "decided": int(counts["decided"]), "uploads_rejected": int(counts["rejected_7d"]), "tiers_30d": by_tier,
            "model": MODEL_NAMES.get(stem, stem.replace("_", " ").capitalize()), "model_stem": stem}


# ------------------------------------------------------------------ admin: outcomes export
EXPORT_COLUMNS = ("application_id", "score_check_id", "snapshot_score", "snapshot_pd", "risk_tier", "requested_amount",
                  "repay_within_days", "final_status", "recorded_date")


def export_outcomes(conn, user, now=None) -> tuple:
    """CSV of the loans with a FINAL recorded outcome (repaid on time, repaid late, defaulted), for future retraining:
    exactly EXPORT_COLUMNS. Never names, emails, notes, statements or file data. Writes an audit row (the admin, the
    row count). Returns (csv text, number of rows). Admins only."""
    auth.require_role(user, "admin")
    a, r = applications, repayments
    rows = db.all_rows(conn, select(a.c.id, a.c.check_id, a.c.snapshot_json, r.c.status, r.c.recorded_at)
                       .join_from(r, a, a.c.id == r.c.application_id)
                       .where(r.c.status.in_(service.TERMINAL_STATUSES)).order_by(a.c.id))
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(EXPORT_COLUMNS)
    for row in rows:
        snap = json.loads(row["snapshot_json"])
        w.writerow([row["id"], row["check_id"] if row["check_id"] is not None else "", int(snap["score"]),
                    f"{float(snap['pd']):.6f}", snap["tier"], f"{float(snap['request']['amount']):.2f}",
                    f"{float(snap['request']['term_days']):g}", row["status"],
                    row["recorded_at"].astimezone(service.NAIROBI).date().isoformat()])
    db.audit(conn, "outcomes_exported", actor_id=user["id"], detail=f"rows={len(rows)}", now=now)
    return buf.getvalue(), len(rows)


# ------------------------------------------------------------------ admin: users
def _status(row: dict, now) -> tuple:
    """("active" | "locked" | "disabled", minutes left of a lock)."""
    if not row["is_active"]:
        return "disabled", 0
    until = row["locked_until"]
    if until is not None and until > db.utcnow(now):
        return "locked", max(1, math.ceil((until - db.utcnow(now)).total_seconds() / 60))
    return "active", 0


def list_users(conn, user, now=None) -> list:
    """Every account: id, email, role, the organisation of a lender, status (ONE query). Never names or passwords."""
    auth.require_role(user, "admin")
    rows = db.all_rows(conn, select(users.c.id, users.c.email, users.c.role, users.c.org_name, users.c.is_active,
                                    users.c.locked_until)
                       .order_by(case((users.c.role == "admin", 0), (users.c.role == "lender", 1), else_=2), users.c.email))
    out = []
    for r in rows:
        status, minutes = _status(r, now)
        out.append({"id": r["id"], "email": r["email"], "role": r["role"],
                    "org_name": r["org_name"] if r["role"] == "lender" else None, "status": status, "minutes": minutes,
                    "is_self": r["id"] == user["id"]})
    return out


def generate_password() -> str:
    """A strong one-time password, as in scripts/create_demo_users.py (shown once, only its scrypt hash is stored)."""
    return secrets.token_urlsafe(PASSWORD_BYTES)


def create_staff_user(conn, user, email, role, org_name=None, now=None) -> tuple:
    """Add a lender or an admin. Returns (new user, one-time password). The password is returned to the caller to show
    ONCE; it is never stored in plain text, logged or put in the audit row. Vendors register themselves.
    One lender account per organisation (applications are addressed to the account)."""
    auth.require_role(user, "admin")
    if role not in STAFF_ROLES:
        raise service.UserError("Choose lender or admin. Vendors create their own accounts.")
    email = auth.normalise_email(email)
    org = service.normalise_org(org_name) or None
    if role == "lender":
        if org is None:
            raise service.UserError("Enter the lender's organisation.")
        if service.org_taken(conn, org):                        # the same rule as lender sign-up
            raise service.UserError(service.ORG_TAKEN)
        name = f"{org} credit desk"
    else:
        org, name = None, "Platform admin"
    password = generate_password()
    with db.transaction(conn):                                  # the account and its audit row, together
        uid = auth.create_user(conn, email, name, password, role, org_name=org, now=now)
        db.audit(conn, "user_created", actor_id=user["id"], target=f"user:{uid}", detail=role, now=now)
    return auth.get_user(conn, uid), password


def _target(conn, user_id) -> dict:
    row = db.one(conn, select(users.c.id).where(users.c.id == int(user_id)))
    if row is None:
        raise service.UserError("This account does not exist.")
    return row


def set_user_active(conn, user, user_id, active: bool, now=None) -> None:
    """Disable or enable an account (and its audit row). An admin cannot disable their own account."""
    auth.require_role(user, "admin")
    target = _target(conn, user_id)
    if target["id"] == user["id"] and not active:
        raise service.UserError("You cannot disable your own account.")
    with db.transaction(conn):
        conn.execute(update(users).where(users.c.id == target["id"]).values(is_active=bool(active)))
        db.audit(conn, "user_enabled" if active else "user_disabled", actor_id=user["id"], target=f"user:{target['id']}",
                 now=now)


def unlock_user(conn, user, user_id, now=None) -> None:
    """End a sign-in lock now (failed attempts back to 0), with its audit row."""
    auth.require_role(user, "admin")
    target = _target(conn, user_id)
    with db.transaction(conn):
        conn.execute(update(users).where(users.c.id == target["id"]).values(failed_attempts=0, locked_until=None))
        db.audit(conn, "user_unlocked", actor_id=user["id"], target=f"user:{target['id']}", now=now)


# ------------------------------------------------------------------ admin: audit log
REFUSALS = {"not_eligible": "not eligible", "no_income_data": "not enough income data",
            "above_limit": "above the estimated limit"}
UPLOAD_REASONS = {"file_type": "not an Excel, CSV or PDF file", "too_large": "larger than 10 MB", "empty": "empty file",
                  "pdf_no_text": "PDF without text", "pdf_password": "password-protected PDF",
                  "unreadable": "could not be read", "too_short": "too short"}


def describe(action: str, target: str | None, detail: str | None, target_email: str | None) -> str:
    """Plain language for one audit row, from the fixed event codes. Never amounts, file names or statement data."""
    who = target_email or "an account"
    ref = target if target and target.startswith("A-") else "an application"
    simple = {
        "register": "Created a vendor account",
        "lender_registered": "Created a lender account",
        "sign_in": "Signed in",
        "password_changed": "Changed their password",
        "delete_saved_results": "Deleted their saved score results",
        "application_sent": f"Sent application {ref}",
        "application_approved": f"Approved application {ref}",
        "application_declined": f"Declined application {ref}",
        "user_disabled": f"Disabled {who}",
        "user_enabled": f"Enabled {who}",
        "user_unlocked": f"Unlocked {who}",
        "repayment_refused": "Refused a repayment record",
    }
    if action in simple:
        return simple[action]
    if action == "sign_in_failed":
        return f"Failed sign-in ({auth.MAX_FAILED_ATTEMPTS}th), account locked" if detail == "locked" else "Failed sign-in"
    if action == "score_check":
        return "Ran a score check" + (" (not saved)" if target == "not_saved" else "")
    if action == "application_refused":
        return "Application not sent: " + REFUSALS.get(detail or "", "not eligible")
    if action == "repayment_recorded":
        old, _, new = (detail or "").partition("->")
        words = service.REPAYMENT_LABEL
        return f"Recorded repayment for {ref}: {words.get(old, 'Repaying')} to {words.get(new, 'a final status')}"
    if action == "outcomes_exported":
        n = (detail or "").removeprefix("rows=")
        return f"Exported repayment outcomes ({n} rows)" if n.isdigit() else "Exported repayment outcomes"
    if action == "upload_rejected":
        return "Upload rejected: " + UPLOAD_REASONS.get(detail or "", "could not be read")
    if action == "user_created":
        return f"Added {'an admin' if detail == 'admin' else 'a lender'} account, {who}"
    return "Other action"


def audit_page(conn, user, page: int = 0, per_page: int = AUDIT_PAGE_SIZE) -> dict:
    """One page of the audit log, newest first (ONE query: the actor's and an account target's email joined in).
    Returns {"rows": [{"id", "who", "what", "when"}], "page", "has_next"}."""
    auth.require_role(user, "admin")
    page = max(0, int(page))
    actor, tgt = aliased(users), aliased(users)
    on_target = and_(audit_log.c.target.is_not(None), audit_log.c.target == literal("user:") + cast(tgt.c.id, Text))
    stmt = (select(audit_log.c.id, audit_log.c.ts, audit_log.c.action, audit_log.c.target, audit_log.c.detail,
                   actor.c.email.label("actor_email"), tgt.c.email.label("target_email"))
            .outerjoin(actor, actor.c.id == audit_log.c.actor_id).outerjoin(tgt, on_target)
            .order_by(audit_log.c.ts.desc(), audit_log.c.id.desc()).limit(per_page + 1).offset(page * per_page))
    rows = db.all_rows(conn, stmt)
    out = [{"id": r["id"], "who": r["actor_email"] or "Unknown account", "when": db.iso(r["ts"]),
            "what": describe(r["action"], r["target"], r["detail"], r["target_email"])} for r in rows[:per_page]]
    return {"rows": out, "page": page, "has_next": len(rows) > per_page}
