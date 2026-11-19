"""Shared setup for the web app tests (tests/test_app_*.py). No real data and no trained artifacts are needed.

build_app_models() trains the same tiny toy logistic model as tests/test_predict.py and writes reference.json with
the REAL affordability cutoffs of the trained model (50th / 85th percentile 0.0564 / 0.4194), so band tests use the
numbers the app shows. statement_csv() writes a synthetic statement with made-up names and phone numbers in the
details, to check that none of it reaches the database, the audit log or the result.
"""
import sys
from pathlib import Path

import joblib

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


def all_text(conn) -> str:
    """Every value in every table, as one string (for privacy checks). Password hashes and salts are left out: they
    are random hex and can contain digit runs that look like phone numbers."""
    out = []
    for t in ("users", "score_checks", "applications", "audit_log"):
        for r in conn.execute(f"SELECT * FROM {t}"):
            out.extend(str(r[k]) for k in r.keys() if k not in ("password_hash", "salt"))
    return "\n".join(out)
