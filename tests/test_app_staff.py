"""Lender and admin: roles and permissions, decisions, admin actions (app/staff_service.py), and their screens.

The service tests run on SQLite and, with DATABASE_URL pointing at PostgreSQL, on PostgreSQL too (marked `postgres`).
The screens are tested on SQLite through AppTest. Applications are stored through service._insert_application with a
hand-made snapshot of the same shape as service.snapshot(), so no model is needed.
"""
import logging
from html import escape
import re
from datetime import timedelta

import pytest
from sqlalchemy import insert, select, update
from streamlit.testing.v1 import AppTest

import app_helpers as H
from app import auth, components as ui, db, errors, service, staff_service as SS
from app.db import applications, audit_log, score_checks, users
from app.pages import admin as admin_page, lender as lender_page

PW = "correct-horse-1"
MAIN = str(H.ROOT / "app" / "main.py")
VENDOR_PAGES = ("home", "score", "result", "reasons", "apply", "history", "profile", "sent")
LENDER_PAGES = ("lender", "lender_decided", "lender_review", "lender_profile")
ADMIN_PAGES = ("admin", "admin_users", "admin_add", "admin_audit", "admin_profile")
PAGES_OF = {"vendor": VENDOR_PAGES, "lender": LENDER_PAGES, "admin": ADMIN_PAGES}
VENDOR_NAME = "Wanjiku Kamau"
SECRET_NOTE = "Repay on Fridays at the branch"


def snap(score=640, tier="Moderate risk", amount=5000.0, term=14.0, max_amount=9000, band="comfortable"):
    labels = ("Good", "Fair", "Weak", "Strong", "Good", "Fair", "Good")
    return {"score": score, "tier": tier, "pd": 0.123,
            "pillars": [{"name": n, "rating": 3, "label": l} for n, l in zip(service.PILLAR_NAMES.values(), labels)],
            "reasons": [{"phrase": "Steady weekly income", "direction": "Lowers risk"},
                        {"phrase": "Frequent Fuliza use", "direction": "Raises risk"}],
            "data_notes": [], "request": {"amount": amount, "term_days": term}, "affordability": {"band": band},
            "eligibility": {"max_amount": max_amount, "comfortable_amount": 6000 if max_amount else max_amount}}


def setup_accounts(conn) -> dict:
    vendor = service.register_vendor(conn, VENDOR_NAME, "vendor@example.test", PW, PW)
    a = auth.get_user(conn, auth.create_user(conn, "umoja@example.test", "Umoja desk", PW, "lender", org_name="Umoja SACCO"))
    b = auth.get_user(conn, auth.create_user(conn, "tumaini@example.test", "Tumaini desk", PW, "lender",
                                             org_name="Tumaini Microfinance"))
    adm = auth.get_user(conn, auth.create_user(conn, "admin@example.test", "Platform admin", PW, "admin"))
    return {"conn": conn, "vendor": vendor, "a": a, "b": b, "admin": adm}


def send(env, lender, s=None, vendor=None):
    return service._insert_application(env["conn"], vendor or env["vendor"], lender, s or snap())


def app_row(conn, app_id):
    return db.one(conn, select(applications).where(applications.c.id == app_id))


def audit_rows(conn, action):
    return db.all_rows(conn, select(audit_log).where(audit_log.c.action == action).order_by(audit_log.c.id))


# ================================================================ service (SQLite, and PostgreSQL when available)
@pytest.fixture(params=H.BACKENDS)
def env(request, tmp_path):
    with H.database(request.param, tmp_path) as engine:
        conn = db.connect(engine)
        e = setup_accounts(conn)
        e["engine"] = engine
        yield e
        conn.close()


def test_each_role_is_refused_every_call_of_the_other_roles(env):
    c, v, a, adm = env["conn"], env["vendor"], env["a"], env["admin"]
    app = send(env, a)
    lender_calls = [lambda u: SS.lender_applications(c, u), lambda u: SS.lender_application(c, u, app["id"]),
                    lambda u: SS.decide_application(c, u, app["id"], "approved")]
    admin_calls = [lambda u: SS.admin_overview(c, u), lambda u: SS.list_users(c, u),
                   lambda u: SS.create_staff_user(c, u, "new@example.test", "lender", "New SACCO"),
                   lambda u: SS.set_user_active(c, u, v["id"], False), lambda u: SS.unlock_user(c, u, v["id"]),
                   lambda u: SS.audit_page(c, u)]
    vendor_calls = [lambda u: service.run_score_check(c, u, b"x", "s.csv"),
                    lambda u: service.submit_application(c, u, a["id"], 1, 5000, 14, True)]
    for user, calls in ((v, lender_calls + admin_calls), (a, admin_calls + vendor_calls),
                        (adm, lender_calls + vendor_calls), (None, lender_calls + admin_calls)):
        for call in calls:
            with pytest.raises(auth.AccessDenied):
                call(user)
    assert app_row(c, app["id"])["status"] == "pending"
    assert db.count(c, "users") == 4 and not audit_rows(c, "user_created") and not audit_rows(c, "user_disabled")
    auth.set_active(c, a["id"], False)                                   # a disabled lender is refused too
    with pytest.raises(auth.AccessDenied):
        SS.lender_applications(c, auth.get_user(c, a["id"]))


def test_a_lender_sees_and_decides_only_their_own_applications(env):
    c, a, b = env["conn"], env["a"], env["b"]
    mine = [send(env, a), send(env, a)]
    theirs = send(env, b)
    assert [x["id"] for x in SS.lender_applications(c, a)] == [m["id"] for m in reversed(mine)]   # newest first
    assert [x["id"] for x in SS.lender_applications(c, b)] == [theirs["id"]]
    for call in (lambda: SS.lender_application(c, a, theirs["id"]),
                 lambda: SS.decide_application(c, a, theirs["id"], "approved", "note"),
                 lambda: SS.lender_application(c, a, 99999), lambda: SS.lender_application(c, a, "x")):
        with pytest.raises(auth.AccessDenied, match=SS.NOT_AVAILABLE):  # the same message: existence is not revealed
            call()
    row = app_row(c, theirs["id"])
    assert row["status"] == "pending" and row["lender_note"] is None and row["decided_at"] is None
    assert not audit_rows(c, "application_approved")


def test_a_lender_gets_the_snapshot_and_the_vendor_name_only(env):
    c, a = env["conn"], env["a"]
    with db.transaction(c):                                   # a saved check of the vendor that was never shared
        c.execute(insert(score_checks).values(
            user_id=env["vendor"]["id"], created_at=db.utcnow(), score=777, pd=0.01, tier="Low risk", pillars_json="[]",
            reasons_json="[]", data_notes_json="[]", request_amount=1.0, request_term=1.0, monthly_income=123456.0,
            affordability_band="comfortable", rows_read=1, max_amount=1.0, comfortable_amount=1.0))
    sent = send(env, a)
    row = SS.lender_application(c, a, sent["id"])
    assert row["vendor"] == VENDOR_NAME and row["snapshot"] == snap() and row["ref"] == sent["ref"]
    text = repr(SS.lender_applications(c, a)) + repr(row)
    assert "vendor@example.test" not in text and "777" not in text and "123456" not in text


def test_approve_and_decline_only_from_pending_once_with_an_audit_row(env):
    c, a = env["conn"], env["a"]
    one, two = send(env, a), send(env, a)
    done = SS.decide_application(c, a, one["id"], "approved", f"  {SECRET_NOTE}  ", now=1_800_000_000)
    assert done["status"] == "approved" and done["lender_note"] == SECRET_NOTE and done["decided_at"]
    before = app_row(c, one["id"])
    for decision in ("approved", "declined"):                       # a double click or a second tab
        with pytest.raises(SS.DecisionError, match="already been decided"):
            SS.decide_application(c, a, one["id"], decision, "changed my mind")
    assert app_row(c, one["id"]) == before
    SS.decide_application(c, a, two["id"], "declined", "")
    assert app_row(c, two["id"])["status"] == "declined" and app_row(c, two["id"])["lender_note"] is None
    approved, declined = audit_rows(c, "application_approved"), audit_rows(c, "application_declined")
    assert [(r["actor_id"], r["target"], r["detail"]) for r in approved] == [(a["id"], one["ref"], None)]
    assert [(r["actor_id"], r["target"]) for r in declined] == [(a["id"], two["ref"])]
    assert SECRET_NOTE not in H.all_text(c).replace(app_row(c, one["id"])["lender_note"], "", 1)   # only in its row
    with pytest.raises(ValueError):
        SS.decide_application(c, a, two["id"], "counter-offer")
    with pytest.raises(SS.DecisionError, match="under 500"):
        SS.decide_application(c, a, send(env, a)["id"], "approved", "x" * 501)


def test_two_tabs_deciding_at_the_same_moment_decide_once(env, monkeypatch):
    """Both tabs read the application as pending; the second UPDATE finds it decided and changes nothing."""
    c, a = env["conn"], env["a"]
    sent = send(env, a)
    stale = SS.lender_application(c, a, sent["id"])                 # what the second tab read before the first decided
    c2 = db.connect(env["engine"])
    try:
        SS.decide_application(c, a, sent["id"], "approved", "first")
        monkeypatch.setattr(SS, "lender_application", lambda *args, **kw: stale)
        with pytest.raises(SS.DecisionError):
            SS.decide_application(c2, a, sent["id"], "declined", "second")
    finally:
        c2.close()
    row = app_row(c, sent["id"])
    assert row["status"] == "approved" and row["lender_note"] == "first" and len(audit_rows(c, "application_approved")) == 1
    assert not audit_rows(c, "application_declined")


def test_the_decision_and_note_reach_the_vendor(env):
    c, a = env["conn"], env["a"]
    sent = send(env, a)
    SS.decide_application(c, a, sent["id"], "declined", SECRET_NOTE)
    mine = service.list_applications(c, env["vendor"]["id"])
    assert [(x["ref"], x["status"], x["lender_note"]) for x in mine] == [(sent["ref"], "declined", SECRET_NOTE)]


def test_an_admin_never_reads_snapshots_notes_names_or_amounts(env):
    c, a, adm = env["conn"], env["a"], env["admin"]
    sent = send(env, a, snap(amount=7350.0, max_amount=9100))
    SS.decide_application(c, a, sent["id"], "declined", SECRET_NOTE)
    out = repr(SS.admin_overview(c, adm)) + repr(SS.list_users(c, adm)) + repr(SS.audit_page(c, adm))
    for leak in (VENDOR_NAME, SECRET_NOTE, "7350", "7,350", "9100", "9,100", "Steady weekly income", "snapshot", "KES"):
        assert leak not in out, leak
    assert f"Declined application {sent['ref']}" in out and f"Sent application {sent['ref']}" in out
    with pytest.raises(auth.AccessDenied):
        SS.lender_application(c, adm, sent["id"])


def test_admin_creates_a_lender_and_an_admin_with_a_one_time_password(env, caplog):
    c, adm = env["conn"], env["admin"]
    caplog.set_level(logging.DEBUG)
    new_lender, pw1 = SS.create_staff_user(c, adm, "Desk@Example.test", "lender", "  Imara   SACCO ")
    new_admin, pw2 = SS.create_staff_user(c, adm, "ops@example.test", "admin", "ignored for admins")
    assert (new_lender["role"], new_lender["org_name"], new_lender["email"]) == ("lender", "Imara SACCO", "desk@example.test")
    assert (new_admin["role"], new_admin["org_name"]) == ("admin", None)
    assert pw1 != pw2 and min(len(pw1), len(pw2)) >= 20
    assert auth.authenticate(c, "desk@example.test", pw1)["id"] == new_lender["id"]
    assert auth.authenticate(c, "ops@example.test", pw2)["role"] == "admin"
    everything = H.all_text(c) + "\n".join(r["password_hash"] + r["salt"] for r in H.rows(c, "users"))
    assert pw1 not in everything and pw2 not in everything                      # only the scrypt hash is stored
    assert not [r for r in caplog.records if pw1 in r.getMessage() or pw2 in r.getMessage()]
    assert [(r["actor_id"], r["detail"]) for r in audit_rows(c, "user_created")] == [(adm["id"], "lender"), (adm["id"], "admin")]
    assert "Imara SACCO" in {x["org_name"] for x in service.list_lenders(c)}
    for args, message in ((("x@example.test", "vendor", None), "Vendors create their own"),
                          (("x@example.test", "lender", "  "), "organisation"),
                          (("x@example.test", "lender", "umoja sacco"), "already has a lender account"),
                          (("umoja@example.test", "admin", None), "already exists"),
                          (("not-an-email", "admin", None), "valid email")):
        with pytest.raises((service.UserError, auth.AuthError), match=message):
            SS.create_staff_user(c, adm, *args)
    assert len(audit_rows(c, "user_created")) == 2


def test_disable_enable_and_the_self_disable_guard(env):
    c, a, adm = env["conn"], env["a"], env["admin"]
    with pytest.raises(service.UserError, match="your own account"):
        SS.set_user_active(c, adm, adm["id"], False)
    assert auth.get_user(c, adm["id"])["is_active"]
    SS.set_user_active(c, adm, a["id"], False)
    assert {u["id"]: u["status"] for u in SS.list_users(c, adm)}[a["id"]] == "disabled"
    with pytest.raises(auth.AuthError):
        auth.authenticate(c, "umoja@example.test", PW)
    SS.set_user_active(c, adm, a["id"], True)
    assert auth.authenticate(c, "umoja@example.test", PW)["id"] == a["id"]
    assert [r["target"] for r in audit_rows(c, "user_disabled")] == [f"user:{a['id']}"]
    assert [r["target"] for r in audit_rows(c, "user_enabled")] == [f"user:{a['id']}"]
    with pytest.raises(service.UserError):
        SS.set_user_active(c, adm, 99999, False)


def test_unlock_ends_a_sign_in_lock(env):
    c, adm, v = env["conn"], env["admin"], env["vendor"]
    t = db.utcnow().timestamp()
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth.AuthError):
            service.authenticate(c, "vendor@example.test", "wrong-password-0", now=t)
    row = {u["id"]: u for u in SS.list_users(c, adm, now=t)}[v["id"]]
    assert row["status"] == "locked" and row["minutes"] == 10
    SS.unlock_user(c, adm, v["id"], now=t)
    assert {u["id"]: u["status"] for u in SS.list_users(c, adm, now=t)}[v["id"]] == "active"
    assert service.authenticate(c, "vendor@example.test", PW, now=t)["id"] == v["id"]
    assert [r["target"] for r in audit_rows(c, "user_unlocked")] == [f"user:{v['id']}"]


def test_audit_log_in_plain_language_newest_first_50_per_page(env):
    c, adm, a, v = env["conn"], env["admin"], env["a"], env["vendor"]
    t = db.utcnow().timestamp() - 10_000
    for i in range(110):
        db.audit(c, "score_check", actor_id=v["id"], target="check:1" if i % 2 else "not_saved", now=t + i)
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth.AuthError):
            service.authenticate(c, "umoja@example.test", "wrong-password-0")
    sent = send(env, a)
    SS.decide_application(c, a, sent["id"], "approved")
    SS.unlock_user(c, adm, a["id"])
    first = SS.audit_page(c, adm, 0)
    whats = [r["what"] for r in first["rows"]]
    assert len(first["rows"]) == 50 and first["has_next"]
    assert whats[:4] == [f"Unlocked umoja@example.test", f"Approved application {sent['ref']}",
                         f"Sent application {sent['ref']}", "Failed sign-in (5th), account locked"]
    assert whats[4] == "Failed sign-in" and first["rows"][0]["who"] == "admin@example.test"
    assert first["rows"][2]["who"] == "vendor@example.test"
    total = db.count(c, "audit_log")
    pages = [SS.audit_page(c, adm, p) for p in range(5)]
    assert sum(len(p["rows"]) for p in pages) == total and not pages[-1]["rows"]
    assert {"Ran a score check", "Ran a score check (not saved)"} <= {r["what"] for p in pages for r in p["rows"]}
    when = [r["when"] for p in pages for r in p["rows"]]
    assert when == sorted(when, reverse=True)                                 # newest first across the pages
    assert SS.describe("application_refused", None, "above_limit", None) == "Application not sent: above the estimated limit"
    assert SS.describe("something_new", "x", "y", None) == "Other action"


def test_overview_counts_only_what_is_recorded(env):
    c, adm, v, a = env["conn"], env["admin"], env["vendor"], env["a"]
    now = db.utcnow().timestamp()
    for days in (1, 2, 6, 8, 40):
        db.audit(c, "score_check", actor_id=v["id"], target="not_saved", now=now - days * 86400)
    for days, tier in ((1, "Low risk"), (3, "Low risk"), (5, "High risk"), (10, "Very high risk"), (45, "Moderate risk")):
        with db.transaction(c):
            c.execute(insert(score_checks).values(
                user_id=v["id"], created_at=db.utcnow(now - days * 86400), score=600, pd=0.1, tier=tier,
                pillars_json="[]", reasons_json="[]", data_notes_json="[]", request_amount=1.0, request_term=1.0,
                affordability_band="unknown", rows_read=1))
    first, _ = send(env, a), send(env, a)
    SS.decide_application(c, a, first["id"], "approved")
    for days, code in ((1, "file_type"), (3, "unreadable"), (9, "too_large")):
        db.audit(c, "upload_rejected", actor_id=v["id"], detail=code, now=now - days * 86400)
    o = SS.admin_overview(c, adm, now=now)
    assert o["scores_7d"] == 3 and o["applications"] == 2 and o["decided"] == 1 and o["uploads_rejected"] == 2
    assert o["tiers_30d"] == {"Low risk": 2, "Moderate risk": 0, "High risk": 1, "Very high risk": 1}
    assert "warnings_seen" not in o and o["model"]


def test_a_rejected_upload_writes_an_audit_row_with_a_fixed_reason_only(env):
    c, v = env["conn"], env["vendor"]
    for data, name, code in ((b"not a statement", "notes.txt", "file_type"), (b"", "empty.csv", "empty"),
                             (b"a,b\n1,2\n", "secret-shop-name.csv", None)):
        with pytest.raises(service.UserError):
            service.run_score_check(c, v, data, filename=name)
    rows = [r for r in H.rows(c, "audit_log") if r["action"] == "upload_rejected"]
    assert [r["detail"] for r in rows][:2] == ["file_type", "empty"]
    assert all(r["detail"] in service.UPLOAD_REJECT_CODES.values() for r in rows)
    assert all(r["actor_id"] == v["id"] and r["target"] is None for r in rows)
    assert "secret-shop-name" not in H.all_text(c) and "notes.txt" not in H.all_text(c)
    described = SS.describe("upload_rejected", None, "file_type", None)
    assert described == "Upload rejected: not an Excel, CSV or PDF file"


# ================================================================ screens (SQLite, AppTest)
@pytest.fixture
def penv(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODEL_PATH", str(tmp_path / "missing" / "logistic.joblib"))   # nothing to warm up
    monkeypatch.setenv("APP_REFERENCE_PATH", str(tmp_path / "missing" / "reference.json"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    url = db.database_url()
    conn = db.connect()
    e = setup_accounts(conn)
    yield e
    conn.close()
    engine = db._ENGINES.pop(url, None)
    if engine is not None:
        engine.dispose()


def _app(**state) -> AppTest:
    at = AppTest.from_file(MAIN, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


DATA_URI = re.compile(r"data:image/[a-z+]+;base64,[A-Za-z0-9+/=]+")     # the embedded logo: not screen text


def _text(at) -> str:
    parts = [m.value for m in at.markdown if "<style>" not in m.value]
    parts += [b.label for b in at.button] + [e.label for e in at.expander]
    parts += [w.label for w in (*at.text_input, *at.text_area, *at.toggle, *at.radio)] + [c.value for c in at.code]
    return DATA_URI.sub("data:image", "\n".join(parts))


def _ok(at):
    assert not at.exception, [e.value for e in at.exception]


def _keys(at, prefix):
    return [b.key for b in at.button if b.key and b.key.startswith(prefix)]


def _sign_in(email):
    at = _app()
    at.text_input(key="signin_email").input(email)
    at.text_input(key="signin_password").input(PW)
    return at.button(key="signin_submit").click().run()


def test_every_page_refuses_the_other_roles(penv):
    sent = send(penv, penv["a"])
    for role, user in (("vendor", penv["vendor"]), ("lender", penv["a"]), ("admin", penv["admin"])):
        for other, pages in PAGES_OF.items():
            if other == role:
                continue
            for page in pages:
                at = _app(user_id=user["id"], page=page, review_id=sent["id"], sent={"ref": "A-1", "lender": "x",
                                                                                     "status": "pending"})
                _ok(at)
                text = _text(at)
                assert "Not available" in text and f"This page is for {other}s only." in text, (role, page)
                assert not [b for b in at.button if b.key != "go_home"], (role, page)          # nothing else
                assert VENDOR_NAME not in text and "Steady weekly income" not in text and "@example.test" not in text


def test_each_role_lands_on_its_home_with_its_own_sidebar(penv):
    expect = {"vendor@example.test": ("home", ["sidenav_home", "sidenav_score", "sidenav_history", "sidenav_profile"]),
              "umoja@example.test": ("lender", ["sidenav_queue", "sidenav_decided", "sidenav_lprofile"]),
              "admin@example.test": ("admin", ["sidenav_overview", "sidenav_users", "sidenav_audit", "sidenav_aprofile"])}
    for email, (home, nav) in expect.items():
        at = _sign_in(email)
        _ok(at)
        assert at.session_state["page"] == home and _keys(at, "sidenav_") == nav, email
        assert [k.replace("side", "") for k in nav] == _keys(at, "nav_")               # the same list in the tab bar


@pytest.mark.parametrize("who, page, label, side_label", [
    ("vendor", "home", "Vendor", "Vendor account"), ("a", "lender", "Lender · Umoja SACCO", "Lender account"),
    ("admin", "admin", "Administrator", "Admin account")])
def test_each_shell_shows_the_account_type_under_the_name(penv, who, page, label, side_label):
    user = penv[who]
    at = _app(user_id=user["id"], page=page)
    _ok(at)
    side = (f'<span class="side-name">{escape(user["name"])}</span>'
            f'<span class="side-role">{escape(side_label)}</span>')
    assert side in _text(at)                                                   # laptop sidebar: "<Role> account"
    assert f'<span class="avatar" aria-hidden="true">{escape(ui.initials(user["name"]))}</span>' in _text(at)
    assert ui.account_label(user) == side_label and ui.role_label(user) == label
    assert at.button(key="side_signout").label == "Sign out"                  # the icon button's accessible name
    assert '<div class="cap side-menu-cap">Menu</div>' in _text(at)
    at.button(key="topbar_menu").click().run()
    menu = f'<span class="menu-name">{escape(user["name"])}</span><span class="menu-role">{escape(label)}</span>'
    assert menu in _text(at)                                                   # phone menu


def test_register_lender_rules(penv):
    c = penv["conn"]
    new = service.register_lender(c, "Imara Desk", "imara@example.test", "  Imara \t SACCO  ", PW, PW)
    assert (new["role"], new["org_name"], new["is_active"]) == ("lender", "Imara SACCO", True)
    for org, message in (("imara sacco", service.ORG_TAKEN), (" UMOJA  SACCO", service.ORG_TAKEN), ("", service.ORG_MISSING),
                         ("x", service.ORG_LENGTH), ("x" * 81, service.ORG_LENGTH)):
        with pytest.raises(auth.AuthError, match=message):
            service.register_lender(c, "Other Desk", "other@example.test", org, PW, PW)
    assert auth.find_user_id(c, "other@example.test") is None
    assert service.register_lender(c, "Long Desk", "long@example.test", "y" * 80, PW, PW)["org_name"] == "y" * 80
    assert service.register_lender(c, "Two Desk", "two@example.test", "Ab", PW, PW)["org_name"] == "Ab"
    # the admin's Add a lender uses the same rule, so it refuses a self-registered organisation too
    with pytest.raises(service.UserError, match=service.ORG_TAKEN):
        SS.create_staff_user(c, penv["admin"], "imara2@example.test", "lender", "IMARA sacco")
    lenders = {r["org_name"] for r in service.list_lenders(c)}
    assert {"Imara SACCO", "Umoja SACCO"} <= lenders                    # self-registered lenders are on the Apply list
    rows = SS.audit_page(c, penv["admin"])["rows"]
    assert "Created a lender account" in [r["what"] for r in rows]


def test_a_lender_without_an_organisation_is_labelled_lender():
    assert ui.role_label({"role": "lender", "org_name": None}) == "Lender"


@pytest.mark.parametrize("role, labels", [("vendor", ["Home", "Check score", "History", "Profile"]),
                                          ("lender", ["Queue", "Decided", "Profile"]),
                                          ("admin", ["Overview", "Users", "Audit", "Profile"])])
def test_every_role_has_the_nav_items_of_the_design(penv, role, labels):
    assert [n.label for n in ui.NAV_FOR[role]] == labels
    user = {"vendor": penv["vendor"], "lender": penv["a"], "admin": penv["admin"]}[role]
    at = _app(user_id=user["id"], page=ui.NAV_FOR[role][0].page)
    _ok(at)
    assert [b.label for b in at.button if b.key.startswith("sidenav_")] == labels
    for item in ui.NAV_FOR[role]:                                             # every entry opens its page, in the guard
        at.button(key=f"sidenav_{item.key}").click().run()
        _ok(at)
        assert at.session_state["page"] == item.page and "Not available" not in _text(at), item


def test_admin_profile_changes_the_password(penv):
    adm = penv["admin"]
    at = _app(user_id=adm["id"], page="admin_profile")
    _ok(at)
    text = _text(at)
    assert "admin@example.test" in text and '<div class="cap">Security</div>' in text and not at.toggle
    at.text_input(key="pw_current").input(PW)
    at.text_input(key="pw_new").input("a-new-admin-pass-1")
    at.text_input(key="pw_confirm").input("a-new-admin-pass-1")
    at.button(key="pw_save").click().run()
    _ok(at)
    assert "Password changed." in _text(at)
    assert auth.authenticate(penv["conn"], "admin@example.test", "a-new-admin-pass-1")["role"] == "admin"


def test_the_phone_menu_lists_the_role_items(penv):
    for user, labels in ((penv["a"], ["Queue", "Decided", "Profile", "Sign out"]),
                         (penv["admin"], ["Overview", "Users", "Audit", "Profile", "Sign out"])):
        at = _app(user_id=user["id"], page=ui.NAV_FOR[user["role"]][0].page)
        at.button(key="topbar_menu").click().run()
        assert [b.label for b in at.button if b.key.startswith("menu_")] == labels
    at.button(key="menu_audit").click().run()
    assert at.session_state["page"] == "admin_audit"


@pytest.mark.parametrize("n", [0, 1, 12])
def test_lender_queue_and_decided_with_zero_one_and_many(penv, n):
    a = penv["a"]
    sent = [send(penv, a, snap(score=560 + i, tier=("Low risk", "Moderate risk", "High risk", "Very high risk")[i % 4],
                               max_amount=(9000, 0, None)[i % 3])) for i in range(n)]
    for i, s in enumerate(sent[:max(0, n - 3)]):
        if i % 2:
            SS.decide_application(penv["conn"], a, s["id"], "approved" if i % 4 == 1 else "declined", "ok")
    send(penv, penv["b"])                                                      # another organisation's application
    apps = SS.lender_applications(penv["conn"], a)
    count = {s: len([x for x in apps if x["status"] == s]) for s in ("pending", "approved", "declined")}
    decided = count["approved"] + count["declined"]
    chips_of = {"lender": [f"Pending {count['pending']}", f"All {n}"],
                "lender_decided": [f"All decided {decided}", f"Approved {count['approved']}",
                                   f"Declined {count['declined']}", f"Awaiting outcome {count['approved']}"]}
    for page, default in (("lender", ("pending",)), ("lender_decided", ("approved", "declined"))):
        at = _app(user_id=a["id"], page=page)
        _ok(at)
        text = _text(at)
        assert "Applications" in text and f"Umoja SACCO · {'Queue' if page == 'lender' else 'Decided'}" in text
        assert at.pills(key=f"{page}_filter").options == chips_of[page]
        rows = [x for x in apps if x["status"] in default]
        assert _keys(at, "open_") == [f"open_{x['id']}" for x in rows]           # laptop table rows
        assert _keys(at, "popen_") == [f"popen_{x['id']}" for x in rows]         # phone rows, same data
        assert "Tumaini" not in text
        if n == 0:
            assert "No applications yet." in text
        for x in rows:
            assert x["ref"] in text and VENDOR_NAME in text
    at = _app(user_id=a["id"], page="lender")
    at.session_state["lender_filter"] = "all"
    at.run()
    assert _keys(at, "open_") == [f"open_{x['id']}" for x in apps]
    at = _app(user_id=a["id"], page="lender_decided")
    at.session_state["lender_decided_filter"] = "approved"
    at.run()
    assert _keys(at, "open_") == [f"open_{x['id']}" for x in apps if x["status"] == "approved"]
    if n:
        text = _text(_app(user_id=a["id"], page="lender"))
        assert "KES 5,000 · 14 days" in text and ui.pill("Pending") in text
        assert f'<span class="avatar sm" aria-hidden="true">{ui.initials(VENDOR_NAME)}</span>' in text   # vendor avatar
        for tier in ("Low", "Moderate", "High", "Very high")[:min(n, 4)]:
            if any(ui.tier_word(x["tier"]) == tier and x["status"] == "pending" for x in apps):
                assert ui.pill(tier, ui.status_kind(tier)) in text


def test_lender_reviews_and_decides_once(penv):
    a, c = penv["a"], penv["conn"]
    sent = send(penv, a)
    at = _app(user_id=a["id"], page="lender")
    at.button(key=f"open_{sent['id']}").click().run()
    _ok(at)
    assert at.session_state["page"] == "lender_review"
    text = _text(at)
    assert "Review application" in text and f"{sent['ref']} · Umoja SACCO" in text
    assert at.button(key="back_queue").label == "Back to queue"
    for part in ("Application", VENDOR_NAME, "KES 5,000 · 14 days", "Request compared with monthly income",
                 ui.pill("Comfortable"), "Up to KES 9,000", '<div class="hero-score">640', "Estimated default risk 12.3%",
                 ui.pill("Moderate risk", "brand"), '<div class="cap">What the model weighed</div>',
                 ui.pill("Raises risk"), ui.pill("Lowers risk"), escape(lender_page.SUMMARY_ONLY)):
        assert part in text, part
    assert lender_page.SUMMARY_ONLY == ("You see this summary only. The statement is never shared. "
                                        "Decisions are final.")
    assert len(re.findall(r'<div class="tile">', text)) == 7
    assert at.button(key="approve").label == "Approve" and at.button(key="decline").label == "Decline"
    at.text_area(key=f"note_{sent['id']}").input(SECRET_NOTE)
    at.button(key="approve").click().run()
    _ok(at)
    text = _text(at)
    assert app_row(c, sent["id"])["status"] == "approved" and app_row(c, sent["id"])["lender_note"] == SECRET_NOTE
    assert ui.pill("Approved") in text and SECRET_NOTE in text and "final" in text
    assert not _keys(at, "approve") and not _keys(at, "decline") and not at.text_area   # read-only now
    at.session_state[lender_page.INTENT] = (sent["id"], "declined")           # a second click that was already queued
    at.run()
    assert SS.ALREADY_DECIDED in _text(at) and app_row(c, sent["id"])["status"] == "approved"
    assert len(audit_rows(c, "application_approved")) == 1 and not audit_rows(c, "application_declined")
    at.button(key="back_queue").click().run()
    assert at.session_state["page"] == "lender"


def test_a_declined_note_reaches_the_vendor_history(penv):
    sent = send(penv, penv["a"])
    at = _app(user_id=penv["a"]["id"], page="lender_review", review_id=sent["id"])
    at.text_area(key=f"note_{sent['id']}").input(SECRET_NOTE)
    at.button(key="decline").click().run()
    _ok(at)
    vt = _text(_app(user_id=penv["vendor"]["id"], page="history"))
    assert ui.pill("Declined") in vt and SECRET_NOTE in vt
    home = _app(user_id=penv["vendor"]["id"], page="home")
    _ok(home)


def test_a_lender_cannot_open_another_organisations_application(penv):
    theirs = send(penv, penv["b"])
    at = _app(user_id=penv["a"]["id"], page="lender_review", review_id=theirs["id"])
    _ok(at)
    text = _text(at)
    assert "Not available" in text and SS.NOT_AVAILABLE in text
    assert VENDOR_NAME not in text and theirs["ref"] not in text and not _keys(at, "approve")
    at.session_state[lender_page.INTENT] = (theirs["id"], "approved")         # a forged decision changes nothing
    at.run()
    assert app_row(penv["conn"], theirs["id"])["status"] == "pending"


def test_lender_profile(penv):
    at = _app(user_id=penv["a"]["id"], page="lender_profile")
    _ok(at)
    text = _text(at)
    assert "Umoja SACCO" in text and "umoja@example.test" in text and at.expander(key="change_password")
    assert not at.toggle                                                        # the vendor settings are not here
    at.button(key="sign_out").click().run()
    assert at.session_state["page"] == "signin" and "user_id" not in at.session_state


@pytest.mark.parametrize("extra", [0, 1, 15])
def test_admin_overview_and_users_with_zero_one_and_many(penv, extra):
    c, adm = penv["conn"], penv["admin"]
    for i in range(extra):
        service.register_vendor(c, f"Vendor {i}", f"v{i}@example.test", PW, PW)
    with db.transaction(c):
        c.execute(insert(score_checks).values(
            user_id=penv["vendor"]["id"], created_at=db.utcnow(), score=600, pd=0.1, tier="High risk", pillars_json="[]",
            reasons_json="[]", data_notes_json="[]", request_amount=1.0, request_term=1.0,
            affordability_band="unknown", rows_read=1))
    at = _app(user_id=adm["id"], page="admin")
    _ok(at)
    text = _text(at)
    for part in ("Scores run (7 days)", "Applications sent", "Applications decided", "Uploads rejected",
                 "Scores by risk level", 'aria-label="Scores by risk level: Low 0%, Moderate 0%, High 100%, Very high 0%."',
                 "Trained on simulated data", "Model", "Active model", "Test AUC", "Features"):
        assert part in text, part
    assert "Warnings seen" not in text and "Not tracked yet" not in text
    assert 'class="bar-fill"' in text and "100% · 1" in text                   # horizontal bars, not a donut
    assert "donut" not in text
    at = _app(user_id=adm["id"], page="admin_users")
    _ok(at)
    text = _text(at)
    people = SS.list_users(c, adm)
    assert len(people) == 4 + extra and f"{len(people)} accounts" in text
    for u in people:
        assert u["email"] in text
    assert "This is you" in text and f"disable_{adm['id']}" not in _keys(at, "disable_")
    assert len(_keys(at, "disable_")) == len(people) - 1 and VENDOR_NAME not in text
    assert at.button(key="add_user").label == "Add a lender or admin"


def test_admin_row_actions_disable_enable_unlock(penv):
    c, adm, a, v = penv["conn"], penv["admin"], penv["a"], penv["vendor"]
    at = _app(user_id=adm["id"], page="admin_users")
    at.button(key=f"disable_{a['id']}").click().run()
    _ok(at)
    assert not auth.get_user(c, a["id"])["is_active"] and ui.pill("Disabled", "neutral") in _text(at)
    at.button(key=f"enable_{a['id']}").click().run()
    assert auth.get_user(c, a["id"])["is_active"] and f"disable_{a['id']}" in _keys(at, "disable_")
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        with pytest.raises(auth.AuthError):
            service.authenticate(c, "vendor@example.test", "wrong-password-0")
    at.run()
    assert "Locked for 10 min" in _text(at) or "Locked for 9 min" in _text(at)
    at.button(key=f"unlock_{v['id']}").click().run()
    assert f"disable_{v['id']}" in _keys(at, "disable_") and "Locked for" not in _text(at)
    at.session_state["user_action"] = ("disable", adm["id"])                    # forged: the service refuses it
    at.run()
    assert "You cannot disable your own account." in _text(at) and auth.get_user(c, adm["id"])["is_active"]
    assert [len(audit_rows(c, x)) for x in ("user_disabled", "user_enabled", "user_unlocked")] == [1, 1, 1]


def test_admin_adds_a_lender_and_sees_the_password_once(penv, caplog):
    caplog.set_level(logging.DEBUG)
    c, adm = penv["conn"], penv["admin"]
    at = _app(user_id=adm["id"], page="admin_users")
    at.button(key="add_user").click().run()
    assert at.session_state["page"] == "admin_add"
    picker = at.radio(key="new_role")
    assert picker.label == "Account type: Lender or Admin" and list(picker.options) == ["Lender", "Admin"]
    at.text_input(key="new_email").input("desk@example.test")
    at.radio(key="new_role").set_value("lender")
    at.text_input(key="new_org").input("Imara SACCO")
    at.button(key="create_user").click().run()
    _ok(at)
    assert len(at.code) == 1
    password = at.code[0].value
    assert len(password) >= 20 and auth.authenticate(c, "desk@example.test", password)["role"] == "lender"
    assert "Lender account created for Imara SACCO" in _text(at) and "Admin account created" not in _text(at)
    assert password not in H.all_text(c) and password not in repr(at.session_state.to_dict())
    assert not [r for r in caplog.records if password in r.getMessage()]
    at.run()                                                                   # any later run: gone
    assert not at.code and password not in _text(at)
    at.radio(key="new_role").set_value("admin")
    at.text_input(key="new_email").input("ops@example.test")
    at.button(key="create_user").click().run()
    assert len(at.code) == 1 and auth.get_user(c, auth.find_user_id(c, "ops@example.test"))["role"] == "admin"
    assert "Admin account created" in _text(at) and "Lender account created" not in _text(at)
    at.text_input(key="new_email").input("again@example.test")
    at.radio(key="new_role").set_value("lender")
    at.text_input(key="new_org").input("Umoja SACCO")
    at.button(key="create_user").click().run()
    assert not at.code and "This organisation already has a lender account." in _text(at)


def test_admin_audit_page_paginates_and_shows_no_amounts(penv):
    c, a, adm, v = penv["conn"], penv["a"], penv["admin"], penv["vendor"]
    sent = send(penv, a, snap(amount=7350.0, max_amount=9100))
    SS.decide_application(c, a, sent["id"], "approved", SECRET_NOTE)
    t = db.utcnow().timestamp() - 5000
    for i in range(60):
        db.audit(c, "score_check", actor_id=v["id"], target="not_saved", now=t + i)
    at = _app(user_id=adm["id"], page="admin_audit")
    _ok(at)
    text = _text(at)
    assert f"Approved application {sent['ref']}" in text and "Who" in text and "When" in text
    for leak in ("7350", "7,350", "9100", "9,100", "KES", SECRET_NOTE, VENDOR_NAME, ".csv", "Steady weekly income"):
        assert leak not in text, leak
    assert at.button(key="audit_prev").disabled and not at.button(key="audit_next").disabled
    at.button(key="audit_next").click().run()
    _ok(at)
    assert "page 2" in _text(at) and at.button(key="audit_next").disabled
    at.button(key="audit_prev").click().run()
    assert "page 1" in _text(at)


def test_lender_review_has_no_score_history_chart(penv):
    sent = send(penv, penv["a"])
    send(penv, penv["a"])                                                     # a second application by the same vendor
    at = _app(user_id=penv["a"]["id"], page="lender_review", review_id=sent["id"])
    _ok(at)
    text = _text(at)
    assert '<div class="hero-score">' in text
    for chart in ("hero-chart", "Score over time", "<polyline", "<svg role=\"img\""):
        assert chart not in text, chart


def test_admin_model_card_reads_the_test_auc_from_the_report(penv):
    assert admin_page.test_auc("logistic") == "0.726"                         # docs/model_report.md, results table
    assert admin_page.test_auc("no_such_model") is None


def test_staff_pages_have_no_emoji_and_status_is_never_coloured_text(penv):
    emoji = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
    sent = send(penv, penv["a"])
    for user, pages in ((penv["a"], LENDER_PAGES), (penv["admin"], ADMIN_PAGES)):
        for page in pages:
            at = _app(user_id=user["id"], page=page, review_id=sent["id"])
            _ok(at)
            text = _text(at)
            assert not emoji.search(text), page
            assert 'class="status"' not in text and not re.search(r'class="pill[^"]*" style=', text), page
