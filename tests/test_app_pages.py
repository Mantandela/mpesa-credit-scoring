"""Web app screens (app/main.py and app/pages/) through streamlit.testing.v1.AppTest.

AppTest cannot drive the file uploader, so the end-to-end test scores the synthetic statement through the service
(exactly what the Score screen calls) and continues in the app from the Result screen.
"""
import re

import pytest
from streamlit.testing.v1 import AppTest

import app_helpers as H
import toy
from app import auth, components, db, service, theme

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
def test_sign_in_renders(env):
    at = _app()
    _no_errors(at)
    text = _text(at)
    assert "Welcome back" in text and "Forgot password?" in text and "New vendor? Create an account" in text
    assert [t.label for t in at.text_input] == ["Email", "Password"]
    assert not [b for b in at.button if b.key.startswith("nav_")]                  # no tab bar before sign in


def test_vendor_signs_in_and_reaches_home(env):
    at = _sign_in(_app(), "vendor@example.com", PW)
    _no_errors(at)
    assert at.session_state["page"] == "home" and at.session_state["user_id"] == env["vendor"]["id"]
    text = _text(at)
    # top bar: small greeting above the first name, avatar initials that open Profile
    assert re.search(r'<div class="tb-greet">Good (morning|afternoon|evening)</div><div class="tb-name">Wanjiku</div>', text)
    assert at.button(key="topbar_avatar").label == "WT"
    # Home without a score: the hero with "--" and its button, no Business health card, no applications yet
    assert '<div class="hero-score">--</div>' in text and "No applications yet" in text
    assert at.button(key="cta_score").label == "Check your score"
    assert "Business health" not in text
    assert not [b for b in at.button if b.key.startswith(("qa_", "row_breakdown"))]   # no tiles, no breakdown row
    assert [b.label for b in at.button if b.key.startswith("nav_")] == ["Home", "Score", "History", "Profile"]


RICH = toy.make_vendor(days=120, daily_in=164000 / 30)       # Low risk under the toy model: eligible up to KES 34,300


def _score(env, user, vendor=None):
    return service.run_score_check(env["conn"], user, H.Upload(H.statement_csv(vendor), "s.csv"))


def _stored_application(env, user, result):
    """An application as submit_application stores it (AppTest cannot upload a file to the Apply screen)."""
    lender = {"id": env["lender"]["id"], "org_name": "Umoja SACCO"}
    return service._insert_application(env["conn"], user, lender, service.snapshot(result))


def test_home_with_a_score_and_applications(env):
    user, conn = env["vendor"], env["conn"]
    result = _score(env, user)
    sent = [_stored_application(env, user, result) for _ in range(4)]
    at = _app(user_id=user["id"], page="home")                  # no session result: the latest saved check is used
    _no_errors(at)
    text = _text(at)
    assert f'<div class="hero-score">{result["score"]} <span>/ 850</span></div>' in text
    assert "Business health" in text
    for p in result["pillars"]:                                  # one row per area: name left, rating as coloured text
        assert components.row(p["name"], components.status_text(p["label"])) in text
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
    assert "Business health" in _text(at) and f"{result['score']} <span>/ 850</span>" in _text(at)


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
    at = _sign_in(_app(), "vendor@example.com", "wrong-password")
    _no_errors(at)
    assert auth.SIGN_IN_FAILED in _text(at) and at.session_state["page"] == "signin"


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
    assert f"{result['score']} <span>/ 850</span>" in text and "Chance of default" in text
    assert "Estimated eligibility" in text and "Up to KES 34,300" in text and "Comfortable up to KES 9,200" in text
    assert "The lender makes the final decision." in text
    assert all(p["name"] in text for p in result["pillars"])
    assert "Score over time" in text                                               # two saved checks
    assert at.button(key="to_apply").label == "Apply for a loan" and at.button(key="to_reasons").label == "See reasons"

    # Reasons: top reasons, and the what-if slider changes only the band (never the score or the limit)
    at.button(key="to_reasons").click().run()
    _no_errors(at)
    med = service.median_request()
    assert at.slider(key="loan_amount").value == int(med[0])
    before = _text(at)
    assert all(r["phrase"] in before for r in result["reasons"]) and "Test an amount" in before
    assert "Up to KES 34,300" in before
    at.slider(key="loan_amount").set_value(150000).run()
    _no_errors(at)
    after = _text(at)
    assert "KES 150,000" in after and "Outside typical range" in after and "Up to KES 34,300" in after
    band = service.affordability_band(150000, result["monthly_income"])
    assert components.status_text(band.capitalize()) in after
    assert at.session_state["result"] == result                                    # never re-scored

    # Apply: lender, amount and days (median request), the statement again, consent, one button
    at.button(key="reasons_apply").click().run()
    _no_errors(at)
    radio = at.radio(key="apply_lender")
    assert sorted(radio.options) == ["Tumaini Microfinance", "Umoja SACCO"]       # organisation names are shown
    assert (at.number_input(key="apply_amount_in").value, at.number_input(key="apply_term_in").value) == \
        (int(med[0]), int(med[1]))
    assert len(at.get("file_uploader")) == 1
    assert at.checkbox(key="apply_consent").label == "Share this summary with the lender"
    send = at.button(key="send_application")
    assert send.label == "Check eligibility and send" and send.disabled            # needs the statement and consent
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

    # History: one line per application
    at.button(key="sent_history").click().run()
    _no_errors(at)
    assert [e.label for e in at.expander] == ["Umoja SACCO  :orange[**Pending**]"]
    assert sent["ref"] in _text(at)

    # Profile: a toggle is stored; delete saved results with a confirm step; sign out
    at.button(key="nav_profile").click().run()
    _no_errors(at)
    at.toggle(key="flag_email_notifications").set_value(True).run()
    assert auth.get_user(env["conn"], uid)["email_notifications"] == 1
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
    assert components.colored_text("Not eligible right now", "Very high risk") in text
    assert "Estimated eligibility" not in text and "Up to KES" not in text
    at.button(key="see_why").click().run()
    assert at.session_state["page"] == "reasons" and "Not eligible right now" in _text(at)


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


# ---------------------------------------------------------------- design rules
def test_status_text_is_coloured_text_only():
    for label in components.STATUS_COLORS:
        s = components.status_text(label.title())
        assert "color:" in s and "font-weight:700" in s and "background" not in s.lower()
        assert re.fullmatch(r'<span class="status" style="color:#[0-9A-F]{6};font-weight:700">[^<]+</span>', s)
    for label in ("Pending", "Approved", "Declined", "Comfortable", "Stretched", "Heavy"):
        md = components.status_md(label)
        assert "background" not in md and md.startswith(":") and "**" in md
    assert "#FFD98A" in components.status_text("Moderate risk", on_hero=True)
    assert components.status_color("Pending") == "#B45309" and components.status_color("High risk") == "#C2410C"
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
