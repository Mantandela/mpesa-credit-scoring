"""Passwords, sign-in with lockout, and the role guard used by every page.

Passwords are hashed with hashlib.scrypt (n=2**14, r=8, p=1) and a random 16-byte salt per user, and compared with
hmac.compare_digest. After 5 failed sign-ins in a row an account is locked for 10 minutes; a successful sign-in
resets the counter. Unknown email and wrong password give the same message. `now` (seconds since the epoch) can be
passed in so the tests control the clock.
"""
import hashlib
import hmac
import re
import secrets
import time

from app import db

MIN_PASSWORD_LENGTH = 10
MAX_FAILED_ATTEMPTS = 5
LOCK_SECONDS = 10 * 60
ROLES = ("vendor", "lender", "admin")
_SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32, "maxmem": 64 * 1024 * 1024}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

SIGN_IN_FAILED = "Email or password is incorrect."
ACCOUNT_LOCKED = "Too many attempts. Try again in 10 minutes."


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


def create_user(conn, email, name, password, role, org_name=None, now=None) -> int:
    """Insert a user. Vendors come through service.register_vendor; lenders and admins only through scripts."""
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    email = normalise_email(email)
    name = (name or "").strip()
    if not name:
        raise AuthError("Enter your full name.")
    check_new_password(password)
    if db.one(conn, "SELECT 1 FROM users WHERE email = ?", (email,)):
        raise AuthError("An account with this email already exists.")
    h, salt = hash_password(password)
    return db.write(conn, "INSERT INTO users (email, name, org_name, role, password_hash, salt, created_at) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?)", (email, name, org_name, role, h, salt, db.utcnow_iso(now)))


def authenticate(conn, email: str, password: str, now: float | None = None) -> dict:
    """Return the user as a dict, or raise AuthError (same message for unknown email and wrong password)."""
    now = time.time() if now is None else now
    try:
        email = normalise_email(email)
    except AuthError:
        raise AuthError(SIGN_IN_FAILED) from None
    row = db.one(conn, "SELECT * FROM users WHERE email = ?", (email,))
    if row is None or not row["is_active"]:
        verify_password(password or "", *_DUMMY)
        raise AuthError(SIGN_IN_FAILED)
    if row["locked_until"] is not None and now < row["locked_until"]:
        raise AuthError(ACCOUNT_LOCKED)
    if not verify_password(password or "", row["password_hash"], row["salt"]):
        failures = row["failed_attempts"] + 1
        if failures >= MAX_FAILED_ATTEMPTS:
            db.write(conn, "UPDATE users SET failed_attempts = 0, locked_until = ? WHERE id = ?", (now + LOCK_SECONDS, row["id"]))
            raise AuthError(ACCOUNT_LOCKED)
        db.write(conn, "UPDATE users SET failed_attempts = ? WHERE id = ?", (failures, row["id"]))
        raise AuthError(SIGN_IN_FAILED)
    db.write(conn, "UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (row["id"],))
    return get_user(conn, row["id"])


def change_password(conn, user_id: int, current: str, new: str, confirm: str) -> None:
    row = db.one(conn, "SELECT password_hash, salt FROM users WHERE id = ?", (user_id,))
    if row is None or not verify_password(current or "", row["password_hash"], row["salt"]):
        raise AuthError("The current password is incorrect.")
    check_new_password(new, confirm)
    h, salt = hash_password(new)
    db.write(conn, "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (h, salt, user_id))


PUBLIC_COLUMNS = ("id", "email", "name", "org_name", "role", "is_active", "created_at", "share_with_lenders",
                  "save_results", "email_notifications")


def get_user(conn, user_id) -> dict | None:
    """The user without password fields, or None."""
    if user_id is None:
        return None
    row = db.one(conn, f"SELECT {', '.join(PUBLIC_COLUMNS)} FROM users WHERE id = ?", (int(user_id),))
    return dict(row) if row else None


def has_role(user: dict | None, *roles: str) -> bool:
    return bool(user) and bool(user.get("is_active")) and user.get("role") in roles


def require_role(user: dict | None, *roles: str) -> dict:
    """Role guard: return the user, or raise AccessDenied."""
    if not user:
        raise AccessDenied("Sign in first.")
    if not has_role(user, *roles):
        raise AccessDenied(f"This page is for {' and '.join(r + 's' for r in roles)} only.")
    return user
