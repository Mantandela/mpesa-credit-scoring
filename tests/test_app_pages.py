"""Web app screens (app/main.py and app/pages/) through streamlit.testing.v1.AppTest.

AppTest cannot drive the file uploader, so the end-to-end test scores the synthetic statement through the service
(exactly what the Score screen calls) and continues in the app from the Result screen.
"""
import re

import pytest
from streamlit.testing.v1 import AppTest

import app_helpers as H
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
    # Home always shows the hero ("--" without a score), the quick actions and the latest application
    assert '<div class="hero-score">--</div>' in text and "No applications yet" in text
    assert [at.button(key=k).label for k in ("qa_score", "qa_loan", "qa_history", "qa_more")] == \
        ["Check score", "Loan check", "History", "More"]
    assert [b.label for b in at.button if b.key.startswith("nav_")] == ["Home", "Score", "History", "Profile"]
    assert at.button(key="cta_score").label == "Check your score"                 # no score yet: one call to action


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

    # the Score screen: prefilled with the median request
    at.button(key="nav_score").click().run()
    _no_errors(at)
    med = service.median_request()
    assert (at.number_input(key="req_amount").value, at.number_input(key="req_term").value) == (int(med[0]), int(med[1]))
    assert at.button(key="get_score").disabled                                     # nothing uploaded yet

    # score twice (what "Get my score" calls), then continue on the Result screen
    service.run_score_check(env["conn"], user, H.Upload(H.statement_csv(), "s.csv"), 5000, 14)
    result = service.run_score_check(env["conn"], user, H.Upload(H.statement_csv(), "s.csv"), 7500, 14)
    at.session_state["result"] = result
    at.session_state["page"] = "result"
    at.run()
    _no_errors(at)
    text = _text(at)
    assert "Prototype, trained on simulated data" in text
    assert f"{result['score']} <span>/ 850</span>" in text and "Chance of default" in text
    assert all(p["name"] in text for p in result["pillars"])
    assert "Score over time" in text                                               # two saved checks

    # Reasons and loan: the slider changes only the band
    at.button(key="to_reasons").click().run()
    _no_errors(at)
    assert at.slider(key="loan_amount").value == 7500
    before = _text(at)
    assert all(r["phrase"] in before for r in result["reasons"])
    at.slider(key="loan_amount").set_value(150000).run()
    _no_errors(at)
    after = _text(at)
    assert "KES 150,000" in after and "Outside typical range" in after
    band = service.affordability_band(150000, result["monthly_income"])
    assert components.status_text(band.capitalize()) in after
    assert at.session_state["result"] == result                                    # never re-scored

    # Apply to Umoja SACCO
    at.button(key="to_apply").click().run()
    _no_errors(at)
    radio = at.radio(key="apply_lender")
    assert sorted(radio.options) == ["Tumaini Microfinance", "Umoja SACCO"]       # organisation names are shown
    radio.set_value(env["lender"]["id"])
    assert at.button(key="send_application").disabled                              # consent first
    at.checkbox(key="apply_consent").check().run()
    at.button(key="send_application").click().run()
    _no_errors(at)
    assert at.session_state["page"] == "sent"
    sent = at.session_state["sent"]
    text = _text(at)
    assert "Application sent" in text and "Umoja SACCO" in text and sent["ref"] in text and "Pending" in text
    snap = H.rows(env["conn"], "applications", ref=sent["ref"])[0]["snapshot_json"]
    assert '"amount": 150000.0' in snap                                            # the slider amount is the request

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
    result = service.run_score_check(env["conn"], user, H.Upload(H.statement_csv(), "s.csv"), 5000, 14)
    service.create_application(env["conn"], user, env["lender"]["id"], result, consent=True)
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
