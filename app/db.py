"""Database layer of the web app: SQLAlchemy 2.x Core on SQLite (default) or PostgreSQL (e.g. Neon).

Which database: DATABASE_URL from the environment, else DATABASE_URL in st.secrets, else SQLite at
data/private/app.db (APP_DB_PATH overrides the file). postgresql:// and postgres:// URLs are rewritten to
postgresql+psycopg://. The URL holds credentials: it is never printed, logged or put in an error message (connection
errors are replaced by DatabaseUnavailable with a fixed message; engines use hide_parameters=True so SQL errors never
show the values either).

The schema is defined once below and created idempotently (create_all with checkfirst) on both databases. All
queries are SQLAlchemy Core constructs, so every value is a bound parameter. No statement content is ever stored: a
score check keeps the result only, and the audit log holds actions and ids.

Connections: one engine per URL per process (cached here; the app wraps it in st.cache_resource), pool_pre_ping and
pool_recycle=300. The app opens one connection per script run and closes it at the end. Writes go through
transaction(); a write of several rows is one transaction.
"""
import os
import sys
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, Float, ForeignKey, Index, Integer, MetaData, Table,
                        Text, create_engine, event, false, func, inspect, insert, select, true)
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.types import TypeDecorator

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "data" / "private" / "app.db"
CONNECT_TIMEOUT = 15        # seconds; a sleeping Neon database usually wakes within a few seconds


class DatabaseUnavailable(RuntimeError):
    """The database could not be reached. The message never contains the URL."""


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on both databases (SQLite stores them without an offset; they are read back as UTC)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: use timezone-aware UTC datetimes")
        value = value.astimezone(timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


# ------------------------------------------------------------------ schema (one definition for both databases)
metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("email", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("org_name", Text),
    Column("role", Text, nullable=False),
    Column("password_hash", Text, nullable=False),
    Column("salt", Text, nullable=False),
    Column("failed_attempts", Integer, nullable=False, server_default="0"),
    Column("locked_until", UTCDateTime()),
    Column("is_active", Boolean, nullable=False, server_default=true()),
    Column("created_at", UTCDateTime(), nullable=False),
    Column("share_with_lenders", Boolean, nullable=False, server_default=true()),
    Column("save_results", Boolean, nullable=False, server_default=true()),
    Column("email_notifications", Boolean, nullable=False, server_default=false()),
    CheckConstraint("role IN ('vendor', 'lender', 'admin')", name="ck_users_role"),
    CheckConstraint("email = lower(email)", name="ck_users_email_lower"),
)
Index("ix_users_email", users.c.email, unique=True)

score_checks = Table(
    "score_checks", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", UTCDateTime(), nullable=False),
    Column("score", Integer, nullable=False),
    Column("pd", Float, nullable=False),
    Column("tier", Text, nullable=False),
    Column("pillars_json", Text, nullable=False),
    Column("reasons_json", Text, nullable=False),
    Column("data_notes_json", Text, nullable=False),
    Column("request_amount", Float, nullable=False),
    Column("request_term", Float, nullable=False),
    Column("monthly_income", Float),
    Column("affordability_band", Text, nullable=False),
    Column("rows_read", Integer, nullable=False),
)
Index("ix_score_checks_user_id", score_checks.c.user_id)

applications = Table(
    "applications", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ref", Text, unique=True),
    Column("vendor_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("lender_id", Integer, ForeignKey("users.id"), nullable=False),
    Column("check_id", Integer, ForeignKey("score_checks.id", ondelete="SET NULL")),
    Column("snapshot_json", Text, nullable=False),
    Column("status", Text, nullable=False, server_default="pending"),
    Column("lender_note", Text),
    Column("created_at", UTCDateTime(), nullable=False),
    Column("decided_at", UTCDateTime()),
    CheckConstraint("status IN ('pending', 'approved', 'declined')", name="ck_applications_status"),
)
Index("ix_applications_vendor_id", applications.c.vendor_id)
Index("ix_applications_lender_id", applications.c.lender_id)

audit_log = Table(
    "audit_log", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", UTCDateTime(), nullable=False),
    Column("actor_id", Integer),
    Column("action", Text, nullable=False),
    Column("target", Text),
    Column("detail", Text),
)
Index("ix_audit_log_ts", audit_log.c.ts)

TABLES = {t.name: t for t in (users, score_checks, applications, audit_log)}


# ------------------------------------------------------------------ settings
def db_path() -> Path:
    return Path(os.environ.get("APP_DB_PATH") or DEFAULT_PATH)


def normalise_url(url: str) -> str:
    """postgres:// and postgresql:// become postgresql+psycopg:// (the driver this app installs)."""
    url = url.strip()
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _secret_url():
    if "streamlit" not in sys.modules:                 # scripts and tests: environment only
        return None
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL")
    except Exception:                                    # noqa: BLE001 - no secrets file, or not running in Streamlit
        return None


def database_url() -> str:
    """DATABASE_URL (environment, then st.secrets), else the SQLite file. Never print the result."""
    url = os.environ.get("DATABASE_URL") or _secret_url()
    if url:
        return normalise_url(str(url))
    return "sqlite:///" + db_path().resolve().as_posix()


def backend_name(url_or_engine) -> str:
    """'sqlite' or 'postgresql', safe to show (no host, user or password)."""
    name = url_or_engine.dialect.name if isinstance(url_or_engine, Engine) else str(url_or_engine).split(":", 1)[0]
    return "sqlite" if name.startswith("sqlite") else "postgresql" if name.startswith("postgres") else "other"


# ------------------------------------------------------------------ engines and connections
def _sqlite_foreign_keys(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON")
    cur.close()


def make_engine(url: str, search_path: str | None = None) -> Engine:
    """A new engine. search_path (PostgreSQL only) puts the tables in that schema; the tests use it for isolation."""
    url = normalise_url(url)
    kw = {"pool_pre_ping": True, "pool_recycle": 300, "hide_parameters": True, "future": True}
    if backend_name(url) == "sqlite":
        path = url.split("sqlite:///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        kw["connect_args"] = {"timeout": 30, "check_same_thread": False}
    else:
        # never wait forever for a host that does not answer (a URL's own connect_timeout takes precedence)
        kw["connect_args"] = {} if "connect_timeout=" in url else {"connect_timeout": CONNECT_TIMEOUT}
        if search_path:
            kw["connect_args"]["options"] = f"-csearch_path={search_path}"
    engine = create_engine(url, **kw)
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _sqlite_foreign_keys)
    return engine


def create_schema(engine: Engine) -> None:
    """Create the tables and indexes that do not exist yet (idempotent)."""
    metadata.create_all(engine, checkfirst=True)


_ENGINES: dict = {}
_LOCK = threading.Lock()


def get_engine(url: str | None = None) -> Engine:
    """The cached engine for a URL (default: database_url()), with the schema created on first use."""
    url = normalise_url(url) if url else database_url()
    with _LOCK:
        engine = _ENGINES.get(url)
        if engine is None:
            engine = make_engine(url)
            _with_retry(lambda: create_schema(engine))
            _ENGINES[url] = engine
    return engine


def _with_retry(fn):
    """Run fn; retry once on OperationalError (Neon sleeps when idle, so the first try can fail).
    A second failure becomes DatabaseUnavailable, whose message never holds the URL."""
    try:
        return fn()
    except OperationalError:
        try:
            return fn()
        except OperationalError:
            raise DatabaseUnavailable("The database is not reachable right now. Try again in a minute.") from None


def connect(engine: Engine | None = None) -> Connection:
    """Open a connection (retry once on OperationalError). Close it when done; the app does so after every run."""
    engine = engine or get_engine()

    def _open():
        conn = engine.connect()
        try:
            conn.exec_driver_sql("SELECT 1")
            conn.rollback()
        except Exception:
            conn.close()
            raise
        return conn
    return _with_retry(_open)


@contextmanager
def transaction(conn: Connection):
    """One transaction for everything inside the block; nested blocks join the outer one.
    Commits on success and rolls back on any error."""
    depth = conn.info.get("tx_depth", 0)
    if depth:
        conn.info["tx_depth"] = depth + 1
        try:
            yield conn
        finally:
            conn.info["tx_depth"] = depth
        return
    if conn.in_transaction():          # a read started an implicit transaction: end it (it holds no writes)
        conn.rollback()
    conn.info["tx_depth"] = 1
    try:
        with conn.begin():
            yield conn
    finally:
        conn.info["tx_depth"] = 0


def end_read(conn: Connection) -> None:
    """End the implicit transaction a read opened, so no snapshot or lock is held between operations."""
    if conn.in_transaction() and not conn.info.get("tx_depth"):
        conn.rollback()


# ------------------------------------------------------------------ helpers
def utcnow(now: float | None = None) -> datetime:
    """Current UTC time (aware), or `now` seconds since the epoch (the tests control the clock)."""
    return datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(now, timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def one(conn: Connection, stmt) -> dict | None:
    row = conn.execute(stmt).mappings().first()
    end_read(conn)
    return dict(row) if row is not None else None


def all_rows(conn: Connection, stmt) -> list:
    rows = [dict(r) for r in conn.execute(stmt).mappings().all()]
    end_read(conn)
    return rows


def audit(conn: Connection, action: str, actor_id=None, target=None, detail=None, now: float | None = None) -> None:
    """Audit row: an action, who did it and an id. Never pass statement content, names, emails or file names here."""
    with transaction(conn):
        conn.execute(insert(audit_log).values(ts=utcnow(now), actor_id=actor_id, action=action, target=target,
                                              detail=detail))


def table_columns(conn_or_engine, table: str) -> list:
    if table not in TABLES:
        raise ValueError("unknown table")
    return [c["name"] for c in inspect(conn_or_engine).get_columns(table)]


def count(conn: Connection, table: str, **where) -> int:
    """Number of rows in a table, optionally filtered by column equality (tests and checks)."""
    t = TABLES[table]
    stmt = select(func.count()).select_from(t)
    for k, v in where.items():
        stmt = stmt.where(t.c[k] == v)
    n = conn.execute(stmt).scalar_one()
    end_read(conn)
    return int(n)
