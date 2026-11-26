"""Building blocks shared by the pages: status pills, icons, the responsive shell (sidebar, page header, tab bar), the
hero score card and its chart, the estimated limit, quick actions, the Business health tiles, recent activity, and the
sign-in / create-account pieces.

Status is always a PILL (pill()): black text (#0E1226), and only the background carries the meaning. No status is ever
shown as coloured text. One render per page: the same elements are laid out as a phone view or a laptop view by the CSS
in theme.py.
"""
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from html import escape

import streamlit as st

from app import service, theme  # noqa: F401 - service puts src/ on sys.path for scoring

APP_NAME = "Nuru"
MUTED_HEX = theme.MUTED
NAIROBI = timezone(timedelta(hours=3))

# ------------------------------------------------------------------ status pills
PILL_KINDS = ("good", "moderate", "high", "bad", "neutral", "brand")
STATUS_KIND = {
    # applications
    "pending": "moderate", "approved": "good", "declined": "bad",
    # risk tiers (with and without " risk")
    "low": "good", "moderate": "moderate", "high": "high", "very high": "bad",
    "low risk": "good", "moderate risk": "moderate", "high risk": "high", "very high risk": "bad",
    # pillar ratings
    "strong": "good", "good": "good", "fair": "moderate", "weak": "bad",
    # affordability
    "comfortable": "good", "stretched": "moderate", "heavy": "high", "unknown": "neutral",
    # reasons
    "raises risk": "bad", "lowers risk": "good",
    # accounts
    "active": "good", "locked": "bad", "disabled": "neutral",
    # eligibility
    "not eligible": "bad", "not eligible right now": "bad", "not enough income data": "neutral",
    # repayment outcomes (service.REPAYMENT_LABEL): repaying neutral purple, on time green, late yellow, defaulted red
    "repaying": "neutral", "repaid on time": "good", "repaid late": "moderate", "defaulted": "bad",
}


def status_kind(label: str) -> str:
    """The pill kind (background) of a status, tier, rating, band or reason direction; "neutral" if unknown."""
    text = str(label).strip().lower()
    if text.startswith("locked"):
        return "bad"
    return STATUS_KIND.get(text, "neutral")


def pill(text: str, kind: str | None = None) -> str:
    """A status pill: 28px, 12px bold BLACK text (the .pill class sets #0E1226), the meaning in the background class
    pill-<kind>. Never an inline colour."""
    kind = kind or status_kind(text)
    if kind not in PILL_KINDS:
        raise ValueError(f"unknown pill kind {kind!r}")
    return f'<span class="pill pill-{kind}">{escape(str(text))}</span>'


def md_escape(s: str) -> str:
    """Plain text inside a Streamlit markdown label (button and expander labels)."""
    return "".join("\\" + c if c in "\\`*_[]()#+-.!:|<>~$" else c for c in str(s))


def icon(name: str, color: str = theme.INDIGO, size: int = 24, label: str | None = None, stroke: float = 2) -> str:
    """Inline SVG line icon. Decorative unless a label is given."""
    a11y = f'role="img" aria-label="{escape(label)}"' if label else 'aria-hidden="true"'
    return theme.svg(name, color, size, stroke).replace("<svg ", f"<svg {a11y} ", 1)


def html(s: str, **kw) -> None:
    st.markdown(s, unsafe_allow_html=True, **kw)


def cap(text: str) -> str:
    """A small-caps label (11px, bold, letter-spaced, upper case): "Your score", "Quick actions", "Menu" ..."""
    return f'<div class="cap">{escape(text)}</div>'


def title(text: str, sub: str | None = None) -> None:
    html(f'<div class="title">{escape(text)}</div>' + (f'<div class="caption">{escape(sub)}</div>' if sub else ""))


def section(text: str) -> None:
    html(f'<div class="section">{escape(text)}</div>')


def muted(text: str) -> None:
    html(f'<div class="muted">{escape(text)}</div>')


def alert(text: str) -> None:
    """An error line (red text with a small icon, no box; read out by screen readers)."""
    html(f'<div class="alert-text" role="alert">{icon("alert", theme.DANGER, 16)}<span>{escape(text)}</span></div>')


def row(key: str, value_html: str, lead_html: str = "") -> str:
    return f'<div class="row"><span class="k">{lead_html}{escape(key)}</span><span class="v">{value_html}</span></div>'


def avatar(name: str, cls: str = "") -> str:
    return f'<span class="{f"avatar {cls}".strip()}" aria-hidden="true">{escape(initials(name))}</span>'


def logo_html(width: int = 150) -> str:
    """The Nuru logo (assets/brand/nuru-logo.png as a data URI), or the text "Nuru" when the file is missing."""
    uri = theme.brand_uri(theme.LOGO_FILE)
    if uri:
        return f'<img src="{uri}" alt="{APP_NAME}" width="{width}">'
    return f'<span class="wordmark">{APP_NAME}</span>'


def not_available(user: dict | None, message: str) -> None:
    """The standard "not available" state: the title, the reason and a button home. Nothing else is drawn."""
    from app.pages.signin import HOME_FOR                      # (import here: the pages import this module)
    title("Not available")
    alert(message)
    if user:
        st.button("Go to my home", key="go_home", on_click=go, args=(HOME_FOR[user["role"]],))


def reason_row(direction: str, phrase: str) -> str:
    return f'<div class="reason"><span class="txt">{escape(phrase)}</span><span class="dir">{pill(direction)}</span></div>'


def money(x) -> str:
    return f"KES {float(x):,.0f}"


def pct(x, digits: int = 1) -> str:
    return f"{100 * float(x):.{digits}f}%"


def _local(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(NAIROBI)


def short_date(iso: str) -> str:
    return _local(iso).strftime("%d %b %Y")


def date_only(day: str) -> str:
    """A calendar date ("2026-12-10") as "10 Dec 2026" (no time zone: it is already a Nairobi date)."""
    from datetime import date
    return date.fromisoformat(day).strftime("%d %b %Y")


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
    NavItem("score", "Check score", "gauge", "score"),
    NavItem("history", "History", "receipt", "history"),
    NavItem("profile", "Profile", "user", "profile"),
)
LENDER_NAV = (
    NavItem("queue", "Queue", "inbox", "lender"),
    NavItem("decided", "Decided", "check_circle", "lender_decided"),
    NavItem("lprofile", "Profile", "user", "lender_profile"),
)
ADMIN_NAV = (
    NavItem("overview", "Overview", "bars", "admin"),
    NavItem("users", "Users", "users", "admin_users"),
    NavItem("audit", "Audit", "clock", "admin_audit"),
    NavItem("aprofile", "Profile", "user", "admin_profile"),
)
NAV_FOR = {"vendor": VENDOR_NAV, "lender": LENDER_NAV, "admin": ADMIN_NAV}

MENU_ITEMS = (  # key, label, page (None = sign out); icons are in theme.MENU_ICONS
    ("home", "Home", "home"),
    ("score", "Check score", "score"),
    ("apply", "Apply for a loan", "apply"),
    ("history", "My applications", "history"),
    ("profile", "Profile", "profile"),
    ("signout", "Sign out", None),
)
MENU_FOR = {
    "vendor": MENU_ITEMS,
    "lender": tuple((n.key, n.label, n.page) for n in LENDER_NAV) + (("signout", "Sign out", None),),
    "admin": tuple((n.key, n.label, n.page) for n in ADMIN_NAV) + (("signout", "Sign out", None),),
}
PROFILE_FOR = {"vendor": "profile", "lender": "lender_profile", "admin": "admin_profile"}     # the avatar button's page
ACCOUNT_LABEL = {"vendor": "Vendor account", "lender": "Lender account", "admin": "Admin account"}


def role_label(user: dict) -> str:
    """The account type in the phone menu: "Vendor", "Lender · <organisation>" or "Administrator"."""
    role = user.get("role")
    if role == "lender":
        return f"Lender · {user['org_name']}" if user.get("org_name") else "Lender"
    return "Administrator" if role == "admin" else "Vendor"


def account_label(user: dict) -> str:
    """The line under the name in the sidebar: "<Role> account"."""
    return ACCOUNT_LABEL.get(user.get("role"), "Vendor account")


MENU_FLAG = "menu_navigated"


def _menu_choose(page) -> None:
    """Menu item callback. Callbacks always fire, also when the dialog is not drawn again on the next run."""
    if page is None:
        sign_out()
    else:
        go(page)
    st.session_state[MENU_FLAG] = True


@st.dialog("Menu", width="small")
def menu_dialog(items=MENU_ITEMS, user: dict | None = None) -> None:
    """The app menu (phone view): who is signed in and the account type, then the items of the signed-in role. A click
    inside a dialog reruns only the dialog, so after a choice it asks for a full rerun, which draws the new page and
    closes the dialog (main.py clears the flag on every full run)."""
    if st.session_state.pop(MENU_FLAG, False):
        st.rerun()
    if user:
        html(f'<div class="menu-user"><span class="menu-name">{escape(user.get("name") or "")}</span>'
             f'<span class="menu-role">{escape(role_label(user))}</span></div>')
    for key, label, page in items:
        st.button(label, key=f"menu_{key}", on_click=_menu_choose, args=(page,), width="stretch")


def _sidebar(user: dict, role: str, nav, active: str | None) -> None:
    """Laptop sidebar (hidden by CSS below 900px): the logo, "Menu", the nav pills, then the user with a sign-out icon
    button (its visible text is hidden by CSS and stays its accessible name; the tooltip says the same)."""
    with st.container(key="shell_side"):
        html(f'<div class="side-brand">{logo_html(150)}</div><div class="cap side-menu-cap">Menu</div>')
        with st.container(key="side_nav"):
            html(f'<div class="sr-only">{escape(role.capitalize())} navigation</div>')
            for item in nav:
                st.button(item.label, key=f"sidenav_{item.key}", on_click=go, args=(item.page,), width="stretch")
        with st.container(horizontal=True, key="side_user", vertical_alignment="center"):
            html(f'<div class="side-user">{avatar(user["name"])}<span class="side-who"><span class="side-name">'
                 f'{escape(user["name"])}</span><span class="side-role">{escape(account_label(user))}</span></span></div>',
                 width="stretch")
            st.button("Sign out", key="side_signout", on_click=sign_out, help="Sign out")


def bottom_nav(nav, active: str | None) -> None:
    """Phone tab bar, fixed to the bottom of the screen (hidden by CSS from 900px)."""
    with st.container(horizontal=True, key="bottom_nav"):
        for item in nav:
            st.button(item.label, key=f"nav_{item.key}", on_click=go, args=(item.page,), width="stretch")


@contextmanager
def shell(user: dict, role: str, nav, active: str | None, tabs: bool = True):
    """The app frame around one page: the laptop sidebar, the content area, and the phone tab bar. `nav` is a list of
    NavItem (the same list drives both navigation styles), `active` the key of the current item."""
    html(theme.nav_css(nav, active))
    _sidebar(user, role, nav, active)
    with st.container(key="shell_main"):
        yield
    if tabs:
        bottom_nav(nav, active)


def page_header(user: dict, title_text: str, sub: str | None = None, actions=()) -> None:
    """Page header: a small-caps line (`sub`) above the title (Outfit 600, 40px on a laptop, 30px under 900px), actions
    on the right. Phone: menu button and avatar around the title (the sidebar has them on a laptop).
    actions: (label, key, page, "primary" | "secondary")."""
    with st.container(horizontal=True, key="page_head", vertical_alignment="center", gap="small"):
        # a real button: its visible label is hidden by CSS but stays its accessible name, "Menu"
        role = user.get("role", "vendor")
        if st.button("Menu", key="topbar_menu", width="content", help="Menu"):
            menu_dialog(MENU_FOR.get(role, MENU_ITEMS), user)
        cap_html = cap(sub) if sub else ""
        html(f'<div class="ph-text">{cap_html}<div class="ph-title" role="heading" aria-level="1">'
             f'{escape(title_text)}</div></div>', width="stretch")
        if PROFILE_FOR.get(role):
            st.button(initials(user.get("name", "")), key="topbar_avatar", on_click=go, args=(PROFILE_FOR[role],),
                      width="content", help="Profile")
        if actions:
            with st.container(horizontal=True, key="head_actions", gap="small"):
                for label, key, page, kind in actions:
                    st.button(label, key=key, type=kind, on_click=go, args=(page,))


def two_columns(name: str, kind: str = "even") -> tuple:
    """Two columns side by side from 1100px, stacked below. kind: "fixed" (the first column a little wider), "even"
    (halves), "rev" (halves; the first column is drawn on the RIGHT on a laptop and comes first on a phone), "side" (the
    second column 380px, e.g. the lender's Decision card)."""
    with st.container(key=f"grid_{kind}_{name}"):
        a, b = st.container(key=f"col_{name}_a"), st.container(key=f"col_{name}_b")
    return a, b


# ------------------------------------------------------------------ the hero score card and its chart
CHART_W, CHART_H, CHART_PAD = 300, 70, 10


def _trend_words(scores: list) -> str:
    if len(scores) == 1:
        return f"one check, score {scores[0]}"
    first, last = scores[0], scores[-1]
    move = (f"up from {first} to {last}" if last > first else f"down from {first} to {last}" if last < first
            else f"unchanged at {last}")
    return f"last {len(scores)} checks, {move}"


def hero_chart(points: list) -> str:
    """A small score-over-time line in yellow (oldest left; higher score = higher), the dates and scores under it.
    points: [(created_at ISO, score)], oldest first."""
    if not points:
        return ""
    scores = [int(s) for _, s in points]
    lo, hi = min(scores), max(scores)
    if hi - lo < 40:                                         # never zoom in so far that small changes look large
        mid = (hi + lo) / 2
        lo, hi = mid - 20, mid + 20
    n = len(points)
    xs = [CHART_W / 2] if n == 1 else [CHART_PAD + i * (CHART_W - 2 * CHART_PAD) / (n - 1) for i in range(n)]
    ys = [CHART_PAD + (hi - s) / (hi - lo) * (CHART_H - 2 * CHART_PAD) for s in scores]
    out = []
    if n > 1:
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
        out.append(f'<polyline points="{line}" fill="none" stroke="{theme.GOLD}" stroke-width="3" stroke-linejoin="round" '
                   'stroke-linecap="round"/>')
    for i, (x, y) in enumerate(zip(xs, ys)):
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#FFFFFF" stroke="{theme.GOLD}" stroke-width="3"/>'
                   if i == n - 1 else f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{theme.GOLD}"/>')
    days = [_local(iso).strftime("%d %b") for iso, _ in points]
    if len(set(days)) < len(days):                          # two checks on one day: add the time
        days = [_local(iso).strftime("%d %b %H:%M") for iso, _ in points]
    labels = "".join(f'<div class="hero-pt"><b>{s}</b><span>{escape(d)}</span></div>' for s, d in zip(scores, days))
    label = f"Score over time, {_trend_words(scores)}."
    return (f'<div class="hero-chart"><svg role="img" aria-label="{escape(label)}" viewBox="0 0 {CHART_W} {CHART_H}" '
            f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">{"".join(out)}</svg>'
            f'<div class="hero-pts" aria-hidden="true">{labels}</div></div>')


def score_hero(result: dict, points: list | None = None, label: str = "Your score", reasons_button: bool = False) -> None:
    """The indigo hero card: the score (Outfit, about 88px) out of 850, a yellow tier pill, the estimated default risk
    and (vendors only) the score-over-time line. Lenders pass no points: no history chart for them."""
    with st.container(key="card_hero"):
        html(f'<div class="hero" role="group" aria-label="{escape(label)}"><div>{cap(label)}'
             f'<div class="hero-score">{int(result["score"])}<span class="hero-of">out of 850</span></div>'
             f'<div class="hero-meta">{pill(result["tier"], "brand")}'
             f'<span>Estimated default risk {pct(result["pd"])}</span></div></div>'
             + (hero_chart(points) if points else "") + "</div>")
        if reasons_button:
            st.button("See reasons", key="to_reasons", on_click=go, args=("reasons",), width="stretch")


def no_score_card() -> None:
    """The only card on Home (and Result, Reasons) before the first check."""
    with st.container(key="card_noscore"):
        html(f'<div class="noscore"><span class="icon-circle">{icon("gauge", theme.INDIGO, 24)}</span>'
             '<div class="section">See your credit score</div>'
             '<div class="muted">Upload your M-Pesa statement to see your score, what shapes it and how much you '
             'could borrow.</div></div>')
        st.button("Check score", key="cta_score", type="primary", on_click=go, args=("score",), width="stretch")


FINAL_DECISION = "The lender makes the final decision."


def limit_card(result: dict) -> None:
    """The estimated limit ("Up to KES X"), the comfortable amount and the final-decision line; monthly inflow and the
    transactions used under a rule."""
    el = result["eligibility"]
    inc, tx = result.get("monthly_income"), result.get("rows_read")
    with st.container(key="card_limit"):
        if el["status"] == "eligible":
            body = (f'<div class="limit-big">Up to {money(el["max_amount"])}</div>'
                    f'<div class="lc-sub">Comfortable up to {money(el["comfortable_amount"])}</div>'
                    f'<div class="lc-sub">{FINAL_DECISION}</div>')
        elif el["status"] == "not_eligible":
            body = f'<div>{pill("Not eligible right now", "bad")}</div><div class="lc-sub">{FINAL_DECISION}</div>'
        else:
            body = '<div class="limit-big">Not enough income data</div>'
        inflow = f"{money(inc)}/mo" if inc else "not found"
        html(cap("Estimated limit") + body + f'<div class="lc-stats"><span>Inflow <b>{inflow}</b></span>'
             f'<span>Transactions <b>{int(tx) if tx is not None else "-"}</b></span></div>')


QUICK_ACTIONS = (("qa_score", "Check score", "score"), ("qa_apply", "Apply", "apply"), ("qa_reasons", "Reasons", "reasons"),
                 ("qa_history", "History", "history"))


def quick_actions() -> None:
    """Four circular actions (60px circles, the label under each); Check score is filled indigo."""
    with st.container(key="card_quick"):
        html(cap("Quick actions"))
        with st.container(horizontal=True, key="quick_row"):
            for key, label, page in QUICK_ACTIONS:
                st.button(label, key=key, on_click=go, args=(page,), width="stretch")


# ------------------------------------------------------------------ Business health tiles
PILLAR_HELP = {                         # what each area measures (true for every rating), never a verdict
    "Income stability": "How steady your weekly income is.",
    "Cash flow buffer": "How much money you keep in your wallet from day to day.",
    "Borrowing distress": "How much you rely on Fuliza and short-term borrowing.",
    "Affordability": "How big your debt payments are compared with your income.",
    "Obligations": "Whether bills and rent are paid on time.",
    "History and growth": "How long your history is and whether your income is growing.",
    "Network": "How many customers and suppliers you deal with repeatedly.",
}
PILLAR_ICONS = {"Income stability": "trend", "Cash flow buffer": "wallet", "Borrowing distress": "credit",
                "Affordability": "scale", "Obligations": "calendar", "History and growth": "bars", "Network": "users"}


def pillars_in_order(pillars: list) -> list:
    """Pillars in the model's order (saved checks carry keys, snapshots only names)."""
    names = list(service.PILLAR_NAMES.values())
    return sorted(pillars, key=lambda p: names.index(p["name"]) if p.get("name") in names else len(names))


pillars_by_name = pillars_in_order


def tiles(pillars: list) -> str:
    """One tile per area: icon in a 44px soft circle, rating pill top right, Outfit title, one muted line."""
    out = []
    for p in pillars_in_order(pillars):
        out.append(f'<div class="tile"><div class="tile-top"><span class="icon-circle">'
                   f'{icon(PILLAR_ICONS.get(p["name"], "spark"), theme.INDIGO, 22)}</span>{pill(p["label"])}</div>'
                   f'<div class="tile-title">{escape(p["name"])}</div>'
                   f'<div class="tile-desc">{escape(PILLAR_HELP.get(p["name"], ""))}</div></div>')
    return f'<div class="tiles">{"".join(out)}</div>'


def health_tiles(pillars: list, label: str = "Your financial life") -> None:
    with st.container(key="health_tiles"):
        html(cap(label) + tiles(pillars))


# ------------------------------------------------------------------ recent activity (Home)
N_ACTIVITY = 5
EMPTY_ACTIVITY = "Nothing here yet. Check your score to get started."


def activity_items(checks: list, apps: list, n: int = N_ACTIVITY) -> list:
    """The latest score checks and applications together, newest first: (when ISO, icon, title, pill html)."""
    items = [(c["created_at"], "gauge", f"Score check · {c['score']}", pill(c["tier"])) for c in checks]
    items += [(a["created_at"], "send", f"Application to {a['lender']} · {a['ref']}", pill(a["status"].capitalize()))
              for a in apps]
    return sorted(items, key=lambda i: i[0], reverse=True)[:n]


def activity_card(checks: list, apps: list) -> None:
    items = activity_items(checks, apps)
    with st.container(key="card_activity"):
        with st.container(horizontal=True, key="activity_head", vertical_alignment="center"):
            html('<div class="section">Recent activity</div>', width="stretch")
            if items:
                st.button("View all", key="latest_all", type="tertiary", on_click=go, args=("history",))
        if not items:
            muted(EMPTY_ACTIVITY)
            return
        html("".join(f'<div class="act"><span class="icon-circle">{icon(ico, theme.INDIGO, 20)}</span>'
                     f'<div class="act-main"><div class="act-title">{escape(t)}</div>'
                     f'<div class="act-date">{escape(date_time(when))}</div></div>{p}</div>'
                     for when, ico, t, p in items))


# ------------------------------------------------------------------ lender and admin pieces
TIER_SHORT = {"Low risk": "Low", "Moderate risk": "Moderate", "High risk": "High", "Very high risk": "Very high"}


def tier_word(tier: str) -> str:
    return TIER_SHORT.get(tier, tier)


def snapshot_limit(el: dict) -> tuple:
    """(text, pill kind or None) of a snapshot's estimated limit: "Up to KES X", "Not eligible" (a red pill) or
    "Not enough income data" (muted)."""
    mx = el.get("max_amount")
    if mx is None:
        return "Not enough income data", "unknown"
    return (f"Up to {money(mx)}", None) if mx > 0 else ("Not eligible", "declined")


def risk_bars(counts: dict, label: str) -> str:
    """Horizontal bars of {tier: count} (Low green, Moderate yellow, High orange, Very high red) with the share and
    count as text, so the colour is never the only cue."""
    total = sum(counts.values())
    rows = []
    for tier, n in counts.items():
        share = 100 * n / total if total else 0
        rows.append(f'<div class="bar-row"><span>{escape(tier_word(tier))}</span><span class="bar-track">'
                    f'<span class="bar-fill" style="display:block;width:{share:.1f}%;'
                    f'background:{theme.BAR_COLORS.get(tier, theme.LABEL)}"></span></span>'
                    f'<span class="bar-val">{share:.0f}% · {n}</span></div>')
    return f'<div class="bars" role="group" aria-label="{escape(label)}">{"".join(rows)}</div>'


# ------------------------------------------------------------------ sign in / create account
AUTH_HEADLINE = "Credit for the vendors banks overlook"
AUTH_LEAD = "Score a statement, see what moves it, and apply to a lender."
AUTH_POINTS = ("Score an Excel or CSV statement in seconds", "See what lifts or drags your score",
               "Find out how much you can borrow")
AUTH_FOOTER = "Your statement is read once and never stored."
SIGNIN_ROLES = "Vendors, lenders and administrators sign in here."


def auth_band() -> None:
    """The dark navy panel of Sign in and Create account (identical on both, so switching does not shift the layout):
    the left column from 900px, a short header strip (icon and headline) on a phone. No screenshot, no tilt. Also
    injects the auth styles (theme.AUTH_CSS)."""
    theme.inject_auth()
    uri = theme.brand_uri(theme.ICON_FILE)
    mark = f'<img src="{uri}" alt="">' if uri else icon("logo", "#FFFFFF", 26)
    points = "".join(f'<li>{icon("check_circle", theme.AUTH_TICK, 18)}<span>{escape(p)}</span></li>' for p in AUTH_POINTS)
    html(f'<div class="auth-band"><span class="auth-mark" aria-hidden="true">{mark}</span>'
         f'<div class="auth-headline">{escape(AUTH_HEADLINE)}</div><p class="auth-lead">{escape(AUTH_LEAD)}</p>'
         f'<ul class="auth-points">{points}</ul></div>')


def auth_title(heading: str, sub: str | None = None) -> None:
    """The Nuru logo, then the form's title (and an optional muted line)."""
    html(f'<div class="auth-logo">{logo_html(132)}</div>'
         f'<div class="auth-title" role="heading" aria-level="1">{escape(heading)}</div>'
         + (f'<div class="auth-sub">{escape(sub)}</div>' if sub else ""))


def auth_note(text: str, cls: str = "auth-hint") -> None:
    """A muted line on the sign-in page."""
    html(f'<div class="{cls}">{escape(text)}</div>')


def auth_error(text: str, where=st) -> None:
    """A sign-in or sign-up message: red text with a small icon, no box (read out by screen readers)."""
    where.markdown(f'<div class="auth-error" role="alert">{icon("alert", theme.DANGER, 16)}<span>{escape(text)}</span></div>',
                   unsafe_allow_html=True)


def auth_footer() -> None:
    html(f'<div class="auth-foot">{icon("lock", theme.MUTED, 14)}<span>{escape(AUTH_FOOTER)}</span></div>')
