"""SQLite storage for the web app.

The database lives at data/private/app.db (gitignored); set APP_DB_PATH to use another file (the tests do).
Only parameterised queries are used. No statement content is ever stored: a score check keeps the score, the
seven pillar ratings, the reason phrases, the request and derived monthly income, never rows, details or names
from the statement. The audit log holds actions and ids only.
"""
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "data" / "private" / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    email               TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    name                TEXT    NOT NULL,
    org_name            TEXT,
    role                TEXT    NOT NULL CHECK (role IN ('vendor', 'lender', 'admin')),
    password_hash       TEXT    NOT NULL,
    salt                TEXT    NOT NULL,
    failed_attempts     INTEGER NOT NULL DEFAULT 0,
    locked_until        REAL,
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT    NOT NULL,
    share_with_lenders  INTEGER NOT NULL DEFAULT 1,
    save_results        INTEGER NOT NULL DEFAULT 1,
    email_notifications INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS score_checks (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at         TEXT    NOT NULL,
    score              INTEGER NOT NULL,
    pd                 REAL    NOT NULL,
    tier               TEXT    NOT NULL,
    pillars_json       TEXT    NOT NULL,
    reasons_json       TEXT    NOT NULL,
    data_notes_json    TEXT    NOT NULL,
    request_amount     REAL    NOT NULL,
    request_term       REAL    NOT NULL,
    monthly_income     REAL,
    affordability_band TEXT    NOT NULL,
    rows_read          INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ref           TEXT    UNIQUE,
    vendor_id     INTEGER NOT NULL REFERENCES users(id),
    lender_id     INTEGER NOT NULL REFERENCES users(id),
    check_id      INTEGER REFERENCES score_checks(id) ON DELETE SET NULL,
    snapshot_json TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'declined')),
    lender_note   TEXT,
    created_at    TEXT    NOT NULL,
    decided_at    TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       TEXT    NOT NULL,
    actor_id INTEGER,
    action   TEXT    NOT NULL,
    target   TEXT,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS idx_checks_user ON score_checks(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_apps_vendor ON applications(vendor_id, created_at);
CREATE INDEX IF NOT EXISTS idx_apps_lender ON applications(lender_id, created_at);
"""


def db_path() -> Path:
    return Path(os.environ.get("APP_DB_PATH") or DEFAULT_PATH)


def connect(path=None) -> sqlite3.Connection:
    """Open the database (creating the folder and the tables if needed). One connection per script run."""
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def utcnow_iso(now: float | None = None) -> str:
    t = datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(now, timezone.utc)
    return t.isoformat(timespec="seconds")


def one(conn, sql: str, params=()) -> sqlite3.Row | None:
    return conn.execute(sql, params).fetchone()


def all_rows(conn, sql: str, params=()) -> list:
    return conn.execute(sql, params).fetchall()


def write(conn, sql: str, params=()) -> int:
    """Run one INSERT/UPDATE/DELETE in its own transaction; returns lastrowid for an insert, else rowcount."""
    with conn:
        cur = conn.execute(sql, params)
    return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount


def audit(conn, action: str, actor_id=None, target=None, detail=None, now: float | None = None) -> None:
    """Audit row: an action, who did it and an id. Never pass statement content, names or file names here."""
    write(conn, "INSERT INTO audit_log (ts, actor_id, action, target, detail) VALUES (?, ?, ?, ?, ?)",
          (utcnow_iso(now), actor_id, action, target, detail))


def table_columns(conn, table: str) -> list:
    if table not in ("users", "score_checks", "applications", "audit_log"):
        raise ValueError("unknown table")
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
