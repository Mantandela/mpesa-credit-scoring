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


def _text(at) -> str:
    """Everything the screen shows as text: markdown, button, widget and expander labels."""
    parts = [m.value for m in at.markdown if "<style>" not in m.value]
    parts += [b.label for b in at.button] + [e.label for e in at.expander]
    parts += [w.label for w in (*at.text_input, *at.number_input, *at.slider, *at.checkbox, *at.toggle, *at.radio)]
    return "\n".join(parts)


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
        elif node.type in ("text_input", "button"):
            out.append((node.type, node.key))
    walk(at.main)
    return out


def test_sign_in_renders(env):
    at = _app()
    _no_errors(at)
    text = _text(at)
    assert "Welcome back" in text and "Sign in to check your score" in text
    assert [t.label for t in at.text_input] == ["Email", "Password"]
    assert at.text_input(key="signin_password").proto.type == TextInputProto.PASSWORD   # built-in reveal control
    assert at.button(key="to_signup").label == "New vendor? **Create an account**"      # bold part is the purple link
    assert not [b for b in at.button if b.key.startswith(("nav_", "topbar_"))]     # no tab bar or top bar before sign in


def test_sign_up_renders(env):
    at = _app(page="signup")
    _no_errors(at)
    text = _text(at)
    assert "Create your account" in text and "Takes less than a minute" in text
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
    # the shared band and footer
    assert components.APP_NAME in text and "Know your credit score from your" in text
    assert all(p in text for p in components.AUTH_POINTS) and components.AUTH_FOOTER in text


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
    assert [b.label for b in at.button if b.key.startswith("nav_")] == ["Home", "Score", "History", "Profile"]
    assert [b.label for b in at.button if b.key.startswith("sidenav_")] == ["Home", "Score", "History", "Profile"]
    assert at.button(key="side_signout").label == "Sign out" and "Wanjiku Test" in text


RICH = toy.make_vendor(days=120, daily_in=164000 / 30)       # Low risk under the toy model: eligible up to KES 34,300


def _score(env, user, vendor=None):
    return service.run_score_check(env["conn"], user, H.Upload(H.statement_csv(vendor), "s.csv"))


def _stored_application(env, user, result):
    """An application as submit_application stores it (AppTest cannot upload a file to the Apply screen)."""
    lender = {"id": env["lender"]["id"], "org_name": "Umoja SACCO"}
    return service._insert_application(env["conn"], user, lender, service.snapshot(result))


def _score_html(result) -> str:
    return f'<div class="sc-score">{result["score"]}<span class="sc-of">out of 850</span></div>'


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
    m = re.search(r'<svg role="img" aria-label="Score chart.*?</svg>', text, re.S)
    return m.group(0) if m else None


def test_home_with_a_score_and_applications(env):
    user, conn = env["vendor"], env["conn"]
    result = _score(env, user)
    sent = [_stored_application(env, user, result) for _ in range(4)]
    at = _app(user_id=user["id"], page="home")                  # no session result: the latest saved check is used
    _no_errors(at)
    text = _text(at)
    assert _score_html(result) in text and f"Estimated default risk {components.pct(result['pd'])}" in text
    assert "Last check · " in text
    assert [(b.key, b.label) for b in at.button if b.key.startswith("head_")] == [
        ("head_score", "Check score"), ("head_apply", "Apply")]
    assert at.button(key="to_reasons").label == "See reasons"
    assert "Business health" in text and components.health_rows(components._pillars_in_order(result["pillars"])) in text
    assert [p["name"] for p in components._pillars_in_order(result["pillars"])] == list(service.PILLAR_NAMES.values())
    assert "Estimated limit" in text or "Not eligible right now" in text or "Not enough income data" in text
    rows = [b for b in at.button if b.key.startswith("row_app_")]
    assert len(rows) == 3                                        # up to 3, newest first
    assert [b.key for b in rows] == [f"row_app_{s['id']}" for s in reversed(sent)][:3]
    assert all(b.label == "Umoja SACCO  :orange[**Pending**]" for b in rows)
    assert not [b for b in at.button if b.key.startswith(("qa_", "row_breakdown"))]
    rows[0].click().run()
    assert at.session_state["page"] == "history"                 # a row opens History


def test_home_uses_the_session_result_when_checks_are_not_saved(env):
    user = service.update_profile_flags(env["conn"], env["vendor"]["id"], save_results=False)
    result = _score(env, user)
    assert result["check_id"] is None
    at = _app(user_id=user["id"], page="home", result=result)
    _no_errors(at)
    assert "Business health" in _text(at) and _score_html(result) in _text(at)
    assert "Score chart, one check" in _text(at)                 # the unsaved result is the chart's only point


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
    at = _sign_in(_app(), "umoja@example.com", PW)                                 # a lender lands on the stub
    assert at.session_state["page"] == "lender" and "Stage 2" in _text(at)
    at.button(key="sign_out").click().run()
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
    assert "Estimated limit: Up to KES 34,300" in text
    assert "Comfortable up to KES 9,200 · the lender makes the final decision" in text
    assert all(p["name"] in text for p in result["pillars"])
    assert "Score chart, last 2 checks" in text                                    # two saved checks
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
    assert components.status_text(band.capitalize()) in after
    assert at.session_state["result"] == result                                    # never re-scored

    # Apply: lender, amount and days (median request), the statement again, consent, one button
    at.button(key="reasons_apply").click().run()
    _no_errors(at)
    radio = at.radio(key="apply_lender")
    assert sorted(radio.options) == ["Tumaini Microfinance", "Umoja SACCO"]       # organisation names are shown
    assert (at.number_input(key="apply_amount_in").value, at.number_input(key="apply_term_in").value) == \
        (9200, int(med[1]))                                    # amount prefilled with the comfortable amount
    text = _text(at)
    assert "Your estimated limit" in text and "Up to KES 34,300" in text and "Comfortable up to KES 9,200" in text
    assert "Your request" in text and "The lender makes the final decision." in text
    assert len(at.get("file_uploader")) == 1
    assert at.checkbox(key="apply_consent").label == \
        "Share my score summary with the lender. My statement is never shared."
    send = at.button(key="send_application")
    assert send.label == "Send application" and send.disabled                      # needs the statement and consent
    # AppTest cannot upload a file: send the way the button does, then continue on the Sent screen
    out = service.submit_application(env["conn"], user, env["lender"]["id"], H.Upload(H.statement_csv(RICH), "s.csv"),
                                     20000, 30, True)
    assert out["outcome"] == service.OUTCOME_SENT
    at.session_state["sent"] = out["application"]
    at.session_state["page"] = "sent"
    at.run()
    _no_errors(at)
    sent = at.session_state["sent"]
    text = _text(at)
    assert "Application sent" in text and "Umoja SACCO" in text and sent["ref"] in text and "Pending" in text

    # History: the two checks and the application (a table on a laptop, expandable rows on a phone)
    at.button(key="sent_history").click().run()
    _no_errors(at)
    text = _text(at)
    assert "2 checks · 1 application" in text and "Score checks" in text and "My applications" in text
    assert text.count(sent["ref"]) == 2 and text.count("Umoja SACCO") >= 2                # table and row
    assert components.status_text("Pending") in text

    # Profile: settings are stored by "Save changes"; delete saved results with a confirm step; sign out
    at.button(key="nav_profile").click().run()
    _no_errors(at)
    at.toggle(key="flag_email_notifications").set_value(True)
    assert auth.get_user(env["conn"], uid)["email_notifications"] == 0                    # not before saving
    at.button(key="profile_save").click().run()
    _no_errors(at)
    assert auth.get_user(env["conn"], uid)["email_notifications"] == 1 and "Changes saved." in _text(at)
    at.button(key="delete_results").click().run()
    assert service.score_history(env["conn"], uid) != []                          # nothing deleted before confirming
    at.button(key="confirm_delete").click().run()
    _no_errors(at)
    assert service.score_history(env["conn"], uid) == [] and "result" not in at.session_state
    at.button(key="sign_out").click().run()
    assert at.session_state["page"] == "signin" and "user_id" not in at.session_state


def test_result_for_a_very_high_risk_vendor(env):
    result = _score(env, env["vendor"])                       # the default toy statement is Very high risk
    assert result["tier"] == "Very high risk"
    at = _app(user_id=env["vendor"]["id"], page="result", result=result)
    _no_errors(at)
    text = _text(at)
    assert components.colored_text("Not eligible right now", "Very high risk") in text            # red text
    assert components.status_color("Very high risk") == "#B42318"
    assert "Estimated limit:" not in text and "Up to KES" not in text
    assert "Your latest score is in the Very high risk zone." in text
    at.button(key="to_reasons").click().run()
    assert at.session_state["page"] == "reasons" and "What the model weighed" in _text(at)


def test_result_without_income_data(env):
    no_income = toy.recompute_balance(toy.make_vendor()[lambda d: d.paid_in == 0].reset_index(drop=True), opening=50000.0)
    result = _score(env, env["vendor"], no_income)
    at = _app(user_id=env["vendor"]["id"], page="result", result=result)
    _no_errors(at)
    assert "Not enough income data" in _text(at) and "Up to KES" not in _text(at)


@pytest.mark.parametrize("msg, shown, see_why", [
    (("above", "You can apply for up to KES 34,300. Lower the amount and try again."),
     "You can apply for up to KES 34,300. Lower the amount and try again.", False),
    (("not_eligible", "Not eligible right now."), "Not eligible right now.", True),
    (("no_income", "Not enough income data."), "Not enough income data.", False),
    (("error", "This PDF has no selectable text. Please upload the Excel or CSV statement."),
     "This PDF has no selectable text. Please upload the Excel or CSV statement.", False),
])
def test_apply_outcome_lines(env, msg, shown, see_why):
    at = _app(user_id=env["vendor"]["id"], page="apply", apply_msg=msg)
    _no_errors(at)
    assert shown in _text(at) and at.session_state["page"] == "apply"
    assert any(b.key == "apply_see_why" for b in at.button) == see_why
    assert len(at.get("file_uploader")) == 1                  # the statement is asked for again


def test_apply_page_never_keeps_the_statement():
    src = (H.ROOT / "app" / "pages" / "apply.py").read_text(encoding="utf-8")
    assert "apply_upload_n" in src and src.count('st.session_state["apply_upload_n"] = n + 1') >= 2


def test_apply_without_a_known_limit_uses_the_median_request(env):
    at = _app(user_id=env["vendor"]["id"], page="apply")       # no score yet
    _no_errors(at)
    assert "Your estimated limit" not in _text(at)
    assert at.number_input(key="apply_amount_in").value == int(service.median_request()[0])


def test_apply_and_reasons_with_a_very_high_result_fall_back_to_the_median(env):
    result = _score(env, env["vendor"])                        # Very high risk: no comfortable amount
    at = _app(user_id=env["vendor"]["id"], page="apply", result=result)
    _no_errors(at)
    assert "Your estimated limit" in _text(at) and "Not eligible right now" in _text(at)
    assert at.number_input(key="apply_amount_in").value == int(service.median_request()[0])
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
def test_status_text_is_coloured_text_only():
    for label in components.STATUS_COLORS:
        s = components.status_text(label.title())
        assert "color:" in s and "font-weight:700" in s and "background" not in s.lower()
        assert re.fullmatch(r'<span class="status" style="color:#[0-9A-F]{6};font-weight:700">[^<]+</span>', s)
    for label in ("Pending", "Approved", "Declined", "Comfortable", "Stretched", "Heavy"):
        md = components.status_md(label)
        assert "background" not in md and md.startswith(":") and "**" in md
    assert components.status_color("Pending") == "#B45309" and components.status_color("Moderate") == "#B45309"
    for red in ("High risk", "Very high risk", "Weak", "Declined", "Raises risk", "Heavy"):
        assert components.status_color(red) == "#B42318", red
    for green in ("Low risk", "Good", "Strong", "Approved", "Lowers risk", "Comfortable"):
        assert components.status_color(green) == "#067647", green
    assert ".status" not in theme.css()                                             # no CSS restyles status text


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
    for m in re.finditer(r'<span class="status"[^>]*>', rendered):                  # rendered status text
        assert "background" not in m.group(0)


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

    base = _score(env, user, RICH)                                                  # 1 check: one point and the zones
    chart = _chart(_text(_app(user_id=user["id"], page="home")))
    assert chart and "Score chart, one check, score" in chart
    assert chart.count("<circle") == 1 and "<polyline" not in chart
    assert re.search(r'r="6.5" fill="#FFFFFF" stroke="#[0-9A-F]{6}"', chart)          # the latest point, outlined

    _add_checks(env, user, base, [520, 556, 600, 640, 700])                        # 6 saved: the last 5 are drawn
    chart = _chart(_text(_app(user_id=user["id"], page="home")))
    assert chart.count("<circle") == 5 and "<polyline" in chart and "last 5 checks" in chart
    checks = service.recent_checks(env["conn"], user["id"], 5)
    drawn = [int(v) for v in re.findall(r'text-anchor="middle" font-size="1[14]"[^>]*>(\d{3})</text>', chart)]
    assert drawn == [c["score"] for c in reversed(checks)]                          # oldest on the left
    assert f'stroke="{components.status_color(checks[0]["tier"])}" stroke-width="3"' in chart


def test_chart_zones_come_from_scoring_and_a_low_score_shows_the_high_zones():
    bounds = components.tier_boundaries()
    assert [b for b, _, _ in bounds] == [int(SC.pd_to_score(u)) for u, _ in SC.TIER_BANDS[:-1]]
    names = [n for _, n in SC.TIER_BANDS]
    assert [(a, b) for _, a, b in bounds] == list(zip(names, names[1:]))
    # scores falling from Moderate into High and Very high: all three zone lines and their labels
    pts = [("2026-11-01T07:00:00+00:00", 640), ("2026-11-02T07:00:00+00:00", 590), ("2026-11-03T07:00:00+00:00", 520)]
    svg = components.score_chart(pts, "Very high risk")
    ys = [float(v) for v in re.findall(r'<line [^>]*y1="([\d.]+)"', svg)]
    assert len(ys) == 3 and 'stroke-dasharray="4 4"' in svg
    assert ys == sorted(ys)                                     # 660, 598, 545 drawn top to bottom: higher is better
    for word, color in (("Moderate", "#B45309"), ("High", "#B42318"), ("Very high", "#B42318")):
        assert f'fill="{color}">{word}</text>' in svg, word
    assert 'stroke="#B42318" stroke-width="3"' in svg                              # latest point in its zone colour
    assert "down from 640 to 520" in svg and "Very high risk zone" in svg
    # a single high score: the Low zone and the nearest line only
    svg = components.score_chart([("2026-11-01T07:00:00+00:00", 720)], "Low risk")
    assert len(re.findall(r"<line ", svg)) == 1 and 'fill="#067647">Low</text>' in svg and ">Very high<" not in svg


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
    assert components.status_text(result["tier"]) in text and components.status_text("Pending") in text
    assert 'class="only-wide tbl-wrap"' in text and 'class="only-narrow"' in text  # table (laptop), rows (phone)


def test_history_with_nothing_yet(env):
    at = _app(user_id=env["vendor"]["id"], page="history")
    _no_errors(at)
    text = _text(at)
    assert "0 checks · 0 applications" in text and "No score checks yet." in text and "No applications yet." in text
    assert at.button(key="history_apply").label == "Apply to a lender"


def test_business_health_filter_chips_keep_the_page(env):
    user = env["vendor"]
    result = _score(env, user, RICH)
    at = _app(user_id=user["id"], page="result", result=result)
    pillars = result["pillars"]
    work = [p for p in pillars if p["label"] in ("Weak", "Fair")]
    assert f"All ({len(pillars)})" in str(at.get("button_group")[0].proto)
    at.session_state["health_filter"] = "work"
    at.run()
    _no_errors(at)
    assert at.session_state["page"] == "result" and at.session_state["result"] == result      # page state kept
    shown = re.findall(r'<span class="x-main">([^<]+)</span>', _text(at))
    assert shown == [p["name"] for p in components._pillars_in_order(work)]


def test_home_top_score_drags_and_latest_applications(env):
    user = env["vendor"]
    result = _score(env, user)                                  # Very high: several reasons raise risk
    at = _app(user_id=user["id"], page="home")
    text = _text(at)
    drags = [r for r in result["reasons"] if r["direction"] == "Raises risk"][:3]
    assert ("Top score drags" in text) == bool(drags)
    for r in drags:
        assert components.reason_row("Raises risk", r["phrase"]) in text
    assert "No applications yet." in text and at.button(key="latest_apply").label == "Apply to a lender"
    _stored_application(env, user, result)
    at = _app(user_id=user["id"], page="home")
    assert at.button(key="latest_all").label == "View all"
    at.button(key="latest_all").click().run()
    assert at.session_state["page"] == "history"


def test_check_score_page_copy(env):
    at = _app(user_id=env["vendor"]["id"], page="score")
    _no_errors(at)
    text = _text(at)
    assert f"CSV, XLSX or XLS · Max {service.MAX_UPLOAD_BYTES // 2**20} MB" in text and "How to export" in text
    assert "Open the M-Pesa Business Portal, then Statements" in text and "Select 90 to 180 days" in text
    assert "Download as CSV or Excel" in text and components.AUTH_FOOTER in text
    assert "pdf" not in text.lower()                            # PDFs only in the scanned-PDF error message
    assert not at.number_input and at.button(key="get_score").label == "Get my score"
