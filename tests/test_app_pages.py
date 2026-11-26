"""Web app screens (app/main.py and app/pages/) through streamlit.testing.v1.AppTest.

AppTest cannot drive the file uploader, so the end-to-end test scores the synthetic statement through the service
(exactly what the Score screen calls) and continues in the app from the Result screen.
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import insert
from streamlit.proto.TextInput_pb2 import TextInput as TextInputProto
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.element_tree import Block

import app_helpers as H
import scoring as SC
import toy
from app import auth, components, db, errors, service, theme

PW = "correct-horse-1"
MAIN = str(H.ROOT / "app" / "main.py")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")
VENDOR_PAGES = ("home", "score", "result", "reasons", "apply", "history", "profile")


@pytest.fixture(scope="module")
def models(tmp_path_factory):
    return H.build_app_models(tmp_path_factory.mktemp("app_models"))


@pytest.fixture
def env(models, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODEL_PATH", str(models["model"]))
    monkeypatch.setenv("APP_REFERENCE_PATH", str(models["ref"]))
    monkeypatch.delenv("DATABASE_URL", raising=False)           # the screens are tested on SQLite only
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "app.db"))
    url = db.database_url()
    conn = db.connect()                                          # the same cached engine the app uses for this URL
    vendor = service.register_vendor(conn, "Wanjiku Test", "vendor@example.com", PW, PW)
    lender = auth.get_user(conn, auth.create_user(conn, "umoja@example.com", "Umoja desk", PW, "lender", org_name="Umoja SACCO"))
    auth.create_user(conn, "tumaini@example.com", "Tumaini desk", PW, "lender", org_name="Tumaini Microfinance")
    yield {"conn": conn, "vendor": vendor, "lender": lender}
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
    """Everything the screen shows as text: markdown, button, widget and expander labels (embedded image data
    removed, so a word search never matches inside the logo's base64)."""
    parts = [m.value for m in at.markdown if "<style>" not in m.value]
    parts += [b.label for b in at.button] + [e.label for e in at.expander]
    parts += [w.label for w in (*at.text_input, *at.number_input, *at.slider, *at.checkbox, *at.toggle, *at.radio)]
    return DATA_URI.sub("data:image", "\n".join(parts))


def _no_errors(at):
    assert not at.exception, [e.value for e in at.exception]


def _sign_in(at, email, password):
    at.text_input(key="signin_email").input(email)
    at.text_input(key="signin_password").input(password)
    return at.button(key="signin_submit").click().run()


# ---------------------------------------------------------------- sign in and roles
def _flow(at) -> list:
    """The screen in display order as (type, key) for inputs and buttons and ("markdown", html) for markdown."""
    out = []

    def walk(node):
        if isinstance(node, Block):
            for i in sorted(node.children):
                walk(node.children[i])
        elif node.type == "markdown" and "<style>" not in node.value:
            out.append(("markdown", node.value))
        elif node.type in ("text_input", "button", "button_group"):
            out.append((node.type, node.key))
    walk(at.main)
    return out


def test_sign_in_renders(env):
    at = _app()
    _no_errors(at)
    text = _text(at)
    assert "Welcome back" in text and "Sign in to check your score" in text
    assert '<div class="auth-hint">Vendors, lenders and administrators sign in here.</div>' in text
    assert "auth-pill" not in text                                                   # no account-type pill here
    assert [t.label for t in at.text_input] == ["Email", "Password"]
    assert at.text_input(key="signin_password").proto.type == TextInputProto.PASSWORD   # built-in reveal control
    assert at.button(key="to_signup").label == "New to Nuru? **Create an account**"     # bold part is the indigo link
    assert not [b for b in at.button if b.key.startswith(("nav_", "topbar_"))]     # no tab bar or top bar before sign in


def test_sign_up_renders(env):
    at = _app(page="signup")
    _no_errors(at)
    text = _text(at)
    assert "Create your account" in text and "Takes less than a minute" in text
    assert "auth-pill" not in text and "auth-note" not in text                         # no pill, no staff note
    # "Sign up as": two buttons, Vendor (chosen) and Lender, under the title and above the fields, outside the form
    kind = at.segmented_control(key="signup_type")
    assert kind.label == "Sign up as" and kind.value == "vendor" and not kind.proto.form_id
    assert kind.options == ["Vendor", "Lender"]                                          # no Admin, no other type
    flow = _flow(at)
    title = next(i for i, (t, v) in enumerate(flow) if t == "markdown" and "auth-title" in v)
    assert title < flow.index(("button_group", "signup_type")) < flow.index(("text_input", "signup_name"))
    assert not at.radio and not at.selectbox and len(at.segmented_control) == 1
    assert [t.label for t in at.text_input] == ["Full name", "Email", "Password", "Confirm password"]
    # Lender: the Organisation name field appears (after Email), and goes away again for Vendor
    kind.set_value("lender").run()
    _no_errors(at)
    assert [t.label for t in at.text_input] == ["Full name", "Email", "Organisation name", "Password",
                                                "Confirm password"]
    assert at.text_input(key="signup_org").proto.form_id == "signup_form"
    at.segmented_control(key="signup_type").set_value("vendor").run()
    assert [t.label for t in at.text_input] == ["Full name", "Email", "Password", "Confirm password"]
    assert at.button(key="signup_submit").label == "Create account"
    assert at.button(key="to_signin").label == "Already have an account? **Sign in**"
    assert not [b for b in at.button if b.key.startswith(("nav_", "topbar_"))]


@pytest.mark.parametrize("page, form, submit", [("signin", "signin_form", "signin_submit"),
                                                ("signup", "signup_form", "signup_submit")])
def test_auth_pages_are_forms_so_enter_submits(env, page, form, submit):
    at = _app(page=page)
    button = at.button(key=submit)
    assert button.proto.is_form_submitter and button.proto.form_id == form
    assert all(t.proto.form_id == form for t in at.text_input)                   # every field is in the form
    link = at.button(key="to_signup" if page == "signin" else "to_signin")
    assert not link.proto.form_id                                                  # the link is outside the form


@pytest.mark.parametrize("page", ["signin", "signup"])
def test_auth_pages_have_no_reset_link_demo_shortcut_or_old_copy(env, page):
    at = _app(page=page)
    _no_errors(at)
    text = _text(at)
    for gone in ("Forgot password", "Demo", "580", "simulat", "pillar"):
        assert gone.lower() not in text.lower(), gone
    assert [b.key for b in at.button] == [f"{page}_submit", "to_signup" if page == "signin" else "to_signin"]
    # the shared panel and footer: the Nuru logo (or the text "Nuru" without the file), the headline, the line
    assert components.APP_NAME in text and components.AUTH_HEADLINE == "Credit for the vendors banks overlook"
    assert components.AUTH_HEADLINE in text and components.AUTH_LEAD in text
    assert all(p in text for p in components.AUTH_POINTS) and components.AUTH_FOOTER in text


@pytest.mark.parametrize("page", ["signin", "signup"])
def test_auth_pages_have_no_tilt_and_no_preview(env, page):
    """No rotation or perspective on the auth pages: not in their markup and not in any CSS they load."""
    at = _app(page=page)
    _no_errors(at)
    everything = "\n".join(m.value for m in at.markdown)                           # including the <style> blocks
    assert "<style>" in everything
    for banned in ("perspective(", "rotateY(", "rotateZ(", "tilt-"):
        assert banned not in everything, banned


def _fill_sign_up(at, name, email, password=PW, org=None):
    at.text_input(key="signup_name").input(name)
    at.text_input(key="signup_email").input(email)
    if org is not None:
        at.text_input(key="signup_org").input(org)
    at.text_input(key="signup_password").input(password)
    at.text_input(key="signup_confirm").input(password)
    return at.button(key="signup_submit").click().run()


def test_register_functions_take_no_role():
    import inspect
    for fn in (service.register_vendor, service.register_lender):
        assert "role" not in inspect.signature(fn).parameters, fn.__name__


@pytest.mark.parametrize("forged_type", [None, "admin", "lender_admin", "ADMIN"])
def test_forged_url_or_session_values_cannot_make_a_lender_or_admin(env, forged_type):
    """The account type comes only from the "Sign up as" buttons: role-like session keys and query parameters are
    ignored, and a selector value outside {vendor, lender} is dropped (Vendor is chosen again)."""
    with pytest.raises(TypeError):
        service.register_vendor(env["conn"], "X", "x@example.com", PW, PW, role="admin")
    with pytest.raises(TypeError):
        service.register_lender(env["conn"], "X", "x@example.com", "X Org", PW, PW, role="admin")
    at = AppTest.from_file(MAIN, default_timeout=60)
    forged = {"page": "signup", "role": "admin", "signup_role": "lender", "user_role": "admin", "account_type": "lender",
              "org_name": "Forged SACCO"}
    if forged_type is not None:
        forged["signup_type"] = forged_type
    for key, value in forged.items():
        at.session_state[key] = value
    at.query_params["role"] = "admin"
    at.query_params["type"] = "lender"
    at.query_params["signup_type"] = "admin"
    at.run()
    _no_errors(at)
    assert at.segmented_control(key="signup_type").value == "vendor"
    assert "Organisation name" not in [t.label for t in at.text_input]
    _fill_sign_up(at, "Forged Role", "forged@example.com")
    _no_errors(at)
    user = auth.get_user(env["conn"], auth.find_user_id(env["conn"], "forged@example.com"))
    assert user["role"] == "vendor" and user["org_name"] is None
    assert at.session_state["page"] == "home" and at.session_state["user_id"] == user["id"]
    assert '<span class="side-role">Vendor account</span>' in _text(at)
    assert db.count(env["conn"], "users", role="admin") == 0


def test_vendor_signs_up_then_signs_in_again(env):
    at = _fill_sign_up(_app(page="signup"), "Achieng New", "achieng@example.com")
    _no_errors(at)
    user = auth.get_user(env["conn"], at.session_state["user_id"])
    assert user["role"] == "vendor" and user["is_active"] and at.session_state["page"] == "home"
    at.button(key="side_signout").click().run()
    at = _sign_in(at, "achieng@example.com", PW)
    _no_errors(at)
    assert at.session_state["page"] == "home" and at.session_state["user_id"] == user["id"]


def test_lender_signs_up_lands_on_the_queue_and_signs_in_again(env):
    at = _app(page="signup")
    at.segmented_control(key="signup_type").set_value("lender").run()
    _fill_sign_up(at, "Imara Desk", "imara@example.com", org="  Imara   SACCO ")
    _no_errors(at)
    user = auth.get_user(env["conn"], auth.find_user_id(env["conn"], "imara@example.com"))
    assert user["role"] == "lender" and user["org_name"] == "Imara SACCO" and user["is_active"]   # trimmed, active
    assert at.session_state["page"] == "lender" and at.session_state["user_id"] == user["id"]
    assert '<span class="side-role">Lender account</span>' in _text(at) and "Imara SACCO · Queue" in _text(at)
    last = H.rows(env["conn"], "audit_log")[-1]
    assert (last["action"], last["actor_id"], last["target"]) == ("lender_registered", user["id"], f"user:{user['id']}")
    assert last["detail"] is None                                     # no password, email or organisation in the log
    at.button(key="side_signout").click().run()
    at = _sign_in(at, "imara@example.com", PW)
    _no_errors(at)
    assert at.session_state["page"] == "lender" and "No applications yet." in _text(at)
    assert {"id": user["id"], "org_name": "Imara SACCO"} in service.list_lenders(env["conn"])   # on the Apply list


@pytest.mark.parametrize("org, message", [
    (" umoja   sacco ", service.ORG_TAKEN),                     # another case and spacing of an existing lender
    ("UMOJA SACCO", service.ORG_TAKEN),
    ("   ", service.ORG_MISSING),
    ("X", service.ORG_LENGTH),
])
def test_lender_sign_up_organisation_message_is_shown_under_its_field(env, org, message):
    at = _app(page="signup")
    at.segmented_control(key="signup_type").set_value("lender").run()
    _fill_sign_up(at, "Second Desk", "second@example.com", org=org)
    _no_errors(at)
    assert at.session_state["page"] == "signup" and "user_id" not in at.session_state
    assert auth.find_user_id(env["conn"], "second@example.com") is None
    flow = _flow(at)
    after = flow[flow.index(("text_input", "signup_org")) + 1]
    assert after[0] == "markdown" and 'class="auth-error"' in after[1] and message in after[1], flow


def test_vendor_signs_in_and_reaches_home(env):
    at = _sign_in(_app(), "vendor@example.com", PW)
    _no_errors(at)
    assert at.session_state["page"] == "home" and at.session_state["user_id"] == env["vendor"]["id"]
    text = _text(at)
    # header: greeting with the first name; avatar initials that open Profile (phone view)
    assert re.search(r'role="heading" aria-level="1">Good (morning|afternoon|evening), Wanjiku</div>', text)
    assert at.button(key="topbar_avatar").label == "WT"
    # Home without a score: one friendly card with a Check score button and nothing else
    assert at.button(key="cta_score").label == "Check score"
    for gone in ("Business health", "Latest applications", "Top score drags", "Estimated limit", "Last check"):
        assert gone not in text, gone
    assert not [b for b in at.button if b.key.startswith(("head_", "row_app_", "to_reasons"))]
    # one nav list drives both navigation styles: the tab bar (phone) and the sidebar (laptop)
    assert [b.label for b in at.button if b.key.startswith("nav_")] == ["Home", "Check score", "History", "Profile"]
    assert [b.label for b in at.button if b.key.startswith("sidenav_")] == ["Home", "Check score", "History", "Profile"]
    assert at.button(key="side_signout").label == "Sign out" and "Wanjiku Test" in text


RICH = toy.make_vendor(days=120, daily_in=164000 / 30)       # Low risk under the toy model: eligible up to KES 34,300


def _score(env, user, vendor=None):
    return service.run_score_check(env["conn"], user, H.Upload(H.statement_csv(vendor), "s.csv"))


def _stored_application(env, user, result):
    """An application stored directly (as submit_application stores it), with the snapshot of `result`."""
    lender = {"id": env["lender"]["id"], "org_name": "Umoja SACCO"}
    return service._insert_application(env["conn"], user, lender, service.snapshot(result))


def _score_html(result) -> str:
    return f'<div class="hero-score">{result["score"]}<span class="hero-of">out of 850</span></div>'


def _add_checks(env, user, base, scores):
    """Saved checks with the given scores, one day apart, oldest first (copies of `base` with the PD and tier of each
    score). Faster than scoring a statement once per check."""
    t0 = datetime(2026, 11, 1, 7, 0, tzinfo=timezone.utc)
    el = base["eligibility"]
    with db.transaction(env["conn"]):
        for i, s in enumerate(scores):
            pd_ = float(SC.score_to_pd(s))
            env["conn"].execute(insert(db.score_checks).values(
                user_id=user["id"], created_at=t0 + timedelta(days=i), score=s, pd=pd_, tier=SC.risk_tier(pd_),
                pillars_json=json.dumps(base["pillars"]), reasons_json=json.dumps(base["reasons"]),
                data_notes_json=json.dumps(base["data_notes"]), request_amount=base["request_amount"],
                request_term=base["request_term"], monthly_income=base["monthly_income"],
                affordability_band=base["affordability_band"], rows_read=base["rows_read"],
                max_amount=el["max_amount"], comfortable_amount=el["comfortable_amount"]))


def _chart(text: str) -> str | None:
    m = re.search(r'<div class="hero-chart"><svg role="img" aria-label="Score over time.*?</div></div>', text, re.S)
    return m.group(0) if m else None


def test_home_with_a_score_and_applications(env):
    user, conn = env["vendor"], env["conn"]
    result = _score(env, user)
    sent = [_stored_application(env, user, result) for _ in range(4)]
    at = _app(user_id=user["id"], page="home")                  # no session result: the latest saved check is used
    _no_errors(at)
    text = _text(at)
    assert re.search(r'<div class="cap">Home</div><div class="ph-title" role="heading" aria-level="1">'
                     r'Good (morning|afternoon|evening), Wanjiku</div>', text)
    assert [(b.key, b.label) for b in at.button if b.key.startswith("head_")] == [("head_score", "Check score")]
    # row 1: the hero (score, tier pill, default risk, score over time), the estimated limit and quick actions
    assert '<div class="cap">Your score</div>' in text and _score_html(result) in text
    assert components.pill(result["tier"], "brand") in text
    assert f"Estimated default risk {components.pct(result['pd'])}" in text and _chart(text)
    assert '<div class="cap">Estimated limit</div>' in text
    assert [(b.key, b.label) for b in at.button if b.key.startswith("qa_")] == [
        ("qa_score", "Check score"), ("qa_apply", "Apply"), ("qa_reasons", "Reasons"), ("qa_history", "History")]
    # row 2: the seven tiles in the model's order, each with its rating pill
    assert '<div class="cap">Your financial life</div>' in text and components.tiles(result["pillars"]) in text
    assert re.findall(r'<div class="tile-title">([^<]+)</div>', text) == list(service.PILLAR_NAMES.values())
    # row 3: recent activity, newest first (the 4 applications and the check: 5 rows), with pills
    assert "Recent activity" in text and text.count('<div class="act">') == 5
    assert text.count('<span class="pill pill-moderate">Pending</span>') == 4
    assert f"Application to Umoja SACCO · {sent[-1]['ref']}" in text
    for key, page in (("qa_apply", "apply"), ("qa_reasons", "reasons"), ("qa_history", "history"), ("qa_score", "score")):
        at = _app(user_id=user["id"], page="home")
        at.button(key=key).click().run()
        assert at.session_state["page"] == page, key
    at = _app(user_id=user["id"], page="home")
    at.button(key="latest_all").click().run()
    assert at.session_state["page"] == "history"                 # View all opens History


def test_home_uses_the_session_result_when_checks_are_not_saved(env):
    user = service.update_profile_flags(env["conn"], env["vendor"]["id"], save_results=False)
    result = _score(env, user)
    assert result["check_id"] is None
    at = _app(user_id=user["id"], page="home", result=result)
    _no_errors(at)
    assert "Your financial life" in _text(at) and _score_html(result) in _text(at)
    assert "Score over time, one check" in _text(at)             # the unsaved result is the chart's only point


MENU = ["Home", "Check score", "Apply for a loan", "My applications", "Profile", "Sign out"]


def test_menu_opens_lists_six_items_and_navigates(env):
    at = _app(user_id=env["vendor"]["id"], page="history")
    menu = at.button(key="topbar_menu")
    assert menu.label == "Menu"                                  # its accessible name (the text is hidden visually)
    assert not [b for b in at.button if b.key.startswith("menu_")]                     # closed at first
    menu.click().run()
    _no_errors(at)
    assert [b.label for b in at.button if b.key.startswith("menu_")] == MENU
    for key, page in (("menu_score", "score"), ("menu_apply", "apply"), ("menu_history", "history"),
                      ("menu_profile", "profile"), ("menu_home", "home")):
        at.button(key="topbar_menu").click().run()
        at.button(key=key).click().run()
        _no_errors(at)
        assert at.session_state["page"] == page, key
        assert not [b for b in at.button if b.key.startswith("menu_")]                 # the menu closed
    at.button(key="topbar_menu").click().run()
    at.button(key="menu_signout").click().run()
    assert at.session_state["page"] == "signin" and "user_id" not in at.session_state
    assert "Welcome back" in _text(at)


def test_wrong_password_shows_one_generic_message(env):
    assert auth.SIGN_IN_FAILED == "Email or password is incorrect."                # the message text is unchanged
    for email in ("vendor@example.com", "nobody@example.com"):                     # wrong password, unknown email
        at = _sign_in(_app(), email, "wrong-password")
        _no_errors(at)
        assert auth.SIGN_IN_FAILED in _text(at) and at.session_state["page"] == "signin"
        flow = _flow(at)
        error = flow[flow.index(("button", "signin_submit")) + 1][1]              # red text right under the button
        assert 'class="auth-error" role="alert"' in error and auth.SIGN_IN_FAILED in error
        assert "background" not in error


def test_lockout_message_is_unchanged(env):
    assert auth.ACCOUNT_LOCKED == "Too many attempts. Try again in 10 minutes."
    at = _app()
    for _ in range(auth.MAX_FAILED_ATTEMPTS - 1):
        _sign_in(at, "vendor@example.com", "wrong-password")
        assert auth.SIGN_IN_FAILED in _text(at)
    _sign_in(at, "vendor@example.com", "wrong-password")
    _no_errors(at)
    assert auth.ACCOUNT_LOCKED in _text(at) and at.session_state["page"] == "signin"
    _sign_in(at, "vendor@example.com", PW)                                          # locked: the right password too
    assert auth.ACCOUNT_LOCKED in _text(at) and "user_id" not in at.session_state


@pytest.mark.parametrize("name, email, password, confirm, message, field", [
    ("Achieng New", "achieng@example.com", "a-long-password", "another-password", "The passwords do not match.",
     "signup_confirm"),
    ("Achieng New", "achieng@example.com", "short", "short", "Use at least 10 characters for the password.",
     "signup_password"),
    ("Achieng New", "not-an-email", "a-long-password", "a-long-password", "Enter a valid email address.", "signup_email"),
    ("Achieng New", "vendor@example.com", "a-long-password", "a-long-password", auth.EMAIL_TAKEN, "signup_email"),
    ("", "achieng@example.com", "a-long-password", "a-long-password", "Enter your full name.", "signup_name"),
])
def test_sign_up_message_is_shown_under_its_field(env, name, email, password, confirm, message, field):
    at = _app(page="signup")
    for key, value in (("signup_name", name), ("signup_email", email), ("signup_password", password),
                       ("signup_confirm", confirm)):
        at.text_input(key=key).input(value)
    at.button(key="signup_submit").click().run()
    _no_errors(at)
    assert at.session_state["page"] == "signup" and "user_id" not in at.session_state
    flow = _flow(at)
    after = flow[flow.index(("text_input", field)) + 1]
    assert after[0] == "markdown" and 'class="auth-error"' in after[1] and message in after[1], flow
    assert sum('class="auth-error"' in v for _, v in flow) == 1                     # one message, in one place


def test_lender_is_blocked_from_vendor_pages(env):
    for page in VENDOR_PAGES:
        at = _app(user_id=env["lender"]["id"], page=page)
        _no_errors(at)
        text = _text(at)
        assert "This page is for vendors only." in text, page
        assert not [b for b in at.button if b.key.startswith("nav_") or b.key in ("get_score", "send_application")]
    at = _sign_in(_app(), "umoja@example.com", PW)                                 # a lender lands on the queue
    assert at.session_state["page"] == "lender" and "Applications" in _text(at) and "Umoja SACCO" in _text(at)
    at.button(key="side_signout").click().run()
    assert at.session_state["page"] == "signin"


def test_signed_out_users_only_see_sign_in(env):
    at = _app(page="history")
    assert at.session_state["page"] == "signin" and "Welcome back" in _text(at)


# ---------------------------------------------------------------- the vendor journey
def test_vendor_journey(env):
    # sign up through the screen
    at = _app(page="signup")
    at.text_input(key="signup_name").input("Achieng New")
    at.text_input(key="signup_email").input("achieng@example.com")
    at.text_input(key="signup_password").input("a-long-password")
    at.text_input(key="signup_confirm").input("a-long-password")
    at.button(key="signup_submit").click().run()
    _no_errors(at)
    assert at.session_state["page"] == "home"
    uid = at.session_state["user_id"]
    user = auth.get_user(env["conn"], uid)

    # the Score screen: upload only, no amount or days
    at.button(key="nav_score").click().run()
    _no_errors(at)
    assert not at.number_input and len(at.get("file_uploader")) == 1
    assert at.button(key="get_score").label == "Get my score" and at.button(key="get_score").disabled
    assert "Loan request" not in _text(at)

    # score twice (what "Get my score" calls), then continue on the Result screen
    _score(env, user, RICH)
    result = _score(env, user, RICH)
    at.session_state["result"] = result
    at.session_state["page"] = "result"
    at.run()
    _no_errors(at)
    text = _text(at)
    assert "simulated data" not in text and "Prototype" not in text               # no prototype line on Result
    assert _score_html(result) in text and "Estimated default risk" in text
    assert "Estimated limit" in text and '<div class="limit-big">Up to KES 34,300</div>' in text
    assert "Comfortable up to KES 9,200" in text and "The lender makes the final decision." in text
    assert all(p["name"] in text for p in result["pillars"])
    assert "Score over time, last 2 checks" in text                                # two saved checks
    assert at.button(key="to_apply").label == "Apply to a lender" and at.button(key="to_reasons").label == "See reasons"

    # Reasons: top reasons, and the what-if slider changes only the band (never the score or the limit)
    at.button(key="to_reasons").click().run()
    _no_errors(at)
    med = service.median_request()
    assert at.slider(key="loan_amount").value == 9200          # starts at the comfortable amount when known
    before = _text(at)
    assert all(r["phrase"] in before for r in result["reasons"]) and "Test an amount" in before
    assert "What the model weighed" in before and "Starts at your comfortable amount." in before
    at.slider(key="loan_amount").set_value(150000).run()
    _no_errors(at)
    after = _text(at)
    assert "KES 150,000" in after and "Outside typical range" in after
    band = service.affordability_band(150000, result["monthly_income"])
    assert components.pill(band.capitalize()) in after
    assert at.session_state["result"] == result                                    # never re-scored

    # Apply: the latest saved check, then amount and days, lender, consent, one button. No upload.
    at.button(key="reasons_apply").click().run()
    _no_errors(at)
    assert not at.get("file_uploader")                                             # no second upload
    radio = at.radio(key="apply_lender")
    assert sorted(radio.options) == ["Tumaini Microfinance", "Umoja SACCO"]       # organisation names are shown
    assert (at.number_input(key="apply_amount_in").value, at.number_input(key="apply_term_in").value) == \
        (9200, int(med[1]))                                    # amount prefilled with the comfortable amount
    text = _text(at)
    assert "Your score check" in text and f"C-{100 + result['check_id']}" in text and f"{result['score']} / 850" in text
    assert "Up to KES 34,300" in text and "Up to KES 9,200" in text and components.pill(result["tier"]) in text
    assert "Your request" in text and "The lender makes the final decision." in text
    assert "checked again" not in text and "upload" not in text.lower()
    assert at.checkbox(key="apply_consent").label == \
        "Share my score summary with the lender. My statement is never shared."
    send = at.button(key="send_application")
    assert send.label == "Send application" and send.disabled                      # needs consent
    at.radio(key="apply_lender").set_value(env["lender"]["id"])
    at.number_input(key="apply_amount_in").set_value(20000)
    at.number_input(key="apply_term_in").set_value(30)
    at.checkbox(key="apply_consent").check().run()
    assert not at.button(key="send_application").disabled
    at.button(key="send_application").click().run()
    _no_errors(at)
    assert at.session_state["page"] == "sent"
    sent = at.session_state["sent"]
    assert sent["check_id"] == result["check_id"]
    row, = H.rows(env["conn"], "applications", id=sent["id"])
    assert row["check_id"] == result["check_id"] and json.loads(row["snapshot_json"])["score"] == result["score"]
    text = _text(at)
    assert "Application sent" in text and "Umoja SACCO" in text and sent["ref"] in text and "Pending" in text
    assert f"C-{100 + result['check_id']}" in text and "Your statement is never shared." in text

    # History: the two checks and the application (a table on a laptop, expandable rows on a phone)
    at.button(key="sent_history").click().run()
    _no_errors(at)
    text = _text(at)
    assert "2 checks · 1 application" in text and "Score checks" in text and "My applications" in text
    assert text.count(sent["ref"]) == 2 and text.count("Umoja SACCO") >= 2                # table and row
    assert components.pill("Pending") in text and 'class="pill pill-moderate">Pending<' in text

    # Profile: a toggle is stored as soon as it is switched; delete saved results with a confirm step; sign out
    at.button(key="nav_profile").click().run()
    _no_errors(at)
    at.toggle(key="flag_email_notifications").set_value(True).run()
    _no_errors(at)
    assert auth.get_user(env["conn"], uid)["email_notifications"] == 1
    at.button(key="delete_results").click().run()
    assert service.score_history(env["conn"], uid) != []                          # nothing deleted before confirming
    at.button(key="confirm_delete").click().run()
    _no_errors(at)
    assert service.score_history(env["conn"], uid) == [] and "result" not in at.session_state
    at.button(key="sign_out").click().run()
    assert at.session_state["page"] == "signin" and "user_id" not in at.session_state



def test_profile_toggles_save_when_switched_and_save_results_off_stops_storing_checks(env):
    uid = env["vendor"]["id"]
    _score(env, auth.get_user(env["conn"], uid))
    before = service.score_history(env["conn"], uid)
    assert len(before) == 1
    at = _app(user_id=uid, page="profile")
    _no_errors(at)
    assert not [b for b in at.button if b.key == "profile_save"]                 # no Save changes for the toggles
    at.toggle(key="flag_share_with_lenders").set_value(not env["vendor"]["share_with_lenders"]).run()
    _no_errors(at)
    assert bool(auth.get_user(env["conn"], uid)["share_with_lenders"]) != bool(env["vendor"]["share_with_lenders"])
    at.toggle(key="flag_save_results").set_value(False).run()
    _no_errors(at)
    user = auth.get_user(env["conn"], uid)
    assert user["save_results"] == 0                                             # stored without pressing anything
    assert at.toggle(key="flag_save_results").value is False                     # and the page still shows it off
    result = _score(env, user)                                                   # the next check is not stored
    assert result["check_id"] is None and service.score_history(env["conn"], uid) == before

def test_result_for_a_very_high_risk_vendor(env):
    result = _score(env, env["vendor"])                       # the default toy statement is Very high risk
    assert result["tier"] == "Very high risk"
    at = _app(user_id=env["vendor"]["id"], page="result", result=result)
    _no_errors(at)
    text = _text(at)
    assert components.pill("Not eligible right now", "bad") in text                # a red pill, black text
    assert "Up to KES" not in text
    assert components.pill("Very high risk", "brand") in text                       # the hero's yellow tier pill
    at.button(key="to_reasons").click().run()
    assert at.session_state["page"] == "reasons" and "What the model weighed" in _text(at)


def test_result_without_income_data(env):
    no_income = toy.recompute_balance(toy.make_vendor()[lambda d: d.paid_in == 0].reset_index(drop=True), opening=50000.0)
    result = _score(env, env["vendor"], no_income)
    at = _app(user_id=env["vendor"]["id"], page="result", result=result)
    _no_errors(at)
    assert "Not enough income data" in _text(at) and "Up to KES" not in _text(at)


def test_apply_page_has_no_file_uploader_and_no_upload_copy(env):
    result = _score(env, env["vendor"], RICH)
    at = _app(user_id=env["vendor"]["id"], page="apply")
    _no_errors(at)
    assert not at.get("file_uploader")
    text = _text(at)
    assert "Uses your latest score check" in text and "Your statement is checked again" not in text
    assert f"C-{100 + result['check_id']}" in text
    src = (H.ROOT / "app" / "pages" / "apply.py").read_text(encoding="utf-8")
    assert "file_uploader" not in src and "apply_upload" not in src


@pytest.mark.parametrize("state", ["none", "expired", "not_saved"])
def test_without_a_usable_check_the_page_asks_to_check_again(env, state):
    user = env["vendor"]
    if state == "expired":
        _score(env, user, RICH)
        with db.transaction(env["conn"]):                                    # make the check 31 days old
            env["conn"].execute(db.score_checks.update().values(
                created_at=db.utcnow() - timedelta(days=service.APPLY_CHECK_MAX_AGE_DAYS + 1)))
    if state == "not_saved":
        user = service.update_profile_flags(env["conn"], user["id"], save_results=False)
        _score(env, user, RICH)
    at = _app(user_id=user["id"], page="apply")
    _no_errors(at)
    text = _text(at)
    assert "Check your score again to apply" in text and not at.get("file_uploader")
    assert not [b for b in at.button if b.key == "send_application"] and not at.number_input
    if state == "not_saved":
        assert "Save my score results" in text
    at.button(key="apply_check_score").click().run()
    assert at.session_state["page"] == "score"


def test_apply_above_the_limit_and_duplicate_show_their_messages(env):
    _score(env, env["vendor"], RICH)
    at = _app(user_id=env["vendor"]["id"], page="apply")
    at.radio(key="apply_lender").set_value(env["lender"]["id"])
    at.number_input(key="apply_amount_in").set_value(34400)
    at.checkbox(key="apply_consent").check().run()
    at.button(key="send_application").click().run()
    _no_errors(at)
    assert "You can apply for up to KES 34,300. Lower the amount and try again." in _text(at)
    assert at.session_state["page"] == "apply" and db.count(env["conn"], "applications") == 0
    at.number_input(key="apply_amount_in").set_value(9000)
    at.button(key="send_application").click().run()
    assert at.session_state["page"] == "sent"
    at = _app(user_id=env["vendor"]["id"], page="apply")
    at.radio(key="apply_lender").set_value(env["lender"]["id"])
    at.checkbox(key="apply_consent").check().run()
    at.button(key="send_application").click().run()
    assert service.MSG_DUPLICATE in _text(at) and db.count(env["conn"], "applications") == 1


def test_apply_with_a_very_high_check_is_not_eligible_and_cannot_send(env):
    result = _score(env, env["vendor"])                        # Very high risk: no comfortable amount
    at = _app(user_id=env["vendor"]["id"], page="apply")
    _no_errors(at)
    assert "Not eligible right now." in _text(at) and any(b.key == "apply_see_why" for b in at.button)
    assert at.number_input(key="apply_amount_in").value == int(result["request_amount"])
    at.checkbox(key="apply_consent").check().run()
    assert at.button(key="send_application").disabled
    at = _app(user_id=env["vendor"]["id"], page="reasons", result=result)
    assert at.slider(key="loan_amount").value == int(service.median_request()[0])


# ---------------------------------------------------------------- errors
SECRET = "cell JANE WANJIKU 0722987654 SELECT * FROM score_checks"


def test_an_unexpected_error_shows_a_card_and_logs_only_class_location_and_id(env, monkeypatch, caplog):
    def boom(*a, **kw):
        raise RuntimeError(SECRET)
    _score(env, env["vendor"])                                 # with a score, Home lists the latest applications
    monkeypatch.setattr(service, "list_applications", boom)
    caplog.set_level(logging.INFO, logger=errors.LOGGER_NAME)
    at = _app(user_id=env["vendor"]["id"], page="home")
    assert not at.exception                                    # handled, not shown as a traceback
    text = _text(at)
    assert "Something went wrong. Please try again." in text and at.button(key="error_home").label == "Back to Home"
    assert "Business health" not in text and "Latest applications" not in text   # the half-drawn page is cleared
    records = [r for r in caplog.records if r.name == errors.LOGGER_NAME]
    assert len(records) == 1
    line = records[0].getMessage()
    m = re.fullmatch(r"incident=([0-9A-F]{6}) RuntimeError at app\.pages\.home:render:\d+", line)
    assert m, line
    assert f"Incident {m.group(1)}" in text                    # the same id on screen
    assert records[0].exc_info is None and records[0].stack_info is None
    for part in ("JANE", "0722987654", "cell", "SELECT", "score_checks"):
        assert part not in line and part not in text
    at.button(key="error_home").click().run()
    assert at.session_state["page"] == "home"


def test_a_score_that_could_not_be_saved_is_still_shown(env):
    result = dict(_score(env, env["vendor"], RICH), check_id=None, save_error=service.MSG_DB_SAVE)
    at = _app(user_id=env["vendor"]["id"], page="result", result=result)
    _no_errors(at)
    text = _text(at)
    assert _score_html(result) in text and "Up to KES 34,300" in text
    assert "Could not save your result. Please try again." in text


def test_an_out_of_date_schema_shows_a_card_and_one_log_line(env, caplog):
    with db.transaction(env["conn"]):
        env["conn"].exec_driver_sql("ALTER TABLE score_checks DROP COLUMN max_amount")
        env["conn"].exec_driver_sql("ALTER TABLE score_checks DROP COLUMN comfortable_amount")
    caplog.set_level(logging.INFO, logger=errors.LOGGER_NAME)
    for page in ("signin", "home"):
        at = _app(user_id=env["vendor"]["id"], page=page)
        _no_errors(at)
        assert "Database schema out of date. See docs/database.md." in _text(at)
        assert not [b for b in at.button if b.key.startswith(("nav_", "signin_"))]   # no page behind it
    lines = [r.getMessage() for r in caplog.records if r.name == errors.LOGGER_NAME]
    assert lines == ["Database schema out of date. See docs/database.md. Missing: score_checks.max_amount, "
                     "score_checks.comfortable_amount"]                              # once, at start-up


# ---------------------------------------------------------------- design rules
def test_pill_has_black_text_and_the_meaning_in_its_background():
    expected = {"Pending": "moderate", "Approved": "good", "Declined": "bad", "Raises risk": "bad", "Lowers risk": "good",
                "Low risk": "good", "Moderate risk": "moderate", "High risk": "high", "Very high risk": "bad",
                "Weak": "bad", "Fair": "moderate", "Good": "good", "Strong": "good", "Active": "good",
                "Locked for 9 min": "bad", "Comfortable": "good", "Stretched": "moderate", "Heavy": "high"}
    for label, kind in expected.items():
        s = components.pill(label)
        assert s == f'<span class="pill pill-{kind}">{label}</span>', label            # no inline style at all
    assert components.pill("Very high risk", "brand") == '<span class="pill pill-brand">Very high risk</span>'
    with pytest.raises(ValueError):
        components.pill("x", "red")
    css = theme.css()
    rule = re.search(r"\.pill \{([^}]*)\}", css).group(1)
    assert "color: #0E1226" in rule and "font-weight: 700" in rule and "height: 28px" in rule
    backgrounds = {"good": "#BFEBCF", "moderate": "#FBE2A0", "high": "#FFD1B0", "bad": "#F8BDB6", "neutral": "#E4E1FF"}
    for kind, bg in backgrounds.items():
        assert re.search(rf"\.pill-{kind} \{{ background: {bg}; \}}", css), kind
    for kind_rule in re.findall(r"\.pill-\w+ \{([^}]*)\}", css):
        assert "color" not in kind_rule                                   # a pill kind never changes the text colour
    # no coloured status text anywhere: the old helpers are gone
    for gone in ("status_text", "colored_text", "status_icon_text", "status_md", "STATUS_COLORS"):
        assert not hasattr(components, gone), gone


def test_no_emoji_anywhere(env, models):
    for p in (H.ROOT / "app").rglob("*.py"):
        assert not EMOJI.search(p.read_text(encoding="utf-8")), p
    assert not EMOJI.search((H.ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    user = env["vendor"]
    result = _score(env, user, RICH)
    _stored_application(env, user, result)
    seen = []
    for page in (*VENDOR_PAGES, "sent"):
        at = _app(user_id=user["id"], page=page, result=result,
                  sent={"ref": "A-101", "lender": "Umoja SACCO", "status": "pending"})
        _no_errors(at)
        seen.append(_text(at))
    for page in ("signin", "signup"):
        seen.append(_text(_app(page=page)))
    rendered = "\n".join(seen)
    assert not EMOJI.search(rendered)
    assert 'class="status"' not in rendered                                       # no coloured status text
    for m in re.finditer(r'<span class="pill[^"]*"[^>]*>', rendered):               # pills: never an inline colour
        assert "style=" not in m.group(0)


# ---------------------------------------------------------------- responsive pages, score chart, History
STATES = ("none", "one", "several")


def _vendor_with(env, state):
    """The vendor with no saved check, one, or six (the chart shows the last five), plus one application."""
    user = env["vendor"]
    if state != "none":
        base = _score(env, user, RICH)                          # one real check
        if state == "several":
            _add_checks(env, user, base, [560, 590, 610, 640, 670])
        _stored_application(env, user, base)
    return user


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("page", VENDOR_PAGES)
def test_every_vendor_page_renders_in_the_shell(env, page, state):
    user = _vendor_with(env, state)
    at = _app(user_id=user["id"], page=page)
    _no_errors(at)
    text = _text(at)
    # one shell: the sidebar items and the tab bar come from the same nav list
    assert [b.key for b in at.button if b.key.startswith("sidenav_")] == [f"sidenav_{n.key}" for n in components.VENDOR_NAV]
    assert [b.key for b in at.button if b.key.startswith("nav_")] == [f"nav_{n.key}" for n in components.VENDOR_NAV]
    assert at.button(key="topbar_menu").label == "Menu" and 'role="heading" aria-level="1"' in text
    assert "Notifications" not in text                                             # no notification bell
    for gone in ("Forgot password", "Demo", "580", "simulat"):
        assert gone.lower() not in text.lower(), gone
    if page in ("home", "result"):
        assert (_chart(text) is None) == (state == "none")
        assert any(b.key == "cta_score" for b in at.button) == (state == "none")


def test_score_chart_with_zero_one_and_five_checks(env):
    user = env["vendor"]
    assert _chart(_text(_app(user_id=user["id"], page="home"))) is None            # 0 checks: no chart, one card

    base = _score(env, user, RICH)                                                  # 1 check: one point
    chart = _chart(_text(_app(user_id=user["id"], page="home")))
    assert chart and "Score over time, one check, score" in chart
    assert chart.count("<circle") == 1 and "<polyline" not in chart
    assert f'r="6" fill="#FFFFFF" stroke="{theme.GOLD}"' in chart                  # the latest point, outlined in yellow

    _add_checks(env, user, base, [520, 556, 600, 640, 700])                        # 6 saved: the last 5 are drawn
    chart = _chart(_text(_app(user_id=user["id"], page="home")))
    assert chart.count("<circle") == 5 and f'<polyline points="' in chart and "last 5 checks" in chart
    assert f'stroke="{theme.GOLD}" stroke-width="3"' in chart                     # the yellow line
    checks = service.recent_checks(env["conn"], user["id"], 5)
    drawn = [int(v) for v in re.findall(r'<div class="hero-pt"><b>(\d{3})</b>', chart)]
    assert drawn == [c["score"] for c in reversed(checks)]                          # oldest on the left, scores under it
    assert len(re.findall(r'<div class="hero-pt"><b>\d{3}</b><span>\d{2} \w{3}', chart)) == 5   # and their dates


def test_hero_chart_goes_up_for_a_higher_score_and_says_the_trend():
    pts = [("2026-11-01T07:00:00+00:00", 640), ("2026-11-02T07:00:00+00:00", 590), ("2026-11-03T07:00:00+00:00", 520)]
    svg = components.hero_chart(pts)
    ys = [float(y) for y in re.findall(r'<circle cx="[\d.]+" cy="([\d.]+)"', svg)]
    assert ys == sorted(ys)                                     # falling scores: each point lower on the chart
    assert "down from 640 to 520" in svg and "01 Nov" in svg and "03 Nov" in svg
    same_day = [("2026-11-01T07:00:00+00:00", 600), ("2026-11-01T09:00:00+00:00", 610)]
    assert "01 Nov 10:00" in components.hero_chart(same_day) and "01 Nov 12:00" in components.hero_chart(same_day)
    assert components.hero_chart([]) == ""


def test_history_lists_checks_and_applications_without_file_names(env):
    user = env["vendor"]
    result = service.run_score_check(env["conn"], user, H.Upload(H.statement_csv(RICH), "my-shop-statement-NOV.csv"))
    app_ = _stored_application(env, user, result)
    at = _app(user_id=user["id"], page="history")
    _no_errors(at)
    text = _text(at)
    assert "my-shop-statement" not in text and ".csv" not in text.lower()
    assert "1 check · 1 application" in text
    for head in ("Date", "Reference", "Score", "Risk", "Default risk", "Estimated limit",
                 "Lender", "Request", "Status", "Lender note"):
        assert f"<th>{head}</th>" in text, head
    assert f"C-{100 + result['check_id']}" in text and app_["ref"] in text
    assert components.pill(result["tier"]) in text and components.pill("Pending") in text
    assert 'class="only-wide tbl-wrap"' in text and 'class="only-narrow"' in text  # table (laptop), rows (phone)


def test_history_with_nothing_yet(env):
    at = _app(user_id=env["vendor"]["id"], page="history")
    _no_errors(at)
    text = _text(at)
    assert "0 checks · 0 applications" in text and "No score checks yet." in text and "No applications yet." in text
    assert at.button(key="history_apply").label == "Apply to a lender"


def test_business_health_tiles_in_the_model_order_with_rating_pills(env):
    user = env["vendor"]
    result = _score(env, user, RICH)
    at = _app(user_id=user["id"], page="result", result=result)
    _no_errors(at)
    text = _text(at)
    assert '<div class="cap">Your financial life</div>' in text
    assert re.findall(r'<div class="tile-title">([^<]+)</div>', text) == list(service.PILLAR_NAMES.values())
    for p in result["pillars"]:
        assert components.pill(p["label"]) in text
    assert not at.get("button_group")                                              # no filter chips any more
    assert at.button(key="to_reasons").label == "See reasons"                      # the hero on Result has it


def test_home_recent_activity_empty_and_view_all(env):
    user = env["vendor"]
    text = _text(_app(user_id=user["id"], page="home"))
    assert components.EMPTY_ACTIVITY not in text                                   # no score yet: only the first card
    user = service.update_profile_flags(env["conn"], user["id"], save_results=False)
    result = _score(env, user)
    at = _app(user_id=user["id"], page="home", result=result)
    _no_errors(at)
    text = _text(at)
    assert components.EMPTY_ACTIVITY == "Nothing here yet. Check your score to get started."
    assert components.EMPTY_ACTIVITY in text and not [b for b in at.button if b.key == "latest_all"]
    _stored_application(env, user, result)
    at = _app(user_id=user["id"], page="home", result=result)
    assert at.button(key="latest_all").label == "View all"
    at.button(key="latest_all").click().run()
    assert at.session_state["page"] == "history"


def test_check_score_page_copy(env):
    at = _app(user_id=env["vendor"]["id"], page="score")
    _no_errors(at)
    text = _text(at)
    assert "CSV, XLSX or XLS · Max 10 MB" in text and "How to export" in text
    assert '<div class="cap">Upload statement</div>' in text
    assert "Open the M-Pesa Business Portal, then Statements" in text and "Select 90 to 180 days" in text
    assert "Download as CSV or Excel" in text and components.AUTH_FOOTER in text
    assert "pdf" not in text.lower()                            # PDFs only in the scanned-PDF error message
    assert not at.number_input and at.button(key="get_score").label == "Get my score"


def test_business_health_rows_say_what_each_area_measures(env):
    result = _score(env, env["vendor"])
    at = _app(user_id=env["vendor"]["id"], page="result", result=result)
    _no_errors(at)
    text = _text(at)
    for line in ("How steady your weekly income is.", "How much money you keep in your wallet from day to day.",
                 "How much you rely on Fuliza and short-term borrowing.",
                 "How big your debt payments are compared with your income.", "Whether bills and rent are paid on time.",
                 "How long your history is and whether your income is growing.",
                 "How many customers and suppliers you deal with repeatedly."):
        assert line in text
