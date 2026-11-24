"""Small building blocks shared by the pages: status text, icons, top bar, hero card, rows, navigation.

Status is always shown as bold coloured TEXT (status_text / status_md). Never a tinted background, pill or badge.
"""
from datetime import datetime, timedelta, timezone
from html import escape

import streamlit as st

from app import theme

APP_NAME = "Alama"
STATUS_COLORS = {
    # applications
    "pending": "#B45309", "approved": "#067647", "declined": "#B42318",
    # risk tiers (with and without " risk")
    "low": "#067647", "moderate": "#B45309", "high": "#C2410C", "very high": "#B42318",
    "low risk": "#067647", "moderate risk": "#B45309", "high risk": "#C2410C", "very high risk": "#B42318",
    # pillar ratings
    "strong": "#067647", "good": "#067647", "fair": "#B45309", "weak": "#B42318",
    # affordability
    "comfortable": "#067647", "stretched": "#B45309", "heavy": "#B42318", "unknown": "#6B6B85",
    # reasons
    "raises risk": "#B42318", "lowers risk": "#067647",
}
HERO_TIER_COLOR = "#FFD98A"
# Streamlit markdown colour names; .streamlit/config.toml sets their text colours to exactly these hex values
_MD_NAMES = {"#B45309": "orange", "#067647": "green", "#B42318": "red", "#6B6B85": "gray"}
NAIROBI = timezone(timedelta(hours=3))


def status_color(label: str, on_hero: bool = False) -> str:
    if on_hero:
        return HERO_TIER_COLOR
    return STATUS_COLORS[str(label).strip().lower()]


def status_text(label: str, on_hero: bool = False) -> str:
    """Bold coloured text for a status, tier, rating, band or reason direction. Text colour only, no background."""
    return (f'<span class="status" style="color:{status_color(label, on_hero)};font-weight:700">'
            f'{escape(str(label))}</span>')


def colored_text(text: str, like: str) -> str:
    """Any text in the colour of a status (e.g. "Not eligible right now" in the tier's colour). Text colour only."""
    return f'<span class="status" style="color:{status_color(like)};font-weight:700">{escape(str(text))}</span>'


def eligibility_lines(el: dict, tier: str) -> str:
    """The eligibility block shared by Result and Reasons (HTML)."""
    if el["status"] == "eligible":
        return (f'<div class="elig-max">Up to {money(el["max_amount"])}</div>'
                f'<div class="elig-comf">Comfortable up to {money(el["comfortable_amount"])}</div>')
    if el["status"] == "not_eligible":
        return f'<div class="elig-no">{colored_text("Not eligible right now", tier)}</div>'
    return '<div class="elig-no" style="color:#6B6B85;font-weight:700">Not enough income data</div>'


def status_md(label: str) -> str:
    """The same status as Streamlit markdown (for widget and expander labels, which cannot hold HTML)."""
    return f":{_MD_NAMES[status_color(label)]}[**{label}**]"


def icon(name: str, color: str = theme.PURPLE, size: int = 24, label: str | None = None, stroke: float = 2) -> str:
    """Inline SVG line icon. Decorative unless a label is given."""
    a11y = f'role="img" aria-label="{escape(label)}"' if label else 'aria-hidden="true"'
    return theme.svg(name, color, size, stroke).replace("<svg ", f"<svg {a11y} ", 1)


def html(s: str, **kw) -> None:
    st.markdown(s, unsafe_allow_html=True, **kw)


def title(text: str, sub: str | None = None) -> None:
    html(f'<div class="title">{escape(text)}</div>' + (f'<div class="caption">{escape(sub)}</div>' if sub else ""))


def section(text: str) -> None:
    html(f'<div class="section">{escape(text)}</div>')


def muted(text: str) -> None:
    html(f'<div class="muted">{escape(text)}</div>')


def alert(text: str) -> None:
    """An error line for forms (red text, read out by screen readers)."""
    html(f'<div class="alert-text" role="alert">{escape(text)}</div>')


def row(key: str, value_html: str, lead_html: str = "") -> str:
    return f'<div class="row"><span class="k">{lead_html}{escape(key)}</span><span class="v">{value_html}</span></div>'


def reason_row(direction: str, phrase: str) -> str:
    return f'<div class="reason"><span class="dir">{status_text(direction)}</span><span class="txt">{escape(phrase)}</span></div>'


def money(x) -> str:
    return f"KES {float(x):,.0f}"


def pct(x, digits: int = 1) -> str:
    return f"{100 * float(x):.{digits}f}%"


def short_date(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(NAIROBI).strftime("%d %b %Y")


def greeting(now: datetime | None = None) -> str:
    h = (now or datetime.now(NAIROBI)).astimezone(NAIROBI).hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def go(page: str, **state) -> None:
    """Button callback: switch screen (and set any session values) before the next run."""
    st.session_state["page"] = page
    for k, v in state.items():
        st.session_state[k] = v


def sign_out() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state["page"] = "signin"


# ------------------------------------------------------------------ larger blocks
def _icon_box(name: str, label: str) -> str:
    return f'<div class="icon-box">{icon(name, theme.INK, 22, label)}</div>'


MENU_ITEMS = (  # key, label, page (None = sign out); icons are in theme.MENU_ICONS
    ("home", "Home", "home"),
    ("score", "Check score", "score"),
    ("apply", "Apply for a loan", "apply"),
    ("history", "My applications", "history"),
    ("profile", "Profile", "profile"),
    ("signout", "Sign out", None),
)


MENU_FLAG = "menu_navigated"


def _menu_choose(page) -> None:
    """Menu item callback. Callbacks always fire, also when the dialog is not drawn again on the next run."""
    if page is None:
        sign_out()
    else:
        go(page)
    st.session_state[MENU_FLAG] = True


@st.dialog("Menu", width="small")
def menu_dialog() -> None:
    """The app menu. A click inside a dialog reruns only the dialog, so after a choice it asks for a full rerun,
    which draws the new page and closes the dialog (main.py clears the flag on every full run)."""
    if st.session_state.pop(MENU_FLAG, False):
        st.rerun()
    for key, label, page in MENU_ITEMS:
        st.button(label, key=f"menu_{key}", on_click=_menu_choose, args=(page,), width="stretch")


def top_bar(user: dict, title_text: str | None = None, caption: str | None = None, home: bool = False) -> None:
    """Menu button (opens the menu dialog), title block, bell icon (visual only) and the avatar (opens Profile)."""
    with st.container(horizontal=True, key="topbar", vertical_alignment="center", gap="small"):
        # a real button: its visible label is hidden by CSS but stays its accessible name, "Menu"
        if st.button("Menu", key="topbar_menu", width="content"):
            menu_dialog()
        if home:
            first = (user.get("name") or "").split()[0] if user.get("name") else ""
            block = f'<div class="tb-greet">{greeting()}</div><div class="tb-name">{escape(first)}</div>'
        elif title_text:
            block = f'<div class="tb-title">{escape(title_text)}</div>' + (
                f'<div class="tb-caption">{escape(caption)}</div>' if caption else "")
        else:
            block = ""
        html(f"<div>{block}</div>", width="stretch")
        html(_icon_box("bell", "Notifications"), width="content")
        st.button(initials(user.get("name", "")), key="topbar_avatar", on_click=go, args=("profile",), width="content")


def hero(score=None, tier: str | None = None, line: str | None = None, cta: bool = False) -> None:
    """Gradient score card. Without a score it shows "--" and, with cta=True, a "Check your score" button."""
    with st.container(key="hero"):
        if score is None:
            html('<div class="hero-label">Your credit score</div><div class="hero-score">--</div>')
            if cta:
                st.button("Check your score", key="cta_score", on_click=go, args=("score",), width="stretch")
            return
        extra = f'<div class="hero-line">{escape(line)}</div>' if line else ""
        html(f'<div role="group" aria-label="Your credit score"><div class="hero-label">Your credit score</div>'
             f'<div class="hero-score">{int(score)} <span>/ 850</span></div>'
             f'<div class="hero-tier">{status_text(tier, on_hero=True)}</div>{extra}</div>')


# ------------------------------------------------------------------ sign in / create account
AUTH_HEADLINE = "Know your credit score from your M-Pesa statement"
AUTH_POINTS = ("Score an Excel or CSV statement in seconds", "See what lifts or drags your score",
               "Find out how much you can borrow")
AUTH_FOOTER = "Your statement is read once and never stored."


def auth_band() -> None:
    """The navy header band of Sign in and Create account (identical on both, so switching does not shift the
    layout). Also injects the auth styles (theme.AUTH_CSS)."""
    theme.inject_auth()
    points = "".join(f'<li>{icon("check_circle", theme.AUTH_TICK, 16)}<span>{escape(p)}</span></li>' for p in AUTH_POINTS)
    headline = escape(AUTH_HEADLINE).replace("M-Pesa", '<span class="nowrap">M-Pesa</span>')   # never break at the hyphen
    html(f'<div class="auth-band"><div class="auth-brand"><span class="auth-logo">{icon("logo", "#FFFFFF", 22)}</span>'
         f'<span>{escape(APP_NAME)}</span></div><div class="auth-headline">{headline}</div>'
         f'<ul class="auth-points">{points}</ul></div>')


def auth_title(heading: str, sub: str) -> None:
    html(f'<div class="auth-title" role="heading" aria-level="1">{escape(heading)}</div>'
         f'<div class="auth-sub">{escape(sub)}</div>')


def auth_error(text: str, where=st) -> None:
    """A sign-in or sign-up message: red text with a small icon, no box (read out by screen readers)."""
    where.markdown(f'<div class="auth-error" role="alert">{icon("alert", theme.ERROR, 16)}<span>{escape(text)}</span></div>',
                   unsafe_allow_html=True)


def auth_footer() -> None:
    html(f'<div class="auth-foot">{icon("lock", theme.MUTED, 14)}<span>{escape(AUTH_FOOTER)}</span></div>')


NAV_TABS = (("home", "Home"), ("score", "Score"), ("history", "History"), ("profile", "Profile"))


def bottom_nav(active: str) -> None:
    """Vendor tab bar, fixed to the bottom of the frame (CSS in theme.py; icons are SVG data URIs there)."""
    html(theme.active_tab_css(active))
    with st.container(horizontal=True, key="bottom_nav"):
        for page, label in NAV_TABS:
            st.button(label, key=f"nav_{page}", on_click=go, args=(page,), width="stretch")
