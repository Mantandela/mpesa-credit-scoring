"""Shared setup for the web app tests (tests/test_app_*.py). No real data and no trained artifacts are needed.

build_app_models() trains the same tiny toy logistic model as tests/test_predict.py and writes reference.json with
the REAL affordability cutoffs of the trained model (50th / 85th percentile 0.0564 / 0.4194), so band tests use the
numbers the app shows. statement_csv() writes a synthetic statement with made-up names and phone numbers in the
details, to check that none of it reaches the database, the audit log or the result.
"""
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

import joblib
import pytest
from sqlalchemy import select
from sqlalchemy.schema import CreateSchema, DropSchema

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_reference as BR  # noqa: E402
import clean  # noqa: E402
import features as Fe  # noqa: E402
import toy  # noqa: E402
from train_models import make_model  # noqa: E402

REAL_P50, REAL_P85 = 0.056367105686659244, 0.41940241208515233
NAMES = ("JANE WANJIKU", "PETER OTIENO", "MARY AKINYI", "JOHN KAMAU", "GRACE MUTUA", "DAVID OCHIENG")
PHONES = ("254712345678", "0722987654", "254733111222", "0711222333", "254700999888", "0799123456")


def build_app_models(d: Path) -> dict:
    from test_predict import _toy_table          # the toy training table of test_predict.py
    d = Path(d)
    feat = _toy_table()
    F = list(Fe.build_row(clean.clean(toy.make_vendor(), as_of="2026-12-31"), toy.make_apps().iloc[0]).keys())
    model = make_model("logistic", C=1.0).fit(feat[F], feat.defaulted)
    joblib.dump({"model": model, "features": F, "settings": {"C": 1.0}, "seed": 42}, d / "logistic.joblib")
    ref, bg = BR.build(feat, F, split_seed=42)
    ref["affordability_bands"] = dict(ref["affordability_bands"], p50=REAL_P50, p85=REAL_P85)
    BR.write(ref, bg, d)
    return {"model": d / "logistic.joblib", "ref": d / "reference.json", "reference": ref}


def statement_frame(vendor=None):
    """A toy statement in the M-Pesa sheet layout, newest first, with names and phone numbers in the details."""
    raw = toy.make_vendor() if vendor is None else vendor
    sheet = raw.sort_values("completion_time", ascending=False).copy()
    pay = sheet.details.str.startswith("Merchant Payment from")
    k = sheet.loc[pay, "counterparty_id"].str[-1].astype(int) % len(NAMES)
    sheet.loc[pay, "details"] = [f"Merchant Payment from {PHONES[i]} - {NAMES[i]}" for i in k]
    sheet = sheet.rename(columns={"receipt_no": "Receipt No.", "completion_time": "Completion Time", "details": "Details",
                                  "transaction_status": "Transaction Status", "paid_in": "Paid In",
                                  "withdrawn": "Withdrawn", "balance": "Balance"})
    return sheet[["Receipt No.", "Completion Time", "Details", "Transaction Status", "Paid In", "Withdrawn", "Balance"]]


def statement_csv(vendor=None) -> bytes:
    return statement_frame(vendor).to_csv(index=False).encode("utf-8")


class Upload:
    """Stands in for a Streamlit UploadedFile (name, size, getvalue)."""

    def __init__(self, data: bytes, name: str):
        self._data, self.name, self.size = data, name, len(data)

    def getvalue(self) -> bytes:
        return self._data


def rows(conn, table: str, order_by: str = "id", **where) -> list:
    """All rows of a table as dicts, filtered by column equality (SQLAlchemy Core, works on both databases)."""
    from app import db
    t = db.TABLES[table]
    stmt = select(t).order_by(t.c[order_by])
    for k, v in where.items():
        stmt = stmt.where(t.c[k] == v)
    return db.all_rows(conn, stmt)


def all_text(conn) -> str:
    """Every value in every table, as one string (for privacy checks). Password hashes and salts are left out: they
    are random hex and can contain digit runs that look like phone numbers."""
    out = []
    for t in ("users", "score_checks", "applications", "repayments", "audit_log"):
        for r in rows(conn, t):
            out.extend(str(v) for k, v in r.items() if k not in ("password_hash", "salt"))
    return "\n".join(out)


# ---------------------------------------------------------------- database backends for the tests
# The default run uses SQLite only. Tests parametrised with BACKENDS also run on PostgreSQL when DATABASE_URL points
# at one (they are marked `postgres` and skipped otherwise). Each PostgreSQL test gets its own throw-away schema
# (search_path), so the tests never touch existing tables, even if DATABASE_URL points at a real database.
BACKENDS = ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]


def postgres_url():
    from app import db
    url = os.environ.get("DATABASE_URL")
    if url and db.backend_name(db.normalise_url(url)) == "postgresql":
        return db.normalise_url(url)
    return None


@contextmanager
def database(backend: str, tmp_path: Path):
    """An engine on an empty database with the app schema: a SQLite file in tmp_path, or a new PostgreSQL schema."""
    from app import db
    admin, schema = None, None
    if backend == "sqlite":
        engine = db.make_engine("sqlite:///" + (tmp_path / "private" / "app.db").as_posix())
    else:
        url = postgres_url()
        if url is None:
            pytest.skip("set DATABASE_URL to a PostgreSQL database to run the postgres tests")
        schema = "apptest_" + uuid.uuid4().hex[:12]
        admin = db.make_engine(url)
        with admin.begin() as c:
            c.execute(CreateSchema(schema))
        engine = db.make_engine(url, search_path=schema)
    db.create_schema(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        if admin is not None:
            with admin.begin() as c:
                c.execute(DropSchema(schema, cascade=True))
            admin.dispose()
