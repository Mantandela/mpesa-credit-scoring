"""Passwords, sign-in with lockout, and the role guard used by every page.

Passwords are hashed with hashlib.scrypt (n=2**14, r=8, p=1) and a random 16-byte salt per user, and compared with
hmac.compare_digest. After 5 failed sign-ins in a row an account is locked for 10 minutes; a successful sign-in
resets the counter. The failure counter and the lock are updated by ONE atomic UPDATE statement, so concurrent
attempts cannot lose a count. Unknown email and wrong password give the same message. Emails are stored and compared
lower-cased. `now` (seconds since the epoch) can be passed in so the tests control the clock.
"""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from sqlalchemy import case, insert, literal, select, update
from sqlalchemy.exc import IntegrityError

from app import db
from app.db import users

MIN_PASSWORD_LENGTH = 10
MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 10 * 60
ROLES = ("vendor", "lender", "admin")
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32, "maxmem": 64 * 1024 * 1024}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SIGN_IN_FAILED = "Email or password is incorrect."
ACCOUNT_LOCKED = "Too many attempts. Try again in 10 minutes."
EMAIL_TAKEN = "An account with this email already exists."


class AuthError(ValueError):
    """Sign-in or registration problem; the message is safe to show."""


class AccessDenied(PermissionError):
    """The signed-in user may not open this page."""


def hash_password(password: str, salt_hex: str | None = None) -> tuple:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **_SCRYPT)
    return digest.hex(), salt.hex()


def verify_password(password: str, hash_hex: str, salt_hex: str) -> bool:
    candidate, _ = hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, hash_hex)


_DUMMY = hash_password("not-a-real-password-0000")        # equal work for unknown emails


def check_new_password(password: str, confirm: str | None = None) -> None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Use at least {MIN_PASSWORD_LENGTH} characters for the password.")
    if confirm is not None and password != confirm:
        raise AuthError("The passwords do not match.")


def normalise_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not _EMAIL.match(e):
        raise AuthError("Enter a valid email address.")
    return e


def find_user_id(conn, email: str) -> int | None:
    try:
        e = normalise_email(email)
    except AuthError:
        return None
    row = db.one(conn, select(users.c.id).where(users.c.email == e))
    return row["id"] if row else None


def create_user(conn, email, name, password, role, org_name=None, now=None) -> int:
    """Insert a user. Vendors come through service.register_vendor; lenders and admins only through scripts."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    email = normalise_email(email)
    name = (name or "").strip()
    if not name:
        raise AuthError("Enter your full name.")
    check_new_password(password)
    if find_user_id(conn, email) is not None:
        raise AuthError(EMAIL_TAKEN)
    h, salt = hash_password(password)
    try:
        with db.transaction(conn):
            res = conn.execute(insert(users).values(email=email, name=name, org_name=org_name, role=role,
                                                    password_hash=h, salt=salt, created_at=db.utcnow(now)))
    except IntegrityError:                     # two sign-ups with one email at the same moment
        raise AuthError(EMAIL_TAKEN) from None
    return int(res.inserted_primary_key[0])


def _record_failure(conn, user_id: int, now) -> bool:
    """Count one failed attempt and lock at the 5th, in one atomic UPDATE. Returns True if the account is now locked."""
    nxt = users.c.failed_attempts + 1
    until = literal(db.utcnow(now) + timedelta(seconds=LOCK_SECONDS), users.c.locked_until.type)
    stmt = (update(users).where(users.c.id == user_id)
            .values(failed_attempts=case((nxt >= MAX_FAILED_ATTEMPTS, 0), else_=nxt),
                    locked_until=case((nxt >= MAX_FAILED_ATTEMPTS, until), else_=users.c.locked_until))
            .returning(users.c.locked_until))
    with db.transaction(conn):
        locked_until = conn.execute(stmt).scalar_one()
    return locked_until is not None and locked_until > db.utcnow(now)


def authenticate(conn, email: str, password: str, now: float | None = None) -> dict:
    """Return the user as a dict, or raise AuthError (same message for unknown email and wrong password)."""
    try:
        email = normalise_email(email)
    except AuthError:
        raise AuthError(SIGN_IN_FAILED) from None
    row = db.one(conn, select(users).where(users.c.email == email))
    if row is None or not row["is_active"]:
        verify_password(password or "", *_DUMMY)
        raise AuthError(SIGN_IN_FAILED)
    if row["locked_until"] is not None and db.utcnow(now) < row["locked_until"]:
        raise AuthError(ACCOUNT_LOCKED)
    if not verify_password(password or "", row["password_hash"], row["salt"]):
        raise AuthError(ACCOUNT_LOCKED if _record_failure(conn, row["id"], now) else SIGN_IN_FAILED)
    with db.transaction(conn):
        conn.execute(update(users).where(users.c.id == row["id"]).values(failed_attempts=0, locked_until=None))
    return get_user(conn, row["id"])


def change_password(conn, user_id: int, current: str, new: str, confirm: str) -> None:
    row = db.one(conn, select(users.c.password_hash, users.c.salt).where(users.c.id == user_id))
    if row is None or not verify_password(current or "", row["password_hash"], row["salt"]):
        raise AuthError("The current password is incorrect.")
    check_new_password(new, confirm)
    h, salt = hash_password(new)
    with db.transaction(conn):
        conn.execute(update(users).where(users.c.id == user_id).values(password_hash=h, salt=salt))


PUBLIC_COLUMNS = ("id", "email", "name", "org_name", "role", "is_active", "created_at", "share_with_lenders",
                  "save_results", "email_notifications")


def get_user(conn, user_id) -> dict | None:
    """The user without password fields (created_at as an ISO string), or None."""
    if user_id is None:
        return None
    row = db.one(conn, select(*(users.c[c] for c in PUBLIC_COLUMNS)).where(users.c.id == int(user_id)))
    if row is None:
        return None
    row["created_at"] = db.iso(row["created_at"])
    for flag in ("is_active", "share_with_lenders", "save_results", "email_notifications"):
        row[flag] = bool(row[flag])
    return row


def set_active(conn, user_id: int, active: bool) -> None:
    with db.transaction(conn):
        conn.execute(update(users).where(users.c.id == user_id).values(is_active=bool(active)))


def has_role(user: dict | None, *roles: str) -> bool:
    return bool(user) and bool(user.get("is_active")) and user.get("role") in roles


def require_role(user: dict | None, *roles: str) -> dict:
    """Role guard: return the user, or raise AccessDenied."""
    if not user:
        raise AccessDenied("Sign in first.")
    if not has_role(user, *roles):
        raise AccessDenied(f"This page is for {' and '.join(r + 's' for r in roles)} only.")
    return user
