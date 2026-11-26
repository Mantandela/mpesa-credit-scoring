"""Web app entry point: the vendor, lender and admin screens.

    streamlit run app/main.py        (from the repo root, so .streamlit/config.toml is used)

Screens are routed through st.session_state["page"]; every screen declares the role it needs and the router applies
the role guard before rendering (and every lender and admin service call checks the role again, see
app/staff_service.py). Each role has its own shell: the same frame with its own nav list. Prototype: all scores come
from a model trained on simulated data.

Database: DATABASE_URL (environment or st.secrets) selects PostgreSQL, e.g. Neon; otherwise SQLite at
data/private/app.db. See docs/database.md.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app import auth, components as ui, db, errors, service, theme  # noqa: E402
from app.pages import admin, apply, history, home, lender, profile, reasons, result, score, sent, signin, signup  # noqa: E402

# page -> (render function, role required or None for the signed-out screens)
PAGES = {
    "signin": (signin.render, None),
    "signup": (signup.render, None),
    "home": (home.render, "vendor"),
    "score": (score.render, "vendor"),
    "result": (result.render, "vendor"),
    "reasons": (reasons.render, "vendor"),
    "apply": (apply.render, "vendor"),
    "sent": (sent.render, "vendor"),
    "history": (history.render, "vendor"),
    "profile": (profile.render, "vendor"),
    "lender": (lender.render_queue, "lender"),
    "lender_decided": (lender.render_decided, "lender"),
    "lender_review": (lender.render_review, "lender"),
    "lender_profile": (lender.render_profile, "lender"),
    "admin": (admin.render_overview, "admin"),
    "admin_users": (admin.render_users, "admin"),
    "admin_add": (admin.render_add_user, "admin"),
    "admin_audit": (admin.render_audit, "admin"),
    "admin_profile": (profile.render_account, "admin"),
}
# page -> the nav item shown as active; pages listed here also show the phone tab bar
NAV_PAGES = {"home": "home", "score": "score", "result": "score", "reasons": "score", "apply": "score",
             "history": "history", "profile": "profile"}
STAFF_NAV_PAGES = {"lender": "queue", "lender_decided": "decided", "lender_profile": "lprofile", "admin": "overview",
                   "admin_users": "users", "admin_add": "users", "admin_audit": "audit",
                   "admin_profile": "aprofile"}


def _active(page: str) -> str | None:
    if page == "lender_review":                       # the review belongs to the list it was opened from
        return STAFF_NAV_PAGES.get(st.session_state.get("review_from") or "lender", "queue")
    return NAV_PAGES.get(page) if page in NAV_PAGES else STAFF_NAV_PAGES.get(page)


@st.cache_resource
def _warm_up_once():
    service.warm_up()          # loads the model in a background thread so the first score is quicker
    return True


@st.cache_resource(show_spinner=False)
def _engine(url: str):
    """One engine per database per process (tables created on first use). The URL is a cache key only."""
    return db.get_engine(url)


@st.cache_resource(show_spinner=False)
def _schema_problems(url: str) -> tuple:
    """Checked once per database at start-up. An out-of-date schema is logged once for the developer (which columns;
    never the URL) and every page then shows a short card instead of failing on the first insert or select."""
    missing = tuple(db.schema_problems(_engine(url)))
    if missing:
        errors.log.error("%s Missing: %s", db.SCHEMA_OUT_OF_DATE, ", ".join(missing))
    return missing


def _error_card(iid: str, user) -> None:
    with st.container(key="card_error"):
        ui.section("Something went wrong. Please try again.")
        ui.muted(f"Incident {iid}")
        home = signin.HOME_FOR.get(user["role"], "signin") if user else "signin"
        st.button("Back to Home", key="error_home", type="primary", on_click=ui.go, args=(home,), width="stretch")


def run() -> None:
    st.session_state.pop(ui.MENU_FLAG, None)          # a full run: any menu choice has already been applied
    theme.inject()
    _warm_up_once()
    url = db.database_url()
    try:
        conn = db.connect(_engine(url))               # one connection per run, closed below
        problems = _schema_problems(url)
    except db.DatabaseUnavailable as e:
        ui.title("Not available")
        ui.alert(str(e))
        return
    if problems:
        conn.close()
        with st.container(key="card_schema"):
            ui.section(db.SCHEMA_OUT_OF_DATE)
        return
    body = st.empty()                                 # the page is drawn here, so an error can clear what was drawn
    try:
        with body.container():
            _route(conn)
    except Exception as e:                            # noqa: BLE001 - st.rerun/st.stop are BaseException, not caught
        iid = errors.report(e)                        # one log line: class, app location, incident id; no message
        body.empty()
        try:
            conn.rollback()
            user = auth.get_user(conn, st.session_state.get("user_id"))
        except Exception:                             # noqa: BLE001
            user = None
        _error_card(iid, user)
    finally:
        conn.close()


def _route(conn) -> None:
    """Pick the page for this user, apply the role guard and render it."""
    user = auth.get_user(conn, st.session_state.get("user_id"))
    if user is not None and not user["is_active"]:
        ui.sign_out()
        user = None
    page = st.session_state.get("page") or "signin"
    if page not in PAGES:
        page = "signin"
    if user is None:
        page = page if page in ("signin", "signup") else "signin"
    elif page in ("signin", "signup"):
        page = signin.HOME_FOR[user["role"]]
    st.session_state["page"] = page
    render, role = PAGES[page]
    if role is not None:
        try:
            auth.require_role(user, role)
        except auth.AccessDenied as e:
            ui.not_available(user, str(e))
            return
        # the role's shell: sidebar (laptop) or tab bar (phone), with that role's nav list
        with ui.shell(user, role, ui.NAV_FOR[role], _active(page), tabs=page in NAV_PAGES if role == "vendor" else True):
            render(conn, user)
    else:
        render(conn, user)
    st.session_state["prev_page"] = page              # the page drawn last (Reasons tilts in only when it opens)


@st.cache_resource(show_spinner=False)
def _favicon():
    return theme.page_icon()


st.set_page_config(page_title=ui.APP_NAME, page_icon=_favicon(), layout="wide", initial_sidebar_state="collapsed")
st.navigation([st.Page(run, title=ui.APP_NAME, default=True)], position="hidden").run()
