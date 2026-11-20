"""Web app: database schema, password hashing, sign-in, lockout and the role guard (app/db.py, app/auth.py).

Every database test runs on SQLite; with DATABASE_URL pointing at PostgreSQL the same tests also run there
(marked `postgres`, each in its own temporary schema).
"""
import threading

import pytest
from sqlalchemy import inspect, insert, select
from sqlalchemy.exc import IntegrityError

import app_helpers as H
from app import auth, db, service
from app.db import users

PW = "correct-horse-1"


@pytest.fixture(params=H.BACKENDS)
def engine(request, tmp_path):
    with H.database(request.param, tmp_path) as e:
        yield e


@pytest.fixture
def conn(engine):
    c = db.connect(engine)
    yield c
    c.close()


@pytest.fixture
def vendor(conn):
    return service.register_vendor(conn, "Test Vendor", "Vendor@Example.com", PW, PW, now=1000.0)


def _user_row(conn, uid):
    return db.one(conn, select(users).where(users.c.id == uid))


def test_schema_is_created_with_the_agreed_columns_and_indexes(engine, conn):
    assert db.table_columns(engine, "users") == [
        "id", "email", "name", "org_name", "role", "password_hash", "salt", "failed_attempts", "locked_until", "is_active",
        "created_at", "share_with_lenders", "save_results", "email_notifications"]
    assert db.table_columns(engine, "score_checks") == [
        "id", "user_id", "created_at", "score", "pd", "tier", "pillars_json", "reasons_json", "data_notes_json",
        "request_amount", "request_term", "monthly_income", "affordability_band", "rows_read", "max_amount",
        "comfortable_amount"]
    assert db.table_columns(engine, "applications") == [
        "id", "ref", "vendor_id", "lender_id", "check_id", "snapshot_json", "status", "lender_note", "created_at", "decided_at"]
    assert db.table_columns(engine, "audit_log") == ["id", "ts", "actor_id", "action", "target", "detail"]
    ins = inspect(engine)
    idx = {(t, i["name"]): i for t in db.TABLES for i in ins.get_indexes(t)}
    assert idx[("users", "ix_users_email")]["unique"]
    for t, name in (("applications", "ix_applications_vendor_id"), ("applications", "ix_applications_lender_id"),
                    ("score_checks", "ix_score_checks_user_id"), ("audit_log", "ix_audit_log_ts")):
        assert (t, name) in idx, name
    db.create_schema(engine)                                           # idempotent
    assert db.table_columns(engine, "users")[0] == "id"


def test_sqlite_is_the_default_and_urls_are_normalised(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "x" / "app.db"))
    assert db.database_url() == "sqlite:///" + (tmp_path / "x" / "app.db").resolve().as_posix()
    for given in ("postgresql://u:p@host/db?sslmode=require", "postgres://u:p@host/db?sslmode=require",
                  "postgresql+psycopg://u:p@host/db?sslmode=require"):
        assert db.normalise_url(given) == "postgresql+psycopg://u:p@host/db?sslmode=require"
    monkeypatch.setenv("DATABASE_URL", "postgres://u:secret@host/db")
    assert db.database_url() == "postgresql+psycopg://u:secret@host/db" and db.backend_name(db.database_url()) == "postgresql"


def test_unreachable_database_never_shows_the_url():
    url = "postgresql+psycopg://someuser:s3cret-pass@127.0.0.1:1/nodb?connect_timeout=1"
    with pytest.raises(db.DatabaseUnavailable) as e:
        db.get_engine(url)
    msg = str(e.value) + repr(e.value)
    assert "s3cret" not in msg and "someuser" not in msg and "127.0.0.1" not in msg
    assert e.value.__cause__ is None and e.value.__suppress_context__
    assert url not in db._ENGINES                                       # a failed engine is not cached


def test_hash_and_verify():
    h1, s1 = auth.hash_password(PW)
    h2, s2 = auth.hash_password(PW)
    assert s1 != s2 and h1 != h2                                      # a random salt per hash
    assert PW not in h1 and len(bytes.fromhex(s1)) == 16
    assert auth.verify_password(PW, h1, s1)
    assert not auth.verify_password(PW + "x", h1, s1)


def test_password_is_never_stored_in_plain_text(conn, vendor):
    row = _user_row(conn, vendor["id"])
    assert PW not in " ".join(str(v) for v in row.values())
    assert row["email"] == "vendor@example.com"                       # stored lower-cased
    assert "password_hash" not in vendor and "salt" not in vendor     # get_user drops password fields
    assert vendor["is_active"] is True and vendor["save_results"] is True and vendor["email_notifications"] is False


def test_sign_in_and_wrong_password(conn, vendor):
    u = service.authenticate(conn, "  vendor@example.COM ", PW, now=2000.0)
    assert u["id"] == vendor["id"] and u["role"] == "vendor"
    with pytest.raises(auth.AuthError) as wrong:
        service.authenticate(conn, "vendor@example.com", "wrong-password", now=2001.0)
    with pytest.raises(auth.AuthError) as unknown:
        service.authenticate(conn, "nobody@example.com", PW, now=2002.0)
    assert str(wrong.value) == str(unknown.value) == auth.SIGN_IN_FAILED   # same message for both
    assert [r["action"] for r in H.rows(conn, "audit_log")] == ["register", "sign_in", "sign_in_failed", "sign_in_failed"]
    detail = " ".join(str(v) for r in H.rows(conn, "audit_log") for v in r.values())
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
    row = _user_row(conn, vendor["id"])
    assert row["failed_attempts"] == 0 and row["locked_until"] is None


def test_lock_time_is_stored_as_utc(conn, vendor):
    for i in range(5):
        with pytest.raises(auth.AuthError):
            auth.authenticate(conn, "vendor@example.com", "bad-password", now=50_000.0 + i)
    until = _user_row(conn, vendor["id"])["locked_until"]
    assert until == db.utcnow(50_004.0 + auth.LOCK_SECONDS) and until.utcoffset().total_seconds() == 0


def test_success_resets_the_failure_counter(conn, vendor):
    for i in range(4):
        with pytest.raises(auth.AuthError):
            auth.authenticate(conn, "vendor@example.com", "bad-password", now=100.0 + i)
    auth.authenticate(conn, "vendor@example.com", PW, now=105.0)
    for i in range(4):                                                    # 4 more failures do not lock
        with pytest.raises(auth.AuthError, match="incorrect"):
            auth.authenticate(conn, "vendor@example.com", "bad-password", now=106.0 + i)
    assert auth.authenticate(conn, "vendor@example.com", PW, now=111.0)["id"] == vendor["id"]


def test_concurrent_failed_sign_ins_are_all_counted(engine, conn, vendor):
    """Four wrong passwords at the same moment on four connections: the atomic UPDATE counts every one."""
    barrier, errors = threading.Barrier(4), []

    def attempt():
        c = db.connect(engine)
        try:
            barrier.wait()
            with pytest.raises(auth.AuthError):
                auth.authenticate(c, "vendor@example.com", "bad-password", now=7000.0)
        except Exception as e:      # noqa: BLE001
            errors.append(e)
        finally:
            c.close()
    threads = [threading.Thread(target=attempt) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert _user_row(conn, vendor["id"])["failed_attempts"] == 4
    with pytest.raises(auth.AuthError, match="Too many attempts"):
        auth.authenticate(conn, "vendor@example.com", "bad-password", now=7001.0)        # the 5th locks


def test_minimum_password_length_and_confirmation(conn):
    with pytest.raises(auth.AuthError, match="at least 10"):
        service.register_vendor(conn, "A Vendor", "a@example.com", "short-pw1", "short-pw1")      # 9 characters
    with pytest.raises(auth.AuthError, match="do not match"):
        service.register_vendor(conn, "A Vendor", "a@example.com", PW, PW + "x")
    assert service.register_vendor(conn, "A Vendor", "a@example.com", "0123456789", "0123456789")["role"] == "vendor"


def _raw_user(email):
    return insert(users).values(email=email, name="x", role="vendor", password_hash="h", salt="s",
                                created_at=db.utcnow())


def test_duplicate_email_is_refused(conn, vendor):
    with pytest.raises(auth.AuthError, match="already exists"):
        service.register_vendor(conn, "Other", "VENDOR@example.com", PW, PW)
    with pytest.raises(IntegrityError):                                # unique index in the schema
        with db.transaction(conn):
            conn.execute(_raw_user("vendor@example.com"))
    with pytest.raises(IntegrityError):                                # emails must be stored lower-cased
        with db.transaction(conn):
            conn.execute(_raw_user("Mixed@Example.com"))
    assert len(H.rows(conn, "users")) == 1


def test_role_guard(conn, vendor):
    lender = auth.get_user(conn, auth.create_user(conn, "l@example.com", "Lender", PW, "lender", org_name="Umoja SACCO"))
    assert auth.require_role(vendor, "vendor") is vendor
    with pytest.raises(auth.AccessDenied, match="vendors only"):
        auth.require_role(lender, "vendor")
    with pytest.raises(auth.AccessDenied):
        auth.require_role(None, "vendor")
    auth.set_active(conn, vendor["id"], False)
    with pytest.raises(auth.AccessDenied):
        auth.require_role(auth.get_user(conn, vendor["id"]), "vendor")
    with pytest.raises(auth.AuthError, match="incorrect"):                                # inactive cannot sign in
        auth.authenticate(conn, "vendor@example.com", PW)


def test_change_password(conn, vendor):
    with pytest.raises(auth.AuthError, match="current password"):
        service.change_password(conn, vendor, "nope-nope-nope", "new-password-1", "new-password-1")
    service.change_password(conn, vendor, PW, "new-password-1", "new-password-1")
    assert auth.authenticate(conn, "vendor@example.com", "new-password-1")["id"] == vendor["id"]


def test_demo_users_script(conn):
    import importlib.util
    spec = importlib.util.spec_from_file_location("create_demo_users", H.ROOT / "scripts" / "create_demo_users.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = mod.create_demo_users(conn, env={"DEMO_ADMIN_PASSWORD": "admin-password-from-env"})
    assert sorted(r for _, r, _, _ in rows) == ["admin", "lender", "lender", "vendor"]
    assert {l["org_name"] for l in service.list_lenders(conn)} == {"Umoja SACCO", "Tumaini Microfinance"}
    generated = [p for _, _, p, _ in rows if p]
    assert len(generated) == 3 and len(set(generated)) == 3 and all(len(p) >= 10 for p in generated)
    assert auth.authenticate(conn, "admin@demo.local", "admin-password-from-env")["role"] == "admin"
    again = mod.create_demo_users(conn, env={})
    assert all(what == "exists" for *_, what in again)                                  # idempotent
