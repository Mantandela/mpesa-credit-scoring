"""Repayment tracking: the rules in staff_service.record_repayment and export_outcomes (SQLite, and PostgreSQL when
DATABASE_URL points at it), and the Decided page, vendor History and admin Overview screens (SQLite, AppTest).
All outcomes here are simulated."""
import csv
import io
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert, update
from streamlit.testing.v1 import AppTest

import app_helpers as H
from app import auth, components as ui, db, service, staff_service as SS
from app.db import applications, repayments
from test_app_staff import MAIN, SECRET_NOTE, VENDOR_NAME, send, setup_accounts, snap

T0 = datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc).timestamp()      # 10:00 in Nairobi; due 15 Nov for 14 days
DAY = 86400


@pytest.fixture(params=H.BACKENDS)
def env(request, tmp_path):
    with H.database(request.param, tmp_path) as engine:
        conn = db.connect(engine)
        yield setup_accounts(conn)
        conn.close()


def approved(env, lender=None, term=14.0, at=T0, **kw):
    lender = lender or env["a"]
    app = send(env, lender, snap(term=term, **kw))
    SS.decide_application(env["conn"], lender, app["id"], "approved", now=at)
    return app


def rows(conn, action):
    return [r for r in H.rows(conn, "audit_log") if r["action"] == action]


# ================================================================ service rules
def test_each_final_outcome_is_recorded_once_and_never_changes(env):
    c, a = env["conn"], env["a"]
    ids = [approved(env)["id"] for _ in range(3)]
    out = {}
    for app_id, status, when in ((ids[0], "repaid_on_time", T0 + 3 * DAY), (ids[1], "repaid_late", T0 + 20 * DAY),
                                 (ids[2], "defaulted", T0 + 20 * DAY)):
        out[status] = SS.record_repayment(c, a, app_id, status, SECRET_NOTE, now=when)
        assert out[status]["repayment"]["status"] == status and out[status]["repayment"]["terminal"]
    stored = {r["application_id"]: r for r in H.rows(c, "repayments")}
    assert [stored[i]["status"] for i in ids] == ["repaid_on_time", "repaid_late", "defaulted"]
    assert all(str(stored[i]["due_date"]) == "2026-11-15" and stored[i]["recorded_by"] == a["id"] for i in ids)
    # a final status is final: every further move is refused, defaulted included, and nothing changes
    refused = 0
    for app_id in ids:
        for status in service.TERMINAL_STATUSES:
            with pytest.raises(SS.RepaymentError, match="already recorded"):
                SS.record_repayment(c, a, app_id, status, now=T0 + 40 * DAY)
            refused += 1
    assert [r["status"] for r in H.rows(c, "repayments")] == ["repaid_on_time", "repaid_late", "defaulted"]
    # audit: one row per change (actor, reference, old -> new; never the note); one generic line per refusal
    rec = rows(c, "repayment_recorded")
    assert [(r["actor_id"], r["detail"]) for r in rec] == [(a["id"], "repaying->repaid_on_time"),
                                                           (a["id"], "repaying->repaid_late"),
                                                           (a["id"], "repaying->defaulted")]
    assert [r["target"] for r in rec] == [f"A-{100 + i}" for i in ids]
    ref = rows(c, "repayment_refused")
    assert len(ref) == refused and all(r["target"] is None and r["detail"] is None for r in ref)
    assert all(SECRET_NOTE not in str(r) for r in H.rows(c, "audit_log"))
    assert SS.describe("repayment_recorded", "A-101", "repaying->repaid_late", None) == \
        "Recorded repayment for A-101: Repaying to Repaid late"


@pytest.mark.parametrize("status", ["repaying", "approved", "paid", "", None])
def test_anything_but_a_final_outcome_is_refused(env, status):
    app = approved(env)
    with pytest.raises(SS.RepaymentError, match="Choose Repaid on time"):
        SS.record_repayment(env["conn"], env["a"], app["id"], status, now=T0 + DAY)
    assert H.rows(env["conn"], "repayments") == [] and len(rows(env["conn"], "repayment_refused")) == 1


def test_only_the_approving_lender_can_record(env):
    c = env["conn"]
    app = approved(env)
    for who in ("b", "vendor", "admin"):                                     # another lender, a vendor, an admin
        with pytest.raises(auth.AccessDenied):
            SS.record_repayment(c, env[who], app["id"], "repaid_on_time", now=T0 + DAY)
    with pytest.raises(auth.AccessDenied):
        SS.record_repayment(c, None, app["id"], "repaid_on_time", now=T0 + DAY)
    assert H.rows(c, "repayments") == [] and len(rows(c, "repayment_refused")) == 4
    theirs = approved(env, lender=env["b"])                                  # b sees only b's repayments
    assert [x["id"] for x in SS.lender_applications(c, env["b"])] == [theirs["id"]]


def test_only_approved_loans_have_a_repayment(env):
    c, a = env["conn"], env["a"]
    pending = send(env, a)
    declined = send(env, a)
    SS.decide_application(c, a, declined["id"], "declined", now=T0)
    for app in (pending, declined):
        with pytest.raises(SS.RepaymentError, match="Only approved"):
            SS.record_repayment(c, a, app["id"], "repaid_on_time", now=T0 + DAY)
        assert SS.lender_application(c, a, app["id"])["repayment"] is None
    assert H.rows(c, "repayments") == []


def test_default_only_after_the_due_date_and_outcomes_only_after_approval(env, monkeypatch):
    c, a = env["conn"], env["a"]
    app = approved(env, term=14.0)                               # approved 1 Nov 10:00 Nairobi, due 15 Nov
    with pytest.raises(SS.RepaymentError, match="only after the loan was approved"):
        SS.record_repayment(c, a, app["id"], "repaid_on_time", now=T0 - 3600)
    for days in (0, 13, 14):                                     # up to and including the due date: refused
        with pytest.raises(SS.RepaymentError, match="only after the due date"):
            SS.record_repayment(c, a, app["id"], "defaulted", now=T0 + days * DAY)
    # the injectable clock: service.CLOCK is what "today" means when no `now` is passed
    monkeypatch.setattr(service, "CLOCK", lambda: T0 + 14 * DAY + 5 * 3600)       # 15 Nov 15:00: still the due date
    with pytest.raises(SS.RepaymentError, match="only after the due date"):
        SS.record_repayment(c, a, app["id"], "defaulted")
    monkeypatch.setattr(service, "CLOCK", lambda: T0 + 14 * DAY + 15 * 3600)      # 16 Nov 01:00 Nairobi: passed
    assert SS.record_repayment(c, a, app["id"], "defaulted")["repayment"]["status"] == "defaulted"


def test_on_time_and_late_can_be_recorded_before_the_due_date(env):
    c, a = env["conn"], env["a"]
    one, two = approved(env), approved(env)
    assert SS.record_repayment(c, a, one["id"], "repaid_on_time", now=T0 + 60)["repayment"]["status"] == "repaid_on_time"
    assert SS.record_repayment(c, a, two["id"], "repaid_late", now=T0 + 2 * DAY)["repayment"]["status"] == "repaid_late"


def test_note_is_optional_trimmed_and_at_most_300_characters(env):
    c, a = env["conn"], env["a"]
    app = approved(env)
    with pytest.raises(SS.RepaymentError, match="300"):
        SS.record_repayment(c, a, app["id"], "repaid_on_time", "x" * 301, now=T0 + DAY)
    SS.record_repayment(c, a, app["id"], "repaid_on_time", "   ", now=T0 + DAY)
    assert H.rows(c, "repayments")[0]["note"] is None


def test_a_second_tab_recording_at_the_same_moment_is_refused(env, monkeypatch):
    """Both tabs read "repaying"; the unique application_id lets only the first insert through."""
    c, a = env["conn"], env["a"]
    app = approved(env)
    stale = SS.lender_application(c, a, app["id"])                          # what the second tab read
    SS.record_repayment(c, a, app["id"], "repaid_on_time", now=T0 + DAY)
    real = SS.lender_application
    calls = {"n": 0}

    def first_stale(conn, user, app_id):
        calls["n"] += 1
        return stale if calls["n"] == 1 else real(conn, user, app_id)
    monkeypatch.setattr(SS, "lender_application", first_stale)
    with pytest.raises(SS.RepaymentError, match="already recorded"):
        SS.record_repayment(c, a, app["id"], "repaid_late", now=T0 + DAY)
    assert [r["status"] for r in H.rows(c, "repayments")] == ["repaid_on_time"]
    assert len(rows(c, "repayment_recorded")) == 1


def test_export_has_only_the_listed_columns_and_final_outcomes(env):
    c, a, adm = env["conn"], env["a"], env["admin"]
    done = approved(env, score=702, tier="Low risk", amount=7350.0, term=21.0)
    late = approved(env)
    open_ = approved(env)                                                    # still repaying: not exported
    send(env, a)                                                             # pending: not exported
    SS.record_repayment(c, a, done["id"], "repaid_on_time", SECRET_NOTE, now=T0 + DAY)
    SS.record_repayment(c, a, late["id"], "repaid_late", "<b>late</b>", now=T0 + 30 * DAY)
    for who in ("a", "vendor"):
        with pytest.raises(auth.AccessDenied):
            SS.export_outcomes(c, env[who])
    text, n = SS.export_outcomes(c, adm, now=T0 + 31 * DAY)
    table = list(csv.reader(io.StringIO(text)))
    assert tuple(table[0]) == SS.EXPORT_COLUMNS == (
        "application_id", "score_check_id", "snapshot_score", "snapshot_pd", "risk_tier", "requested_amount",
        "repay_within_days", "final_status", "recorded_date")
    assert n == 2 and len(table) == 3
    by_id = {int(r[0]): dict(zip(table[0], r)) for r in table[1:]}
    assert set(by_id) == {done["id"], late["id"]} and open_["id"] not in by_id
    first = by_id[done["id"]]
    assert first == {"application_id": str(done["id"]), "score_check_id": "", "snapshot_score": "702",
                     "snapshot_pd": "0.123000", "risk_tier": "Low risk", "requested_amount": "7350.00",
                     "repay_within_days": "21", "final_status": "repaid_on_time", "recorded_date": "2026-11-02"}
    for leak in (SECRET_NOTE, "<b>late</b>", VENDOR_NAME, "@example.test", "Umoja", "Repay on Fridays"):
        assert leak not in text, leak
    audit = rows(c, "outcomes_exported")
    assert [(r["actor_id"], r["detail"]) for r in audit] == [(adm["id"], "rows=2")]
    assert SS.describe("outcomes_exported", None, "rows=2", None) == "Exported repayment outcomes (2 rows)"


def test_overview_counts_outcomes(env):
    c, a, adm = env["conn"], env["a"], env["admin"]
    apps = [approved(env) for _ in range(4)]
    SS.record_repayment(c, a, apps[0]["id"], "repaid_on_time", now=T0 + DAY)
    SS.record_repayment(c, a, apps[1]["id"], "defaulted", now=T0 + 20 * DAY)
    o = SS.admin_overview(c, adm)
    assert o["outcomes"] == {"repaying": 2, "repaid_on_time": 1, "repaid_late": 0, "defaulted": 1}
    assert o["outcomes_recorded"] == 2
    assert SS.repayment_counts(SS.lender_applications(c, a)) == o["outcomes"]


def test_the_due_date_uses_the_nairobi_calendar_day():
    late_evening_utc = datetime(2026, 11, 25, 21, 30, tzinfo=timezone.utc)   # 26 Nov 00:30 in Nairobi
    assert str(service.due_date(late_evening_utc, 14)) == "2026-12-10"
    assert str(service.due_date(late_evening_utc, 13.2)) == "2026-12-10"     # part days round up


# ================================================================ screens (SQLite, AppTest)
@pytest.fixture
def penv(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODEL_PATH", str(tmp_path / "missing" / "logistic.joblib"))
    monkeypatch.setenv("APP_REFERENCE_PATH", str(tmp_path / "missing" / "reference.json"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    url = db.database_url()
    conn = db.connect()
    yield setup_accounts(conn)
    conn.close()
    engine = db._ENGINES.pop(url, None)
    if engine is not None:
        engine.dispose()


def _app(**state) -> AppTest:
    at = AppTest.from_file(MAIN, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def _text(at) -> str:
    parts = [m.value for m in at.markdown if "<style>" not in m.value]
    parts += [b.label for b in at.button] + [w.label for w in (*at.radio, *at.text_area)]
    return "\n".join(parts)


def _ok(at):
    assert not at.exception, [e.value for e in at.exception]


def _keys(at, prefix):
    return [b.key for b in at.button if b.key and b.key.startswith(prefix)]


def _approve_days_ago(penv, days, **kw):
    """An approved application decided `days` ago on the real clock (the screens use it)."""
    app = send(penv, penv["a"], snap(**kw))
    SS.decide_application(penv["conn"], penv["a"], app["id"], "approved")
    with db.transaction(penv["conn"]):
        penv["conn"].execute(update(applications).where(applications.c.id == app["id"])
                             .values(decided_at=db.utcnow() - timedelta(days=days)))
    return app


def test_decided_page_summary_chip_and_record_dialog(penv):
    c, a = penv["conn"], penv["a"]
    fresh = _approve_days_ago(penv, 1, term=14.0)                    # 13 days left: no Defaulted choice
    overdue = _approve_days_ago(penv, 30, term=14.0)                 # 16 days overdue
    done = _approve_days_ago(penv, 5)
    SS.record_repayment(c, a, done["id"], "repaid_late")
    declined = send(penv, a)
    SS.decide_application(c, a, declined["id"], "declined")
    at = _app(user_id=a["id"], page="lender_decided")
    _ok(at)
    text = _text(at)
    counts = SS.repayment_counts(SS.lender_applications(c, a))
    assert counts == {"repaying": 2, "repaid_on_time": 0, "repaid_late": 1, "defaulted": 0}
    for label, kind, n in (("Repaying", "neutral", 2), ("On time", "good", 0), ("Late", "moderate", 1),
                           ("Defaulted", "bad", 0)):
        assert f'<span class="rsum-n">{n}</span>{ui.pill(label, kind)}' in text, label             # summary card
    assert "Awaiting outcome 2" in at.pills(key="lender_decided_filter").options
    assert ui.pill("Repaying") in text and ui.pill("Repaid late") in text
    assert "13 days left" in text and "16 days overdue" in text and "Recorded" in text
    assert sorted(_keys(at, "rec_")) == sorted([f"rec_{fresh['id']}", f"rec_{overdue['id']}"])   # repaying only
    assert sorted(_keys(at, "mrec_")) == sorted([f"mrec_{fresh['id']}", f"mrec_{overdue['id']}"])
    at.session_state["lender_decided_filter"] = "awaiting"
    at.run()
    assert sorted(_keys(at, "open_")) == sorted([f"open_{fresh['id']}", f"open_{overdue['id']}"])

    # not yet due: Repaid on time or late only
    at.button(key=f"rec_{fresh['id']}").click().run()
    _ok(at)
    choice = at.radio(key=f"repay_choice_{fresh['id']}")
    assert choice.options == ["Repaid on time", "Repaid late"] and "Defaulted can be recorded after the due date" in _text(at)
    # overdue: Defaulted too; Continue -> the confirm step -> Confirm
    at.button(key=f"rec_{overdue['id']}").click().run()
    choice = at.radio(key=f"repay_choice_{overdue['id']}")
    assert choice.options == ["Repaid on time", "Repaid late", "Defaulted"]
    choice.set_value("defaulted").run()
    at.text_area(key=f"repay_note_{overdue['id']}").input("<script>x</script> paid nothing").run()
    at.button(key="repay_continue").click().run()
    _ok(at)
    assert "This cannot be changed afterwards." in _text(at) and ui.pill("Defaulted") in _text(at)
    assert "&lt;script&gt;x&lt;/script&gt; paid nothing" in _text(at) and "<script>x</script>" not in _text(at)
    assert H.rows(c, "repayments")[-1]["status"] == "repaid_late"            # nothing stored before Confirm
    at.button(key="repay_confirm").click().run()
    _ok(at)
    row = [r for r in H.rows(c, "repayments") if r["application_id"] == overdue["id"]][0]
    assert row["status"] == "defaulted" and row["note"] == "<script>x</script> paid nothing"
    assert f"{overdue['ref']}: Defaulted recorded." in _text(at)
    assert f"rec_{overdue['id']}" not in _keys(at, "rec_") and not at.radio                       # dialog closed
    # the review page shows it, the note escaped
    at = _app(user_id=a["id"], page="lender_review", review_id=overdue["id"], review_from="lender_decided")
    _ok(at)
    assert ui.pill("Defaulted") in _text(at) and "&lt;script&gt;" in _text(at) and "<script>x" not in _text(at)


def test_back_returns_to_the_choice_and_nothing_is_stored(penv):
    app = _approve_days_ago(penv, 1)
    at = _app(user_id=penv["a"]["id"], page="lender_decided")
    at.button(key=f"rec_{app['id']}").click().run()
    at.button(key="repay_continue").click().run()
    at.button(key="repay_back").click().run()
    _ok(at)
    assert at.radio(key=f"repay_choice_{app['id']}") and H.rows(penv["conn"], "repayments") == []


def test_vendor_history_shows_the_status_and_due_date_read_only(penv):
    c, a = penv["conn"], penv["a"]
    app = _approve_days_ago(penv, 0, term=14.0)
    pending = send(penv, a)
    at = _app(user_id=penv["vendor"]["id"], page="history")
    _ok(at)
    text = _text(at)
    due = ui.date_only(SS.lender_application(c, a, app["id"])["repayment"]["due_date"])
    assert "<th>Repayment</th>" in text and ui.pill("Repaying") in text and f"Due {due}" in text
    SS.record_repayment(c, a, app["id"], "repaid_on_time")
    at = _app(user_id=penv["vendor"]["id"], page="history")
    text = _text(at)
    assert ui.pill("Repaid on time") in text and pending["ref"] in text
    assert not [b for b in at.button if b.key and ("rec" in b.key or "repay" in b.key)]           # read-only
    assert service.list_applications(c, penv["vendor"]["id"])[0]["repayment"] is None             # pending: none
    with pytest.raises(auth.AccessDenied):
        SS.record_repayment(c, penv["vendor"], app["id"], "repaid_late")


def test_admin_overview_outcomes_card_and_export_button(penv):
    c, a = penv["conn"], penv["a"]
    for status in ("repaid_on_time", "repaid_late"):
        SS.record_repayment(c, a, _approve_days_ago(penv, 3)["id"], status)
    _approve_days_ago(penv, 1)
    at = _app(user_id=penv["admin"]["id"], page="admin")
    _ok(at)
    text = _text(at)
    assert "Outcomes recorded" in text and "Repayment outcomes" in text
    for label, n in (("Repaying", 1), ("Repaid on time", 1), ("Repaid late", 1), ("Defaulted", 0)):
        assert f'<span class="rsum-n">{n}</span>{ui.pill(label)}' in text, label
    btn = at.get("download_button")
    assert len(btn) == 1 and btn[0].proto.label == "Export outcomes (CSV)" and not btn[0].proto.disabled
    assert not rows(c, "outcomes_exported")                     # rendering the page exports nothing
    # what the button runs on click: the CSV for this admin, and its audit row
    data = __import__("app.pages.admin", fromlist=["x"])._export_csv(penv["admin"]["id"])()
    assert data.decode().splitlines()[0] == ",".join(SS.EXPORT_COLUMNS) and len(data.decode().splitlines()) == 3
    assert [r["detail"] for r in rows(c, "outcomes_exported")] == ["rows=2"]
