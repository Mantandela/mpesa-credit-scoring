"""Web app service layer (app/service.py): Check score, estimated eligibility, Apply (fresh scoring), privacy.

Uses a toy model trained in a temporary folder (tests/app_helpers.py) and synthetic statements only. Under that
model the default toy statement is Very high risk (not eligible) and RICH (about KES 164,000 a month) is Low risk:
eligible up to KES 34,300, comfortable up to KES 9,200. Every test runs on SQLite, and on PostgreSQL too when
DATABASE_URL points at one (marked `postgres`).
"""
import json
import re
import threading
from datetime import datetime

import pytest

import app_helpers as H
from app import auth, db, service

import eligibility as EL
import predict as P
import toy

PW = "correct-horse-1"
RICH = toy.make_vendor(days=120, daily_in=164000 / 30)
NO_INCOME = toy.recompute_balance(toy.make_vendor()[lambda d: d.paid_in == 0].reset_index(drop=True), opening=50000.0)


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    return H.build_app_models(tmp_path_factory.mktemp("app_models"))


@pytest.fixture(params=H.BACKENDS)
def env(request, models, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODEL_PATH", str(models["model"]))
    monkeypatch.setenv("APP_REFERENCE_PATH", str(models["ref"]))
    with H.database(request.param, tmp_path) as engine:
        conn = db.connect(engine)
        vendor = service.register_vendor(conn, "Test Vendor", "vendor@example.com", PW, PW)
        lender_id = auth.create_user(conn, "umoja@example.com", "Umoja desk", PW, "lender", org_name="Umoja SACCO")
        lender_b = auth.create_user(conn, "tumaini@example.com", "Tumaini desk", PW, "lender",
                                    org_name="Tumaini Microfinance")
        yield {"conn": conn, "engine": engine, "vendor": vendor, "lender_id": lender_id, "lender_b": lender_b,
               "models": models, "tmp": tmp_path}
        conn.close()


@pytest.fixture(scope="module")
def csv_bytes():
    return H.statement_csv()


@pytest.fixture(scope="module")
def rich_bytes():
    return H.statement_csv(RICH)


def _check(env, data=None, name="statement.csv", user=None):
    data = H.statement_csv() if data is None else data
    return service.run_score_check(env["conn"], user or env["vendor"], H.Upload(data, name))


def _submit(env, check_id, amount=5000, term=14, consent=True, user=None, lender=None, now=None):
    """Apply with a SAVED score check (there is no upload on Apply)."""
    return service.submit_application(env["conn"], user or env["vendor"], lender or env["lender_id"], check_id,
                                      amount, term, consent, now=now)


def _later(check, days):
    """Seconds since the epoch, `days` after the check was made (to control the clock)."""
    return datetime.fromisoformat(check["created_at"]).timestamp() + days * 86400


# ---------------------------------------------------------------- check score
def test_score_check_returns_the_summary_with_eligibility_and_saves_it(env, rich_bytes):
    s = _check(env, rich_bytes)
    assert 300 <= s["score"] <= 850 and 0 < s["pd"] < 1 and s["tier"].endswith("risk")
    assert [p["name"] for p in s["pillars"]] == list(service.PILLAR_NAMES.values())
    assert all(p["label"] in {"Weak", "Fair", "Good", "Strong"} for p in s["pillars"])
    assert 1 <= len(s["reasons"]) <= 5 and all(r["direction"] in {"Raises risk", "Lowers risk"} for r in s["reasons"])
    assert s["rows_read"] > 100 and s["check_id"] is not None
    assert s["monthly_income"] == pytest.approx(164000, rel=1e-9)
    el = s["eligibility"]
    assert el == EL.eligibility(s["tier"], s["monthly_income"], service.cutoffs())
    assert (el["status"], el["max_amount"], el["comfortable_amount"]) == ("eligible", 34300, 9200)
    row, = H.rows(env["conn"], "score_checks", id=s["check_id"])
    assert row["score"] == s["score"] and row["user_id"] == env["vendor"]["id"] and row["rows_read"] == s["rows_read"]
    assert (row["max_amount"], row["comfortable_amount"]) == (34300, 9200)
    latest = service.latest_check(env["conn"], env["vendor"]["id"])
    assert latest["score"] == s["score"] and latest["eligibility"]["max_amount"] == 34300
    audit = H.rows(env["conn"], "audit_log", action="score_check")
    assert len(audit) == 1 and audit[0]["target"] == f"check:{s['check_id']}"


def test_check_score_needs_no_amount_or_term_and_scores_at_the_median_request(env, csv_bytes, models):
    import inspect
    assert list(inspect.signature(service.run_score_check).parameters) == ["conn", "user", "file", "filename", "now"]
    s = _check(env, csv_bytes)
    direct = P.score_statement(toy.make_vendor(), model_path=str(models["model"]), reference_path=str(models["ref"]))
    assert s["pd"] == pytest.approx(direct["probability_of_default"], abs=1e-12)
    assert (s["request_amount"], s["request_term"]) == service.median_request()


def test_very_high_tier_is_not_eligible(env, csv_bytes):
    s = _check(env, csv_bytes)
    assert s["tier"] == "Very high risk"
    assert s["eligibility"] == {"status": "not_eligible", "max_amount": 0, "comfortable_amount": 0, "tier_factor": 0.0}
    row, = H.rows(env["conn"], "score_checks", id=s["check_id"])
    assert service.latest_check(env["conn"], env["vendor"]["id"])["eligibility"]["status"] == "not_eligible"
    assert row["max_amount"] == 0


def test_no_income_is_unknown(env):
    s = _check(env, H.statement_csv(NO_INCOME))
    assert s["monthly_income"] is None and s["eligibility"]["status"] == "unknown"
    assert service.latest_check(env["conn"], env["vendor"]["id"])["eligibility"]["status"] == "unknown"


def test_save_results_off_stores_nothing(env, rich_bytes):
    user = service.update_profile_flags(env["conn"], env["vendor"]["id"], save_results=False)
    s = _check(env, rich_bytes, user=user)
    assert s["check_id"] is None and s["eligibility"]["status"] == "eligible"
    assert db.count(env["conn"], "score_checks") == 0
    assert [r["target"] for r in H.rows(env["conn"], "audit_log", action="score_check")] == ["not_saved"]


def test_only_vendors_can_score_or_apply(env, csv_bytes):
    lender = auth.get_user(env["conn"], env["lender_id"])
    with pytest.raises(auth.AccessDenied):
        _check(env, csv_bytes, user=lender)
    with pytest.raises(auth.AccessDenied):
        _submit(env, csv_bytes, user=lender)


# ---------------------------------------------------------------- affordability (what-if, no re-scoring)
@pytest.mark.parametrize("ratio, band", [
    (0.0, "comfortable"), (0.056, "comfortable"), (H.REAL_P50, "comfortable"), (0.0564, "stretched"),
    (0.419, "stretched"), (H.REAL_P85, "stretched"), (0.4195, "heavy"), (5.0, "heavy")])
def test_affordability_band_boundaries(env, ratio, band):
    assert service.affordability_band(ratio, 1.0) == band
    assert service.affordability_band(ratio * 100000, 100000) == band


def test_affordability_band_without_income_and_monotone(env):
    assert service.affordability_band(5000, None) == "unknown" and service.affordability_band(5000, 0) == "unknown"
    rank = {"comfortable": 0, "stretched": 1, "heavy": 2}
    bands = [rank[service.affordability_band(a, 50000)] for a in range(1000, 150001, 500)]
    assert bands == sorted(bands) and set(bands) == {0, 1, 2}


# ---------------------------------------------------------------- apply: with a saved score check
def test_apply_succeeds_with_a_fresh_check_and_the_snapshot_comes_from_it(env, csv_bytes, rich_bytes):
    old = _check(env, csv_bytes)                      # an older saved check from ANOTHER statement (Very high)
    check = _check(env, rich_bytes)                   # the one applied with (Low risk)
    out = _submit(env, check["check_id"], amount=20000, term=30)
    assert out["outcome"] == service.OUTCOME_SENT
    sent = out["application"]
    assert re.fullmatch(r"A-\d{3,}", sent["ref"]) and sent["lender"] == "Umoja SACCO" and sent["status"] == "pending"
    assert sent["check_id"] == check["check_id"]
    row, = H.rows(env["conn"], "applications", id=sent["id"])
    assert row["check_id"] == check["check_id"]                                     # bound to that check
    snap = json.loads(row["snapshot_json"])
    assert tuple(snap) == service.SNAPSHOT_KEYS
    assert snap["score"] == check["score"] != old["score"] and snap["tier"] == "Low risk" != old["tier"]
    assert snap["pd"] == check["pd"] and snap["data_notes"] == check["data_notes"]
    assert [(p["name"], p["label"]) for p in snap["pillars"]] == [(p["name"], p["label"]) for p in check["pillars"]]
    assert snap["reasons"] == [{"phrase": r["phrase"], "direction": r["direction"]} for r in check["reasons"]]
    assert snap["request"] == {"amount": 20000.0, "term_days": 30.0}
    assert snap["affordability"] == {"band": service.affordability_band(20000, check["monthly_income"])}
    assert snap["eligibility"] == {"max_amount": 34300, "comfortable_amount": 9200}
    assert all(set(p) == {"name", "rating", "label"} for p in snap["pillars"])
    assert "monthly_income" not in snap and "rows_read" not in json.dumps(snap)
    assert db.count(env["conn"], "score_checks") == 2   # applying saves no score check and re-scores nothing
    apps = service.list_applications(env["conn"], env["vendor"]["id"])
    assert [(a["ref"], a["lender"], a["status"]) for a in apps] == [(sent["ref"], "Umoja SACCO", "pending")]


def test_apply_never_reads_or_scores_a_statement(env, rich_bytes, monkeypatch):
    check = _check(env, rich_bytes)

    def no_scoring(*a, **kw):
        raise AssertionError("Apply must not score a statement")
    monkeypatch.setattr(P, "score_uploaded_file", no_scoring)
    assert _submit(env, check["check_id"])["outcome"] == service.OUTCOME_SENT
    import inspect
    assert "file" not in inspect.signature(service.submit_application).parameters


def test_refused_when_the_check_is_older_than_30_days(env, rich_bytes):
    assert service.APPLY_CHECK_MAX_AGE_DAYS == 30
    check = _check(env, rich_bytes)
    assert _submit(env, check["check_id"], now=_later(check, 30))["outcome"] == service.OUTCOME_SENT   # 30 days: ok
    with pytest.raises(service.UserError, match="more than 30 days old"):
        _submit(env, check["check_id"], lender=env["lender_b"], now=_later(check, 30.01))
    assert db.count(env["conn"], "applications") == 1
    assert service.check_for_apply(env["conn"], env["vendor"], now=_later(check, 31)) == (None, "expired")
    assert service.check_for_apply(env["conn"], env["vendor"], now=_later(check, 1))[0]["check_id"] == check["check_id"]


def test_amount_up_to_the_limit_is_sent_and_above_it_is_refused(env, rich_bytes):
    check = _check(env, rich_bytes)
    above = _submit(env, check["check_id"], amount=34400)
    assert above["outcome"] == service.OUTCOME_ABOVE_LIMIT and above["max_amount"] == 34300
    assert above["application"] is None and db.count(env["conn"], "applications") == 0
    at_limit = _submit(env, check["check_id"], amount=34300)
    assert at_limit["outcome"] == service.OUTCOME_SENT and db.count(env["conn"], "applications") == 1


def test_refused_when_the_check_belongs_to_another_vendor_or_does_not_exist(env, rich_bytes):
    other = service.register_vendor(env["conn"], "Other Vendor", "other@example.com", PW, PW)
    theirs = _check(env, rich_bytes, user=other)
    mine = _check(env, rich_bytes)
    for forged in (theirs["check_id"], 999999, "1 OR 1=1", None, -1):
        with pytest.raises(service.UserError, match="not available"):
            _submit(env, forged)
    assert db.count(env["conn"], "applications") == 0
    assert _submit(env, mine["check_id"])["outcome"] == service.OUTCOME_SENT


def test_refused_for_a_duplicate_pending_application(env, rich_bytes):
    check = _check(env, rich_bytes)
    first = _submit(env, check["check_id"])["application"]
    with pytest.raises(service.UserError, match="already have a pending application"):
        _submit(env, check["check_id"], amount=6000)
    assert db.count(env["conn"], "applications") == 1
    # another lender, or a new check, is a different application
    assert _submit(env, check["check_id"], lender=env["lender_b"])["outcome"] == service.OUTCOME_SENT
    newer = _check(env, rich_bytes)
    assert _submit(env, newer["check_id"])["outcome"] == service.OUTCOME_SENT
    # once the first one is decided it is no longer pending
    from sqlalchemy import update
    with db.transaction(env["conn"]):
        env["conn"].execute(update(db.applications).where(db.applications.c.id == first["id"]).values(status="declined"))
    assert _submit(env, check["check_id"])["outcome"] == service.OUTCOME_SENT


def test_very_high_tier_is_refused_and_nothing_is_sent(env, csv_bytes):
    check = _check(env, csv_bytes)
    out = _submit(env, check["check_id"], amount=1000)
    assert out["outcome"] == service.OUTCOME_NOT_ELIGIBLE and out["result"]["tier"] == "Very high risk"
    assert out["application"] is None and db.count(env["conn"], "applications") == 0


def test_no_income_data_is_refused(env):
    check = _check(env, H.statement_csv(NO_INCOME))
    out = _submit(env, check["check_id"])
    assert out["outcome"] == service.OUTCOME_NO_INCOME and db.count(env["conn"], "applications") == 0


def test_refuses_without_consent_lender_or_amount(env, rich_bytes):
    check = _check(env, rich_bytes)
    with pytest.raises(service.UserError, match="Tick the box"):
        _submit(env, check["check_id"], consent=False)
    with pytest.raises(service.UserError, match="Choose a lender"):
        _submit(env, check["check_id"], lender=env["vendor"]["id"])
    with pytest.raises(service.UserError, match="above 0"):
        _submit(env, check["check_id"], amount=0)
    assert db.count(env["conn"], "applications") == 0


def test_with_save_results_off_there_is_no_check_to_apply_with(env, rich_bytes):
    user = service.update_profile_flags(env["conn"], env["vendor"]["id"], save_results=False)
    unsaved = _check(env, rich_bytes, user=user)
    assert unsaved["check_id"] is None
    assert service.check_for_apply(env["conn"], user) == (None, "not_saved")
    with pytest.raises(service.UserError, match="not available"):
        _submit(env, unsaved["check_id"], user=user)
    assert db.count(env["conn"], "applications") == 0


def test_audit_rows_hold_fixed_codes_and_ids_only(env, rich_bytes, csv_bytes):
    rich = _check(env, rich_bytes)
    poor = _check(env, csv_bytes)
    _submit(env, rich["check_id"], amount=34400)                                         # above limit
    _submit(env, poor["check_id"], amount=1000)                                          # not eligible
    _submit(env, _check(env, H.statement_csv(NO_INCOME))["check_id"])                   # no income data
    sent = _submit(env, rich["check_id"], amount=12345)["application"]
    refused = H.rows(env["conn"], "audit_log", action="application_refused")
    assert [r["detail"] for r in refused] == ["above_limit", "not_eligible", "no_income_data"]
    assert all(r["target"] is None for r in refused)
    submitted = H.rows(env["conn"], "audit_log", action="application_submitted")
    assert [(r["actor_id"], r["target"], r["detail"]) for r in submitted] == [
        (env["vendor"]["id"], f"application:{sent['id']}", f"check:{rich['check_id']}")]
    from app import staff_service as SS
    assert SS.describe("application_submitted", f"application:{sent['id']}", f"check:{rich['check_id']}", None) == \
        f"Sent application {sent['ref']} with score check C-{100 + rich['check_id']}"
    text = " ".join(str(v) for r in H.rows(env["conn"], "audit_log") for v in r.values())
    for s in ("34400", "34300", "12345", ".csv", "JANE", "statement", "0722987654"):
        assert s not in text, s


# ---------------------------------------------------------------- references
def test_two_vendors_applying_at_the_same_time_get_different_references(env):
    """Two vendors, each on its own connection, store 5 applications at the same moment (a barrier releases them
    together). References come from the row id, so all 10 differ and match their rows."""
    second = service.register_vendor(env["conn"], "Second Vendor", "second@example.com", PW, PW)
    summary = {"score": 640, "pd": 0.11, "tier": "Moderate risk", "pillars": [], "reasons": [], "data_notes": [],
               "request_amount": 5000.0, "request_term": 14.0, "affordability_band": "comfortable",
               "eligibility": {"status": "eligible", "max_amount": 24000, "comfortable_amount": 9200}}
    lender = {"id": env["lender_id"], "org_name": "Umoja SACCO"}
    barrier, refs, errors = threading.Barrier(2), [], []

    def send(vendor):
        conn = db.connect(env["engine"])
        try:
            barrier.wait()
            for _ in range(5):
                refs.append(service._insert_application(conn, vendor, lender, service.snapshot(summary))["ref"])
        except Exception as e:      # noqa: BLE001
            errors.append(e)
        finally:
            conn.close()
    threads = [threading.Thread(target=send, args=(v,)) for v in (env["vendor"], second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert len(refs) == 10 and len(set(refs)) == 10
    stored = H.rows(env["conn"], "applications")
    assert sorted(r["ref"] for r in stored) == sorted(refs)
    assert all(r["ref"] == f"A-{100 + r['id']}" for r in stored)


def test_list_lenders_shows_organisations(env):
    assert [l["org_name"] for l in service.list_lenders(env["conn"])] == ["Tumaini Microfinance", "Umoja SACCO"]


def test_delete_saved_results_keeps_sent_applications(env, rich_bytes):
    _check(env, rich_bytes)
    check = _check(env, rich_bytes)
    sent = _submit(env, check["check_id"])["application"]
    assert len(service.score_history(env["conn"], env["vendor"]["id"])) == 2
    assert service.delete_saved_results(env["conn"], env["vendor"]) == 2
    assert service.score_history(env["conn"], env["vendor"]["id"]) == [] and service.latest_check(env["conn"], env["vendor"]["id"]) is None
    app, = H.rows(env["conn"], "applications", id=sent["id"])
    assert json.loads(app["snapshot_json"])["score"] > 0                                 # the lender copy stays
    assert app["check_id"] is None                                                       # the link is cleared
    assert [r["detail"] for r in H.rows(env["conn"], "audit_log", action="delete_saved_results")] == ["checks=2"]


# ---------------------------------------------------------------- privacy and files
def test_no_statement_content_in_the_database_or_audit_log(env, rich_bytes):
    s = _check(env, rich_bytes, name="JANE WANJIKU statement 0722987654.csv")
    out = _submit(env, s["check_id"], amount=9000)
    assert out["outcome"] == service.OUTCOME_SENT
    text = H.all_text(env["conn"]) + json.dumps(s) + json.dumps(out)
    for name in H.NAMES:
        for part in name.split():
            assert part not in text.upper(), "a name from the statement was stored"
    for phone in H.PHONES:
        assert phone not in text
    assert not re.search(r"(?<![\d.])\d{9,}", text), "a phone-like digit run was stored"
    for word in ("Merchant Payment", "Customer Withdrawal", "CP_", "Receipt", "statement 0722"):
        assert word not in text


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


def test_uploaded_temp_file_is_removed(env, csv_bytes, rich_bytes, temp_files):
    d, made = temp_files
    _check(env, csv_bytes)                                                     # check score
    check = _check(env, rich_bytes)
    _submit(env, check["check_id"])                                            # apply: no file at all
    _submit(env, check["check_id"], amount=10 ** 6, lender=env["lender_b"])    # apply, above limit
    with pytest.raises(service.UserError, match="could not read"):
        _check(env, b"Receipt No.,Completion Time\nx,y\n")
    assert len(made) == 3 and not any(d.iterdir())


def test_rejected_files_are_never_written(env, temp_files):
    d, made = temp_files
    with pytest.raises(service.UserError, match="Excel"):
        _check(env, b"data", name="statement.docx")
    with pytest.raises(service.UserError, match="10 MB"):
        _check(env, b"x" * (service.MAX_UPLOAD_BYTES + 1))
    with pytest.raises(service.UserError, match="empty"):
        _check(env, b"")
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


@pytest.mark.parametrize("raised, message", [
    (ValueError("No usable transactions before the application date 2026-01-01."), service.MSG_TOO_SHORT),
    (ValueError("The statement has no transactions."), service.MSG_TOO_SHORT),
    (ValueError("could not convert 'JANE' to float"), service.MSG_UNREADABLE),
    (FileNotFoundError("models/logistic.joblib"), service.MSG_NO_MODEL),
    (ImportError("shap"), service.MSG_NO_MODEL),
    (KeyError("Details"), service.MSG_UNREADABLE),
])
def test_every_scoring_failure_maps_to_a_fixed_message(env, monkeypatch, raised, message):
    def fail(*a, **kw):
        raise raised
    monkeypatch.setattr(P, "score_uploaded_file", fail)
    with pytest.raises(service.UserError) as e:
        _check(env, b"x,y\n")
    assert str(e.value) == message and e.value.__cause__ is None


def test_model_not_ready_has_its_own_message(env, monkeypatch, tmp_path):
    monkeypatch.setenv("APP_MODEL_PATH", str(tmp_path / "missing.joblib"))
    with pytest.raises(service.UserError, match="scoring engine is still starting"):
        _check(env, b"x,y\n")


def _drop_eligibility_columns(conn):
    """Turn the database into the schema of the previous version (score_checks without the eligibility columns)."""
    with db.transaction(conn):
        conn.exec_driver_sql("ALTER TABLE score_checks DROP COLUMN max_amount")
        conn.exec_driver_sql("ALTER TABLE score_checks DROP COLUMN comfortable_amount")


def test_a_database_error_while_saving_keeps_the_score(env, rich_bytes):
    _drop_eligibility_columns(env["conn"])                       # the insert now fails, as on an old database
    s = _check(env, rich_bytes)
    assert 300 <= s["score"] <= 850 and s["eligibility"]["max_amount"] == 34300   # the computed score is kept
    assert s["check_id"] is None and s["save_error"] == service.MSG_DB_SAVE
    assert env["conn"].exec_driver_sql("SELECT COUNT(*) FROM score_checks").scalar() == 0
    assert db.count(env["conn"], "audit_log", action="score_check") == 0          # rolled back together


def test_a_saved_score_has_no_save_error(env, rich_bytes):
    assert _check(env, rich_bytes)["save_error"] is None


def test_a_database_error_while_sending_is_a_fixed_message(env, rich_bytes, monkeypatch):
    from sqlalchemy.exc import OperationalError

    def fail(*a, **kw):
        raise OperationalError("INSERT INTO applications ...", {"snapshot_json": "secret"}, Exception("JANE"))
    check = _check(env, rich_bytes)
    monkeypatch.setattr(service, "_insert_application", fail)
    with pytest.raises(service.UserError) as e:
        _submit(env, check["check_id"])
    assert str(e.value) == service.MSG_DB_APPLY and e.value.__cause__ is None
    assert db.count(env["conn"], "applications") == 0


def test_unexpected_reader_errors_never_leak_their_text(env, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("cell value JANE WANJIKU 0722987654")
    monkeypatch.setattr(P, "score_uploaded_file", boom)
    with pytest.raises(service.UserError) as e:
        _check(env, b"x,y\n")
    assert str(e.value) == service.MSG_UNREADABLE and e.value.__cause__ is None and e.value.__suppress_context__
