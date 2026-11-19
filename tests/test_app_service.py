"""Web app service layer (app/service.py): scoring an upload, affordability bands, applications, privacy.

Uses a toy model trained in a temporary folder (tests/app_helpers.py) and synthetic statements only.
"""
import json
import re

import pytest

import app_helpers as H
from app import auth, db, service

import predict as P
import toy

PW = "correct-horse-1"


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    return H.build_app_models(tmp_path_factory.mktemp("app_models"))


@pytest.fixture
def env(models, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODEL_PATH", str(models["model"]))
    monkeypatch.setenv("APP_REFERENCE_PATH", str(models["ref"]))
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    conn = db.connect()
    vendor = service.register_vendor(conn, "Test Vendor", "vendor@example.com", PW, PW)
    lender_id = auth.create_user(conn, "umoja@example.com", "Umoja desk", PW, "lender", org_name="Umoja SACCO")
    auth.create_user(conn, "tumaini@example.com", "Tumaini desk", PW, "lender", org_name="Tumaini Microfinance")
    yield {"conn": conn, "vendor": vendor, "lender_id": lender_id, "models": models, "tmp": tmp_path}
    conn.close()


@pytest.fixture(scope="module")
def csv_bytes():
    return H.statement_csv()


def _check(env, data=None, amount=5000, term=14, name="statement.csv", user=None):
    data = H.statement_csv() if data is None else data
    return service.run_score_check(env["conn"], user or env["vendor"], H.Upload(data, name), amount, term)


# ---------------------------------------------------------------- scoring
def test_score_check_returns_the_summary_and_saves_it(env, csv_bytes):
    s = _check(env, csv_bytes)
    assert 300 <= s["score"] <= 850 and 0 < s["pd"] < 1 and s["tier"].endswith("risk")
    assert [p["name"] for p in s["pillars"]] == list(service.PILLAR_NAMES.values())
    assert all(p["label"] in {"Weak", "Fair", "Good", "Strong"} for p in s["pillars"])
    assert 1 <= len(s["reasons"]) <= 5 and all(r["direction"] in {"Raises risk", "Lowers risk"} for r in s["reasons"])
    assert s["rows_read"] > 100 and s["monthly_income"] > 0 and s["check_id"] is not None
    row = env["conn"].execute("SELECT * FROM score_checks WHERE id = ?", (s["check_id"],)).fetchone()
    assert row["score"] == s["score"] and row["user_id"] == env["vendor"]["id"] and row["rows_read"] == s["rows_read"]
    assert service.latest_check(env["conn"], env["vendor"]["id"])["score"] == s["score"]
    audit = env["conn"].execute("SELECT * FROM audit_log WHERE action = 'score_check'").fetchall()
    assert len(audit) == 1 and audit[0]["target"] == f"check:{s['check_id']}"


def test_score_is_evaluated_at_the_median_request(env, csv_bytes, models):
    a = _check(env, csv_bytes, amount=1000, term=7)
    b = _check(env, csv_bytes, amount=200000, term=60)
    for k in ("score", "pd", "tier", "pillars", "reasons", "data_notes"):
        assert a[k] == b[k], k
    direct = P.score_statement(toy.make_vendor(), model_path=str(models["model"]), reference_path=str(models["ref"]))
    assert a["pd"] == pytest.approx(direct["probability_of_default"], abs=1e-12)        # median request by default
    assert service.median_request() == (models["reference"]["requested_amount"]["median"],
                                        models["reference"]["requested_term_days"]["median"])


def test_raw_amount_is_not_clipped(env):
    vendor = toy.make_vendor(days=120, daily_in=164000 / 30)           # about KES 164,000 of income a month
    s = _check(env, H.statement_csv(vendor), amount=200000, term=30)
    assert s["request_amount"] == 200000.0
    assert s["monthly_income"] == pytest.approx(164000, rel=1e-9)
    assert s["affordability_band"] == "heavy" and s["outside_typical_range"]
    small = _check(env, H.statement_csv(vendor), amount=5000, term=14)
    assert small["affordability_band"] == "comfortable" and not small["outside_typical_range"]
    assert small["score"] == s["score"]


def test_save_results_off_stores_nothing(env, csv_bytes):
    user = service.update_profile_flags(env["conn"], env["vendor"]["id"], save_results=False)
    s = _check(env, csv_bytes, user=user)
    assert s["check_id"] is None and s["score"]
    assert env["conn"].execute("SELECT COUNT(*) FROM score_checks").fetchone()[0] == 0
    assert env["conn"].execute("SELECT target FROM audit_log WHERE action = 'score_check'").fetchone()[0] == "not_saved"


def test_only_vendors_can_score(env, csv_bytes):
    lender = auth.get_user(env["conn"], env["lender_id"])
    with pytest.raises(auth.AccessDenied):
        _check(env, csv_bytes, user=lender)


# ---------------------------------------------------------------- affordability
@pytest.mark.parametrize("ratio, band", [
    (0.0, "comfortable"), (0.056, "comfortable"), (H.REAL_P50, "comfortable"), (0.0564, "stretched"),
    (0.419, "stretched"), (H.REAL_P85, "stretched"), (0.4195, "heavy"), (5.0, "heavy")])
def test_affordability_band_boundaries(env, ratio, band):
    assert service.affordability_band(ratio, 1.0) == band                 # amount / monthly income = ratio exactly
    assert service.affordability_band(ratio * 100000, 100000) == band


def test_affordability_band_without_income_and_monotone(env):
    assert service.affordability_band(5000, None) == "unknown" and service.affordability_band(5000, 0) == "unknown"
    rank = {"comfortable": 0, "stretched": 1, "heavy": 2}
    bands = [rank[service.affordability_band(a, 50000)] for a in range(1000, 150001, 500)]
    assert bands == sorted(bands) and set(bands) == {0, 1, 2}
    a = service.affordability(150000, 50000)
    assert a["share_of_monthly_income"] == 3.0 and a["band"] == "heavy" and a["outside_typical_range"]


def test_service_band_matches_the_scoring_function(env, csv_bytes):
    s = _check(env, csv_bytes, amount=7500, term=14)
    assert service.affordability_band(7500, s["monthly_income"]) == s["affordability_band"]


# ---------------------------------------------------------------- applications
def test_create_application_stores_only_the_summary_snapshot(env, csv_bytes):
    s = _check(env, csv_bytes)
    with pytest.raises(service.UserError, match="Tick the box"):
        service.create_application(env["conn"], env["vendor"], env["lender_id"], s, consent=False)
    sent = service.create_application(env["conn"], env["vendor"], env["lender_id"], s, amount=20000, term=30, consent=True)
    assert re.fullmatch(r"A-\d{3,}", sent["ref"]) and sent["lender"] == "Umoja SACCO" and sent["status"] == "pending"
    row = env["conn"].execute("SELECT * FROM applications WHERE id = ?", (sent["id"],)).fetchone()
    snap = json.loads(row["snapshot_json"])
    assert tuple(snap) == service.SNAPSHOT_KEYS
    assert snap["score"] == s["score"] and snap["tier"] == s["tier"] and snap["pd"] == s["pd"]
    assert snap["request"] == {"amount": 20000.0, "term_days": 30.0}
    assert snap["affordability"]["band"] == service.affordability_band(20000, s["monthly_income"])
    assert all(set(p) == {"name", "rating", "label"} for p in snap["pillars"])
    assert all(set(r) == {"phrase", "direction"} for r in snap["reasons"])
    assert set(snap["affordability"]) == {"band", "share_of_monthly_income"}
    assert '"monthly_income"' not in json.dumps(snap) and "rows_read" not in json.dumps(snap)
    apps = service.list_applications(env["conn"], env["vendor"]["id"])
    assert [(a["ref"], a["lender"], a["status"]) for a in apps] == [(sent["ref"], "Umoja SACCO", "pending")]
    with pytest.raises(service.UserError, match="Choose a lender"):
        service.create_application(env["conn"], env["vendor"], env["vendor"]["id"], s, consent=True)   # not a lender


def test_list_lenders_shows_organisations(env):
    assert [l["org_name"] for l in service.list_lenders(env["conn"])] == ["Tumaini Microfinance", "Umoja SACCO"]


def test_delete_saved_results(env, csv_bytes):
    s1 = _check(env, csv_bytes)
    _check(env, csv_bytes)
    sent = service.create_application(env["conn"], env["vendor"], env["lender_id"], s1, consent=True)
    assert len(service.score_history(env["conn"], env["vendor"]["id"])) == 2
    assert service.delete_saved_results(env["conn"], env["vendor"]) == 2
    assert service.score_history(env["conn"], env["vendor"]["id"]) == [] and service.latest_check(env["conn"], env["vendor"]["id"]) is None
    app = env["conn"].execute("SELECT check_id, snapshot_json FROM applications WHERE id = ?", (sent["id"],)).fetchone()
    assert app["check_id"] is None and json.loads(app["snapshot_json"])["score"] == s1["score"]   # the lender copy stays
    assert env["conn"].execute("SELECT detail FROM audit_log WHERE action = 'delete_saved_results'").fetchone()[0] == "checks=2"


# ---------------------------------------------------------------- privacy and files
def test_no_statement_content_in_the_database_or_audit_log(env, csv_bytes):
    s = _check(env, csv_bytes, name="JANE WANJIKU statement 0722987654.csv")
    service.create_application(env["conn"], env["vendor"], env["lender_id"], s, consent=True)
    text = H.all_text(env["conn"]) + json.dumps(s)
    for name in H.NAMES:
        for part in name.split():
            assert part not in text.upper(), "a name from the statement was stored"
    for phone in H.PHONES:
        assert phone not in text
    assert not re.search(r"(?<![\d.])\d{9,}", text), "a phone-like digit run was stored"
    for word in ("Merchant Payment", "Customer Withdrawal", "CP_", "Receipt", "statement 0722"):
        assert word not in text
    audit = " ".join(str(v) for r in env["conn"].execute("SELECT * FROM audit_log") for v in tuple(r))
    assert ".csv" not in audit and "statement" not in audit.lower()


@pytest.fixture
def temp_files(tmp_path, monkeypatch):
    """Record the temporary files the scoring function creates, in an empty folder."""
    d = tmp_path / "uploads"
    d.mkdir()
    monkeypatch.setattr(P.tempfile, "tempdir", str(d))
    made, real = [], P.tempfile.mkstemp

    def recording(*a, **kw):
        fd, name = real(*a, **kw)
        made.append(name)
        return fd, name
    monkeypatch.setattr(P.tempfile, "mkstemp", recording)
    return d, made


def test_uploaded_temp_file_is_removed(env, csv_bytes, temp_files):
    d, made = temp_files
    _check(env, csv_bytes)
    with pytest.raises(service.UserError, match="could not read"):
        _check(env, b"Receipt No.,Completion Time\nx,y\n")
    assert len(made) == 2 and not any(d.iterdir())


def test_rejected_files_are_never_written(env, temp_files):
    d, made = temp_files
    with pytest.raises(service.UserError, match="Excel"):
        _check(env, b"data", name="statement.docx")
    with pytest.raises(service.UserError, match="10 MB"):
        _check(env, b"x" * (service.MAX_UPLOAD_BYTES + 1))
    with pytest.raises(service.UserError, match="empty"):
        _check(env, b"")
    with pytest.raises(service.UserError, match="above 0"):
        _check(env, b"x,y\n", amount=0)
    assert not made and not any(d.iterdir())


def test_scanned_pdf_gets_the_friendly_message(env, tmp_path, temp_files):
    from reportlab.pdfgen import canvas
    p = tmp_path / "scan.pdf"
    c = canvas.Canvas(str(p))
    c.rect(50, 50, 300, 300, fill=1)
    c.showPage()
    c.save()
    with pytest.raises(service.UserError) as e:
        _check(env, p.read_bytes(), name="scan.pdf")
    assert str(e.value) == "This PDF has no selectable text. Please upload the Excel or CSV statement."
    d, made = temp_files
    assert len(made) == 1 and not any(d.iterdir())


def test_unexpected_reader_errors_never_leak_their_text(env, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("cell value JANE WANJIKU 0722987654")
    monkeypatch.setattr(P, "score_uploaded_file", boom)
    with pytest.raises(service.UserError) as e:
        _check(env, b"x,y\n")
    assert str(e.value) == service.MSG_UNREADABLE and e.value.__cause__ is None and e.value.__suppress_context__
