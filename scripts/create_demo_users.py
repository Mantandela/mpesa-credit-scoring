"""Create the demo accounts: 1 vendor, 2 lenders (Umoja SACCO, Tumaini Microfinance) and 1 admin.

Passwords come from environment variables, or are generated at random and printed ONCE (store them yourself; they
are not saved in plain text anywhere). No password is hard-coded. Existing accounts are left unchanged.

    DEMO_VENDOR_PASSWORD, DEMO_UMOJA_PASSWORD, DEMO_TUMAINI_PASSWORD, DEMO_ADMIN_PASSWORD   (optional, >= 10 characters)
    DATABASE_URL     (optional: PostgreSQL, e.g. Neon; never printed)
    APP_DB_PATH      (optional: the SQLite file when DATABASE_URL is not set; default data/private/app.db)

Run from the repo root:  python scripts/create_demo_users.py
"""
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import auth, db  # noqa: E402

DEMO_USERS = (
    # email, name, role, organisation, password env var
    ("vendor@demo.local", "Demo Vendor", "vendor", None, "DEMO_VENDOR_PASSWORD"),
    ("umoja@demo.local", "Umoja SACCO credit desk", "lender", "Umoja SACCO", "DEMO_UMOJA_PASSWORD"),
    ("tumaini@demo.local", "Tumaini Microfinance credit desk", "lender", "Tumaini Microfinance", "DEMO_TUMAINI_PASSWORD"),
    ("admin@demo.local", "Platform admin", "admin", None, "DEMO_ADMIN_PASSWORD"),
)


def create_demo_users(conn, env=None) -> list:
    """Create the missing demo users. Returns [(email, role, password or None if it came from env/existed)]."""
    env = os.environ if env is None else env
    out = []
    for email, name, role, org, var in DEMO_USERS:
        if auth.find_user_id(conn, email) is not None:
            out.append((email, role, None, "exists"))
            continue
        given = env.get(var)
        password = given or secrets.token_urlsafe(12)
        try:
            auth.create_user(conn, email, name, password, role, org_name=org)
        except auth.AuthError:                 # created at the same moment by another run
            out.append((email, role, None, "exists"))
            continue
        out.append((email, role, None if given else password, "created"))
    return out


def main():
    url = db.database_url()
    engine = db.get_engine(url)
    conn = db.connect(engine)
    try:
        rows = create_demo_users(conn)
    finally:
        conn.close()
        engine.dispose()
    where = db.db_path().as_posix() if db.backend_name(url) == "sqlite" else "PostgreSQL from DATABASE_URL (not shown)"
    print(f"database: {where}")
    for email, role, password, what in rows:
        shown = password if password else ("(from environment)" if what == "created" else "(unchanged)")
        print(f"{what:8} {role:7} {email:24} {shown}")
    if any(p for _, _, p, _ in rows):
        print("Generated passwords are shown only now. Store them safely.")


if __name__ == "__main__":
    main()
