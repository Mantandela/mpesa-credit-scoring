"""Web app: database schema, password hashing, sign-in, lockout and the role guard (app/db.py, app/auth.py)."""
import sqlite3

import pytest

import app_helpers  # noqa: F401  (puts the repo root on sys.path)
from app import auth, db, service

PW = "correct-horse-1"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "private" / "app.db")
    yield c
    c.close()


@pytest.fixture
def vendor(conn):
    return service.register_vendor(conn, "Test Vendor", "Vendor@Example.com", PW, PW, now=1000.0)


def test_schema_is_created_with_the_agreed_columns(tmp_path, conn):
    assert (tmp_path / "private" / "app.db").exists()                 # folder created when missing
    assert db.table_columns(conn, "users") == [
        "id", "email", "name", "org_name", "role", "password_hash", "salt", "failed_attempts", "locked_until", "is_active",
        "created_at", "share_with_lenders", "save_results", "email_notifications"]
    assert db.table_columns(conn, "score_checks") == [
        "id", "user_id", "created_at", "score", "pd", "tier", "pillars_json", "reasons_json", "data_notes_json",
        "request_amount", "request_term", "monthly_income", "affordability_band", "rows_read"]
    assert db.table_columns(conn, "applications") == [
        "id", "ref", "vendor_id", "lender_id", "check_id", "snapshot_json", "status", "lender_note", "created_at", "decided_at"]
    assert db.table_columns(conn, "audit_log") == ["id", "ts", "actor_id", "action", "target", "detail"]
    db.connect(tmp_path / "private" / "app.db").close()               # opening again is harmless


def test_hash_and_verify():
    h1, s1 = auth.hash_password(PW)
    h2, s2 = auth.hash_password(PW)
    assert s1 != s2 and h1 != h2                                      # a random salt per hash
    assert PW not in h1 and len(bytes.fromhex(s1)) == 16
    assert auth.verify_password(PW, h1, s1)
    assert not auth.verify_password(PW + "x", h1, s1)


def test_password_is_never_stored_in_plain_text(conn, vendor):
    row = conn.execute("SELECT * FROM users WHERE id = ?", (vendor["id"],)).fetchone()
    assert PW not in " ".join(str(v) for v in tuple(row))
    assert "password_hash" not in vendor and "salt" not in vendor     # get_user drops password fields


def test_sign_in_and_wrong_password(conn, vendor):
    u = service.authenticate(conn, "  vendor@example.COM ", PW, now=2000.0)
    assert u["id"] == vendor["id"] and u["role"] == "vendor"
    with pytest.raises(auth.AuthError) as wrong:
        service.authenticate(conn, "vendor@example.com", "wrong-password", now=2001.0)
    with pytest.raises(auth.AuthError) as unknown:
        service.authenticate(conn, "nobody@example.com", PW, now=2002.0)
    assert str(wrong.value) == str(unknown.value) == auth.SIGN_IN_FAILED   # same message for both
    actions = [r["action"] for r in conn.execute("SELECT action FROM audit_log ORDER BY id")]
    assert actions == ["register", "sign_in", "sign_in_failed", "sign_in_failed"]
    detail = " ".join(str(v) for r in conn.execute("SELECT * FROM audit_log") for v in tuple(r))
    assert "wrong-password" not in detail and "nobody@example.com" not in detail and PW not in detail


def test_lockout_after_five_failures_and_unlock_after_ten_minutes(conn, vendor):
    t0 = 10_000.0
    for i in range(4):
        with pytest.raises(auth.AuthError, match="incorrect"):
            auth.authenticate(conn, "vendor@example.com", "bad-password", now=t0 + i)
    with pytest.raises(auth.AuthError, match="Too many attempts"):
        auth.authenticate(conn, "vendor@example.com", "bad-password", now=t0 + 4)        # 5th failure locks
    with pytest.raises(auth.AuthError, match="Too many attempts"):
        auth.authenticate(conn, "vendor@example.com", PW, now=t0 + 4 + 599)              # even the right password
    u = auth.authenticate(conn, "vendor@example.com", PW, now=t0 + 4 + 601)              # 10 minutes later
    assert u["id"] == vendor["id"]
    row = conn.execute("SELECT failed_attempts, locked_until FROM users WHERE id = ?", (vendor["id"],)).fetchone()
    assert row["failed_attempts"] == 0 and row["locked_until"] is None


def test_success_resets_the_failure_counter(conn, vendor):
    for i in range(4):
        with pytest.raises(auth.AuthError):
            auth.authenticate(conn, "vendor@example.com", "bad-password", now=100.0 + i)
    auth.authenticate(conn, "vendor@example.com", PW, now=105.0)
    for i in range(4):                                                    # 4 more failures do not lock
        with pytest.raises(auth.AuthError, match="incorrect"):
            auth.authenticate(conn, "vendor@example.com", "bad-password", now=106.0 + i)
    assert auth.authenticate(conn, "vendor@example.com", PW, now=111.0)["id"] == vendor["id"]


def test_minimum_password_length_and_confirmation(conn):
    with pytest.raises(auth.AuthError, match="at least 10"):
        service.register_vendor(conn, "A Vendor", "a@example.com", "short-pw1", "short-pw1")      # 9 characters
    with pytest.raises(auth.AuthError, match="do not match"):
        service.register_vendor(conn, "A Vendor", "a@example.com", PW, PW + "x")
    assert service.register_vendor(conn, "A Vendor", "a@example.com", "0123456789", "0123456789")["role"] == "vendor"


def test_duplicate_email_is_refused(conn, vendor):
    with pytest.raises(auth.AuthError, match="already exists"):
        service.register_vendor(conn, "Other", "VENDOR@example.com", PW, PW)
    with pytest.raises(sqlite3.IntegrityError):                                          # also enforced by the schema
        db.write(conn, "INSERT INTO users (email, name, role, password_hash, salt, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 ("vendor@EXAMPLE.com", "x", "vendor", "h", "s", "now"))


def test_role_guard(conn, vendor):
    lender = auth.get_user(conn, auth.create_user(conn, "l@example.com", "Lender", PW, "lender", org_name="Umoja SACCO"))
    assert auth.require_role(vendor, "vendor") is vendor
    with pytest.raises(auth.AccessDenied, match="vendors only"):
        auth.require_role(lender, "vendor")
    with pytest.raises(auth.AccessDenied):
        auth.require_role(None, "vendor")
    db.write(conn, "UPDATE users SET is_active = 0 WHERE id = ?", (vendor["id"],))
    with pytest.raises(auth.AccessDenied):
        auth.require_role(auth.get_user(conn, vendor["id"]), "vendor")
    with pytest.raises(auth.AuthError, match="incorrect"):                                # inactive cannot sign in
        auth.authenticate(conn, "vendor@example.com", PW)


def test_change_password(conn, vendor):
    with pytest.raises(auth.AuthError, match="current password"):
        service.change_password(conn, vendor, "nope-nope-nope", "new-password-1", "new-password-1")
    service.change_password(conn, vendor, PW, "new-password-1", "new-password-1")
    assert auth.authenticate(conn, "vendor@example.com", "new-password-1")["id"] == vendor["id"]


def test_demo_users_script(conn, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("create_demo_users", app_helpers.ROOT / "scripts" / "create_demo_users.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.create_demo_users(conn, env={"DEMO_ADMIN_PASSWORD": "admin-password-from-env"})
    roles = sorted(r for _, r, _, _ in rows)
    assert roles == ["admin", "lender", "lender", "vendor"]
    assert {l["org_name"] for l in service.list_lenders(conn)} == {"Umoja SACCO", "Tumaini Microfinance"}
    generated = [p for _, _, p, _ in rows if p]
    assert len(generated) == 3 and len(set(generated)) == 3 and all(len(p) >= 10 for p in generated)
    assert auth.authenticate(conn, "admin@demo.local", "admin-password-from-env")["role"] == "admin"
    again = mod.create_demo_users(conn, env={})
    assert all(what == "exists" for *_, what in again)                                  # idempotent
