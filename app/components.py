"""Building blocks shared by the pages: status text, icons, the responsive shell (sidebar, page header, tab bar), the
score card and its chart, the estimated limit card, Business health, and the sign-in / create-account pieces.

Status is always shown as bold coloured TEXT (status_text / status_md), never as a tinted background, pill or badge.
One render per page: the same elements are laid out as a phone view or a laptop view by the CSS in theme.py.
"""
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from html import escape

import streamlit as st

from app import service, theme  # noqa: F401 - service puts src/ on sys.path for scoring

import scoring as SC  # noqa: E402

APP_NAME = "Alama"
GREEN, AMBER, RED, MUTED_HEX = "#067647", "#B45309", "#B42318", "#6B6B85"
STATUS_COLORS = {
    # applications
    "pending": AMBER, "approved": GREEN, "declined": RED,
    # risk tiers (with and without " risk")
    "low": GREEN, "moderate": AMBER, "high": RED, "very high": RED,
    "low risk": GREEN, "moderate risk": AMBER, "high risk": RED, "very high risk": RED,
    # pillar ratings
    "strong": GREEN, "good": GREEN, "fair": AMBER, "weak": RED,
    # affordability
    "comfortable": GREEN, "stretched": AMBER, "heavy": RED, "unknown": MUTED_HEX,
    # reasons
    "raises risk": RED, "lowers risk": GREEN,
}
# Streamlit markdown colour names; .streamlit/config.toml sets their text colours to exactly these hex values
_MD_NAMES = {AMBER: "orange", GREEN: "green", RED: "red", MUTED_HEX: "gray"}
NAIROBI = timezone(timedelta(hours=3))


def status_color(label: str) -> str:
    return STATUS_COLORS[str(label).strip().lower()]


def status_text(label: str) -> str:
    """Bold coloured text for a status, tier, rating, band or reason direction. Text colour only, no background."""
    return f'<span class="status" style="color:{status_color(label)};font-weight:700">{escape(str(label))}</span>'


def colored_text(text: str, like: str) -> str:
    """Any text in the colour of a status (e.g. "Not eligible right now" in red). Text colour only."""
    return f'<span class="status" style="color:{status_color(like)};font-weight:700">{escape(str(text))}</span>'


def status_md(label: str) -> str:
    """The same status as Streamlit markdown (for widget and expander labels, which cannot hold HTML)."""
    return f":{_MD_NAMES[status_color(label)]}[**{label}**]"


def md_escape(s: str) -> str:
    """Plain text inside a Streamlit markdown label (button and expander labels)."""
    return "".join("\\" + c if c in "\\`*_[]()#+-.!:|<>~$" else c for c in str(s))


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
    """An error line (red text with a small icon, no box; read out by screen readers)."""
    html(f'<div class="alert-text" role="alert">{icon("alert", RED, 16)}<span>{escape(text)}</span></div>')


def row(key: str, value_html: str, lead_html: str = "") -> str:
    return f'<div class="row"><span class="k">{lead_html}{escape(key)}</span><span class="v">{value_html}</span></div>'


def reason_row(direction: str, phrase: str) -> str:
    return f'<div class="reason"><span class="txt">{escape(phrase)}</span><span class="dir">{status_text(direction)}</span></div>'


def money(x) -> str:
    return f"KES {float(x):,.0f}"


def pct(x, digits: int = 1) -> str:
    return f"{100 * float(x):.{digits}f}%"


def _local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(NAIROBI)


def short_date(iso: str) -> str:
    return _local(iso).strftime("%d %b %Y")


def date_time(iso: str) -> str:
    return _local(iso).strftime("%d %b %Y, %H:%M")


def greeting(now: datetime | None = None) -> str:
    h = (now or datetime.now(NAIROBI)).astimezone(NAIROBI).hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def first_name(user: dict) -> str:
    return (user.get("name") or "").split()[0] if (user.get("name") or "").split() else ""


def go(page: str, **state) -> None:
    """Button callback: switch screen (and set any session values) before the next run."""
    st.session_state["page"] = page
    for k, v in state.items():
        st.session_state[k] = v


def sign_out() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state["page"] = "signin"


# ------------------------------------------------------------------ the shell: one nav list, two navigation styles
NavItem = namedtuple("NavItem", "key label icon page")
VENDOR_NAV = (
    NavItem("home", "Home", "home", "home"),
    NavItem("score", "Score", "gauge", "score"),
    NavItem("history", "History", "receipt", "history"),
    NavItem("profile", "Profile", "user", "profile"),
)

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
    """The app menu (phone view). A click inside a dialog reruns only the dialog, so after a choice it asks for a full
    rerun, which draws the new page and closes the dialog (main.py clears the flag on every full run)."""
    if st.session_state.pop(MENU_FLAG, False):
        st.rerun()
    for key, label, page in MENU_ITEMS:
        st.button(label, key=f"menu_{key}", on_click=_menu_choose, args=(page,), width="stretch")


def _sidebar(user: dict, role: str, nav, active: str | None) -> None:
    """Laptop sidebar (hidden by CSS below 1024px): logo tile and app name, the nav items, the user and Sign out."""
    with st.container(key="shell_side"):
        html(f'<div class="side-brand"><span class="side-logo">{icon("logo", "#FFFFFF", 20)}</span>'
             f'<span>{escape(APP_NAME)}</span></div>')
        with st.container(key="side_nav"):
            html(f'<div class="sr-only">{escape(role.capitalize())} navigation</div>')
            for item in nav:
                st.button(item.label, key=f"sidenav_{item.key}", on_click=go, args=(item.page,), width="stretch")
        with st.container(key="side_user"):
            html(f'<div class="side-user"><span class="side-avatar" aria-hidden="true">{escape(initials(user["name"]))}'
                 f'</span><span class="side-name">{escape(user["name"])}</span></div>')
            st.button("Sign out", key="side_signout", type="tertiary", on_click=sign_out)


def bottom_nav(nav, active: str | None) -> None:
    """Phone tab bar, fixed to the bottom of the screen (hidden by CSS from 1024px)."""
    with st.container(horizontal=True, key="bottom_nav"):
        for item in nav:
            st.button(item.label, key=f"nav_{item.key}", on_click=go, args=(item.page,), width="stretch")


@contextmanager
def shell(user: dict, role: str, nav, active: str | None, tabs: bool = True):
    """The app frame around one page: the laptop sidebar, the content area, and the phone tab bar. `nav` is a list of
    NavItem (the same list drives both navigation styles), `active` the key of the current item. Reusable for the
    lender and admin shells with their own nav lists."""
    html(theme.nav_css(nav, active))
    _sidebar(user, role, nav, active)
    with st.container(key="shell_main"):
        yield
    if tabs:
        bottom_nav(nav, active)


def page_header(user: dict, title_text: str, sub: str | None = None, actions=()) -> None:
    """Page header. Phone: menu button, title, avatar (actions on a line below). Laptop: small grey subtitle above the
    26px title, actions on the right (menu and avatar hidden: the sidebar has them).
    actions: (label, key, page, "primary" | "secondary")."""
    with st.container(horizontal=True, key="page_head", vertical_alignment="center", gap="small"):
        # a real button: its visible label is hidden by CSS but stays its accessible name, "Menu"
        if st.button("Menu", key="topbar_menu", width="content"):
            menu_dialog()
        sub_html = f'<div class="ph-sub">{escape(sub)}</div>' if sub else ""
        html(f'<div class="ph-text">{sub_html}<div class="ph-title" role="heading" aria-level="1">'
             f'{escape(title_text)}</div></div>', width="stretch")
        st.button(initials(user.get("name", "")), key="topbar_avatar", on_click=go, args=("profile",), width="content")
        if actions:
            with st.container(horizontal=True, key="head_actions", gap="small"):
                for label, key, page, kind in actions:
                    st.button(label, key=key, type=kind, on_click=go, args=(page,))


def two_columns(name: str, kind: str = "even") -> tuple:
    """Two columns side by side from 1024px, stacked below. kind: "fixed" (left about 420px), "even" (halves),
    "rev" (halves; the first column is drawn on the RIGHT on a laptop and comes first on a phone)."""
    with st.container(key=f"grid_{kind}_{name}"):
        a, b = st.container(key=f"col_{name}_a"), st.container(key=f"col_{name}_b")
    return a, b


# ------------------------------------------------------------------ score chart
CHART_W, CHART_H = 360, 200
PLOT_L, PLOT_R, PLOT_T, PLOT_B = 22, 292, 34, 158
ZONE_WORDS = {"Low risk": "Low", "Moderate risk": "Moderate", "High risk": "High", "Very high risk": "Very high"}


def tier_boundaries() -> list:
    """[(score, tier above the line, tier below)] from scoring.TIER_BANDS converted with pd_to_score (never
    hard-coded): with the current bands 660, 598 and 545."""
    bands = SC.TIER_BANDS
    return [(int(SC.pd_to_score(upper)), name, nxt) for (upper, name), (_, nxt) in zip(bands, bands[1:])]


def _y_range(scores: list, lines: list) -> tuple:
    lo, hi = min(scores), max(scores)
    below, above = [b for b in lines if b <= lo], [b for b in lines if b >= hi]
    lo = min(lo, max(below)) if below else lo                # the nearest zone line under the lowest score
    hi = max(hi, min(above)) if above else hi                # and over the highest
    if hi - lo < 60:                                         # never zoom in so far that small changes look large
        mid = (hi + lo) / 2
        lo, hi = mid - 30, mid + 30
    pad = max(10.0, 0.12 * (hi - lo))
    return lo - pad, hi + pad


def _trend_words(scores: list) -> str:
    if len(scores) == 1:
        return f"one check, score {scores[0]}"
    first, last = scores[0], scores[-1]
    move = (f"up from {first} to {last}" if last > first else f"down from {first} to {last}" if last < first
            else f"unchanged at {last}")
    return f"last {len(scores)} checks, {move}"


def score_chart(points: list, tier: str) -> str:
    """Inline SVG line chart of the last checks (oldest left; higher score = higher on the chart) with dashed zone lines
    at the tier boundaries, coloured zone names at the right edge, the latest point larger with an outline in its
    tier's colour. points: [(created_at ISO, score)], oldest first. Text outside the chart stays outside the figure."""
    if not points:
        return ""
    scores = [int(s) for _, s in points]
    bounds = tier_boundaries()
    lo, hi = _y_range(scores, [b for b, _, _ in bounds])
    y = lambda s: PLOT_T + (hi - s) / (hi - lo) * (PLOT_B - PLOT_T)          # noqa: E731
    n = len(points)
    xs = [(PLOT_L + PLOT_R) / 2] if n == 1 else [PLOT_L + i * (PLOT_R - PLOT_L) / (n - 1) for i in range(n)]
    ys = [y(s) for s in scores]
    out = []
    # zones: dashed lines and coloured names
    edges = [hi] + [b for b, _, _ in bounds] + [lo]
    names = [bounds[0][1]] + [below for _, _, below in bounds]
    for i, name in enumerate(names):
        top, bottom = min(edges[i], hi), max(edges[i + 1], lo)
        if top - bottom <= 0:
            continue
        if y(bottom) - y(top) >= 13:
            out.append(f'<text x="{CHART_W - 2}" y="{(y(top) + y(bottom)) / 2 + 4:.1f}" text-anchor="end" font-size="11" '
                       f'font-weight="700" fill="{status_color(name)}">{ZONE_WORDS[name]}</text>')
    for b, _, _ in bounds:
        if lo < b < hi:
            out.append(f'<line x1="0" x2="{PLOT_R + 14}" y1="{y(b):.1f}" y2="{y(b):.1f}" stroke="#A79CCF" '
                       f'stroke-width="1" stroke-dasharray="4 4"/>')
    # area and line
    if n > 1:
        line = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in zip(xs, ys))
        out.append(f'<polygon points="{xs[0]:.1f},{PLOT_B + 6} {line} {xs[-1]:.1f},{PLOT_B + 6}" fill="#EFEAFB"/>')
        out.append(f'<polyline points="{line}" fill="none" stroke="{theme.PURPLE}" stroke-width="2.5" '
                   'stroke-linejoin="round" stroke-linecap="round"/>')
    # points, scores above them, dates under the chart
    days = [_local(iso).strftime("%d %b") for iso, _ in points]
    with_time = len(set(days)) < len(days)
    for i, ((iso, _), x, yy, s) in enumerate(zip(points, xs, ys, scores)):
        last = i == n - 1
        if last:
            out.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="6.5" fill="#FFFFFF" stroke="{status_color(tier)}" '
                       'stroke-width="3"/>')
            out.append(f'<text x="{x:.1f}" y="{yy - 13:.1f}" text-anchor="middle" font-size="14" font-weight="700" '
                       f'fill="{theme.INK}">{s}</text>')
        else:
            out.append(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="4" fill="{theme.PURPLE}"/>')
            out.append(f'<text x="{x:.1f}" y="{yy - 10:.1f}" text-anchor="middle" font-size="11" '
                       f'fill="{theme.MUTED}">{s}</text>')
        out.append(f'<text x="{x:.1f}" y="{PLOT_B + 24}" text-anchor="middle" font-size="11" fill="{theme.MUTED}">'
                   f'{days[i]}</text>')
        if with_time:
            out.append(f'<text x="{x:.1f}" y="{PLOT_B + 37}" text-anchor="middle" font-size="10" fill="{theme.MUTED}">'
                       f'{_local(iso).strftime("%H:%M")}</text>')
    label = (f"Score chart, {_trend_words(scores)}. Your latest score is in the {tier} zone.")
    return (f'<div class="score-chart"><svg role="img" aria-label="{escape(label)}" viewBox="0 0 {CHART_W} {CHART_H}" '
            f'width="100%" xmlns="http://www.w3.org/2000/svg" font-family="Roboto, sans-serif">{"".join(out)}</svg></div>')


# ------------------------------------------------------------------ cards shared by Home and Result
def no_score_card() -> None:
    """The only card on Home (and Result, Reasons) before the first check."""
    with st.container(key="card_noscore"):
        html(f'<div class="noscore"><span class="icon-circle">{icon("gauge", theme.PURPLE, 26)}</span>'
             '<div class="section">See your credit score</div>'
             '<div class="muted">Upload your M-Pesa statement to see your score, what shapes it and how much you '
             'could borrow.</div></div>')
        st.button("Check score", key="cta_score", type="primary", on_click=go, args=("score",), width="stretch")


def score_card(result: dict, points: list) -> None:
    """Score, estimated default risk, the score chart and "See reasons". No tier name under the score."""
    with st.container(key="card_score"):
        html(f'<div role="group" aria-label="Your score"><div class="sc-label">Your score</div>'
             f'<div class="sc-score">{int(result["score"])}<span class="sc-of">out of 850</span></div>'
             f'<div class="sc-pd">Estimated default risk {pct(result["pd"])}</div></div>'
             + score_chart(points, result["tier"]))
        st.button("See reasons", key="to_reasons", on_click=go, args=("reasons",), width="stretch")


def limit_lines(el: dict) -> str:
    """The estimated limit line and its caption (HTML)."""
    if el["status"] == "eligible":
        return (f'<div class="lc-limit">Estimated limit: Up to {money(el["max_amount"])}</div>'
                f'<div class="lc-sub">Comfortable up to {money(el["comfortable_amount"])} · the lender makes the final '
                'decision</div>')
    if el["status"] == "not_eligible":
        return f'<div class="lc-limit">{colored_text("Not eligible right now", "declined")}</div>'
    return '<div class="lc-limit lc-unknown">Not enough income data</div>'


def limit_card(result: dict) -> None:
    """Monthly inflow and transactions used, then the estimated limit."""
    inc, tx = result.get("monthly_income"), result.get("rows_read")
    inflow = f"{money(inc)}/mo" if inc else "not found"
    with st.container(key="card_limit"):
        html(f'<div class="lc-stats"><span>Inflow <b>{inflow}</b></span>'
             f'<span>Tx <b>{int(tx) if tx is not None else "-"}</b></span></div><div class="lc-rule"></div>'
             + limit_lines(result["eligibility"]))


def drags_card(result: dict) -> None:
    """Up to three reasons that raise risk; nothing when there are none."""
    drags = [r for r in result["reasons"] if r["direction"] == "Raises risk"][:3]
    if not drags:
        return
    with st.container(key="card_drags"):
        section("Top score drags")
        html("".join(reason_row(r["direction"], r["phrase"]) for r in drags))


PILLAR_HELP = {
    "Income stability": "How steady your sales are from week to week, and how many days you trade.",
    "Cash flow buffer": "How much money stays in your M-Pesa account after you pay out.",
    "Borrowing distress": "How often you use Fuliza, how fast you repay it and how many payments fail.",
    "Affordability": "How a typical small loan compares with your monthly income.",
    "Obligations": "How regularly you pay bills and suppliers.",
    "History and growth": "How long your statement goes back, and whether your sales are rising.",
    "Network": "How many different customers pay you, and how much comes in through your till.",
}
RATING_ICONS = {"weak": "triangle", "fair": "alert", "good": "check_circle", "strong": "check_circle"}
HEALTH_FILTERS = ("all", "work", "good")


def _pillars_in_order(pillars: list) -> list:
    order = list(service.PILLAR_NAMES)
    return sorted(pillars, key=lambda p: order.index(p["key"]) if p.get("key") in order else len(order))


def health_rows(pillars: list) -> str:
    """One expandable row per area (details/summary): name, rating as coloured text with an icon, chevron; a one-line
    explanation when open."""
    out = []
    for p in pillars:
        color = status_color(p["label"])
        out.append(f'<details class="xrow"><summary><span class="x-main">{escape(p["name"])}</span>'
                   f'<span class="x-side">{icon(RATING_ICONS[p["label"].lower()], color, 16)}{status_text(p["label"])}'
                   f'</span><span class="x-chev">{icon("chevron", theme.MUTED, 18)}</span></summary>'
                   f'<div class="x-body">{escape(PILLAR_HELP.get(p["name"], ""))}</div></details>')
    return "".join(out)


def health_card(result: dict) -> None:
    """Business health: the seven areas in the model's order, with filter chips (a pills widget: choosing one reruns
    the page with everything else in session state unchanged)."""
    pillars = _pillars_in_order(result["pillars"])
    work = [p for p in pillars if p["label"].lower() in ("weak", "fair")]
    good = [p for p in pillars if p["label"].lower() in ("good", "strong")]
    names = {"all": f"All ({len(pillars)})", "work": f"Needs work ({len(work)})", "good": f"Good or strong ({len(good)})"}
    with st.container(key="card_health"):
        section("Business health")
        choice = st.pills("Show", HEALTH_FILTERS, format_func=names.get, default="all", key="health_filter",
                          label_visibility="collapsed") or "all"
        shown = {"all": pillars, "work": work, "good": good}[choice]
        html(health_rows(shown) if shown else '<div class="muted">No areas in this group.</div>')


def latest_apps_card(apps: list) -> None:
    with st.container(key="card_latest"):
        with st.container(horizontal=True, key="latest_head", vertical_alignment="center"):
            html('<div class="section">Latest applications</div>', width="stretch")
            if apps:
                st.button("View all", key="latest_all", type="tertiary", on_click=go, args=("history",))
        if not apps:
            muted("No applications yet.")
            st.button("Apply to a lender", key="latest_apply", type="tertiary", on_click=go, args=("apply",))
        for a in apps:
            st.button(f"{md_escape(a['lender'])}  {status_md(a['status'].capitalize())}", key=f"row_app_{a['id']}",
                      on_click=go, args=("history",), width="stretch")


# ------------------------------------------------------------------ sign in / create account
AUTH_HEADLINE = "Know your credit score from your M-Pesa statement"
AUTH_POINTS = ("Score an Excel or CSV statement in seconds", "See what lifts or drags your score",
               "Find out how much you can borrow")
AUTH_FOOTER = "Your statement is read once and never stored."


def auth_band() -> None:
    """The navy header band of Sign in and Create account (identical on both, so switching does not shift the
    layout); from 1024px it is the left half of a split screen. Also injects the auth styles (theme.AUTH_CSS)."""
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
