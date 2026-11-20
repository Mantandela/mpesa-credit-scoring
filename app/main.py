"""Web app entry point (stage 1: vendor screens; lender and admin are stubs).

    streamlit run app/main.py        (from the repo root, so .streamlit/config.toml is used)

Screens are routed through st.session_state["page"]; every screen declares the role it needs and the router applies
the role guard before rendering. Prototype: all scores come from a model trained on simulated data.

Database: DATABASE_URL (environment or st.secrets) selects PostgreSQL, e.g. Neon; otherwise SQLite at
data/private/app.db. See docs/database.md.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app import auth, components as ui, db, service, theme  # noqa: E402
from app.pages import apply, history, home, profile, reasons, result, score, sent, signin, signup, staff  # noqa: E402

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
    "lender": (staff.render_lender, "lender"),
    "admin": (staff.render_admin, "admin"),
}
NAV_PAGES = {"home": "home", "score": "score", "result": "score", "reasons": "score", "apply": "score",
             "history": "history", "profile": "profile"}


@st.cache_resource
def _warm_up_once():
    service.warm_up()          # loads the model in a background thread so the first score is quicker
    return True


@st.cache_resource(show_spinner=False)
def _engine(url: str):
    """One engine per database per process (tables created on first use). The URL is a cache key only."""
    return db.get_engine(url)


def run() -> None:
    st.session_state.pop(ui.MENU_FLAG, None)          # a full run: any menu choice has already been applied
    theme.inject()
    _warm_up_once()
    try:
        conn = db.connect(_engine(db.database_url()))    # one connection per run, closed below
    except db.DatabaseUnavailable as e:
        ui.title("Not available")
        ui.alert(str(e))
        return
    try:
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
                ui.title("Not available")
                ui.alert(str(e))
                st.button("Go to my home", key="go_home", on_click=ui.go, args=(signin.HOME_FOR[user["role"]],))
                return
        render(conn, user)
        if role == "vendor" and page in NAV_PAGES:
            ui.bottom_nav(NAV_PAGES[page])
    finally:
        conn.close()


@st.cache_resource(show_spinner=False)
def _favicon():
    return theme.favicon()


st.set_page_config(page_title=ui.APP_NAME, page_icon=_favicon(), layout="centered", initial_sidebar_state="collapsed")
st.navigation([st.Page(run, title=ui.APP_NAME, default=True)], position="hidden").run()
