"""Small building blocks shared by the pages: status text, icons, hero card, rows, navigation.

Status is always shown as bold coloured TEXT (status_text / status_md). Never a tinted background, pill or badge.
"""
from datetime import datetime, timedelta, timezone
from html import escape

import streamlit as st

from app import theme

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

ICONS = {
    "logo": '<path d="M4 17l5-5 4 4 7-8" /><path d="M15 8h5v5" />',
    "check": '<circle cx="12" cy="12" r="9" /><path d="M8 12.5l2.5 2.5L16 9.5" />',
    "upload": '<path d="M12 16V4" /><path d="M7 9l5-5 5 5" /><path d="M5 20h14" />',
    "chevron": '<path d="M9 6l6 6-6 6" />',
}


def status_color(label: str, on_hero: bool = False) -> str:
    if on_hero:
        return HERO_TIER_COLOR
    return STATUS_COLORS[str(label).strip().lower()]


def status_text(label: str, on_hero: bool = False) -> str:
    """Bold coloured text for a status, tier, rating, band or reason direction. Text colour only, no background."""
    return (f'<span class="status" style="color:{status_color(label, on_hero)};font-weight:700">'
            f'{escape(str(label))}</span>')


def status_md(label: str) -> str:
    """The same status as Streamlit markdown (for widget and expander labels, which cannot hold HTML)."""
    return f":{_MD_NAMES[status_color(label)]}[**{label}**]"


def icon(name: str, color: str = theme.PURPLE, size: int = 24, label: str | None = None) -> str:
    """Inline SVG line icon. Decorative unless a label is given."""
    a11y = f'role="img" aria-label="{escape(label)}"' if label else 'aria-hidden="true"'
    return (f'<svg {a11y} width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def html(s: str) -> None:
    st.markdown(s, unsafe_allow_html=True)


def title(text: str, sub: str | None = None) -> None:
    html(f'<div class="title">{escape(text)}</div>' + (f'<div class="subtitle">{escape(sub)}</div>' if sub else ""))


def section(text: str) -> None:
    html(f'<div class="section">{escape(text)}</div>')


def muted(text: str) -> None:
    html(f'<div class="muted">{escape(text)}</div>')


def alert(text: str) -> None:
    """An error line for forms (red text, read out by screen readers)."""
    html(f'<div class="alert-text" role="alert">{escape(text)}</div>')


def row(key: str, value_html: str) -> str:
    return f'<div class="row"><span class="k">{escape(key)}</span><span class="v">{value_html}</span></div>'


def money(x) -> str:
    return f"KES {float(x):,.0f}"


def pct(x, digits: int = 1) -> str:
    return f"{100 * float(x):.{digits}f}%"


def short_date(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(NAIROBI).strftime("%d %b %Y")


def greeting(now: datetime | None = None) -> str:
    h = (now or datetime.now(NAIROBI)).astimezone(NAIROBI).hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def hero(score: int, tier: str, line: str | None = None) -> None:
    extra = f'<div class="line">{escape(line)}</div>' if line else ""
    html(f'<div class="hero" role="group" aria-label="Your credit score">'
         f'<div class="score">{int(score)} <span>/ 850</span></div>'
         f'<div class="tier">{status_text(tier, on_hero=True)}</div>{extra}</div>')


def auth_header(heading: str, sub: str) -> None:
    html(f'<div class="auth-head"><span class="logo">{icon("logo", theme.PURPLE, 26)}</span>'
         f'<div class="welcome">{escape(heading)}</div><div class="sub">{escape(sub)}</div></div>')


def go(page: str, **state) -> None:
    """Button callback: switch screen (and set any session values) before the next run."""
    st.session_state["page"] = page
    for k, v in state.items():
        st.session_state[k] = v


def sign_out() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state["page"] = "signin"


NAV_TABS = (("home", "Home", ":material/home:"), ("score", "Score", ":material/speed:"),
            ("history", "History", ":material/receipt_long:"), ("profile", "Profile", ":material/person:"))


def bottom_nav(active: str) -> None:
    """Vendor tab bar, fixed to the bottom of the column (CSS in theme.py)."""
    html(theme.active_tab_css(active))
    with st.container(key="bottom_nav"):
        cols = st.columns(len(NAV_TABS))
        for col, (page, label, ico) in zip(cols, NAV_TABS):
            with col:
                st.button(label, key=f"nav_{page}", icon=ico, on_click=go, args=(page,), width="stretch")
