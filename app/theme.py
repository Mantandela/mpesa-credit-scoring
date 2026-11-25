"""Alama theme (the approved design): Roboto, lavender page, white cards with a hairline border, purple primary.

The four base colours are in .streamlit/config.toml; everything else is the CSS below, injected once per run with
st.markdown (style-only st.html can be dropped on a rerun).

Responsive layout (one render per page, laid out by media queries):
- below 1024px (phone and tablet): a centred column up to 430px, the page header as a top bar (menu button, title,
  avatar) and the tab bar fixed to the bottom of the screen. 768px to 1023px uses this same phone layout.
- from 1024px (laptop): no frame; a fixed 240px sidebar (logo, nav items, user and Sign out) and a content area padded
  28px 36px, at most 1100px wide, with the page header (grey subtitle above a 26px title, actions on the right).
Pages outside the vendor shell (sign in, errors, the staff stubs) stay in the centred column at every width.

Containers are styled through their keys: "card_*" white card, "grid_<kind>_*" two columns from 1024px ("fixed",
"even", "rev"), "row_*" list row with a chevron, "page_head" the header ("topbar_menu" / "topbar_avatar" its phone-only
buttons, "head_actions" its buttons), "shell_side" the sidebar ("sidenav_*" its items), "shell_main" the content area,
"bottom_nav" the tab bar, "menu_*" the items of the menu dialog.
Sign in and Create account add AUTH_CSS (navy band, "auth_card" card, footer), injected by those two pages only.

Icons are simple inline SVG line icons. Buttons cannot hold SVG markup, so their icons are the same SVGs as CSS data
URIs (see icon_uri); everywhere else they are inline <svg> elements (components.icon).
"""
from urllib.parse import quote

import streamlit as st

PURPLE = "#5B3FC4"
PURPLE_DARK = "#4A2FB0"
PURPLE_LIGHT = "#7C5CE0"
INK = "#1D1B3A"
MUTED = "#6B6B85"
PAGE = "#F5F2FC"
LINE = "#E3DDF5"
TINT = "#E8DFFB"            # icon tiles and the avatar only, never status
ACTIVE_BG = "#EFEAFB"       # the active sidebar item

ICONS = {
    "logo": '<path d="M4 17l5-5 4 4 7-8"/><path d="M15 8h5v5"/>',
    "check": '<path d="M5.5 12.5l4 4L18.5 7.5"/>',
    "check_circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
    "upload": '<path d="M12 16V5"/><path d="M7 10l5-5 5 5"/><path d="M5 19h14"/>',
    "chevron": '<path d="M9 6l6 6-6 6"/>',
    "menu": '<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h10"/>',
    "home": '<path d="M4 11l8-7 8 7"/><path d="M6 9.5V20h12V9.5"/><path d="M10 20v-5h4v5"/>',
    "gauge": '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/><path d="M4 19h16"/>',
    "receipt": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6"/><path d="M9 12h6"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    "wallet": '<rect x="3" y="6" width="18" height="13" rx="3"/><path d="M3 10h18"/><path d="M15.5 14.5h2.5"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "inbox": '<path d="M4 13l2.5-7h11L20 13v6H4z"/><path d="M4 13h4.5l1 2h5l1-2H20"/>',
    "shield": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>',
    "logout": '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4"/><path d="M10 16l-4-4 4-4"/><path d="M6 12h10"/>',
    "alert": '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5"/><path d="M12 16.5h.01"/>',
    "triangle": '<path d="M12 4l9 16H3z"/><path d="M12 10v4.5"/><path d="M12 17.5h.01"/>',
    "lock": '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
}


def svg(name: str, color: str = PURPLE, size: int = 24, stroke: float = 2) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def icon_uri(name: str, color: str, stroke: float = 2) -> str:
    """The icon as a CSS url() (for button icons, which cannot hold SVG markup)."""
    return f'url("data:image/svg+xml;utf8,{quote(svg(name, color, stroke=stroke))}")'


MENU_ICONS = {"home": "home", "score": "gauge", "apply": "wallet", "history": "receipt", "profile": "user", "signout": "logout"}


def _icon_css() -> str:
    out = [f".st-key-topbar_menu button::before {{ background: {icon_uri('menu', INK)} center / 22px no-repeat; }}"]
    for key, ico in MENU_ICONS.items():
        out.append(f".st-key-menu_{key} button::before {{ background: {TINT} {icon_uri(ico, PURPLE_DARK)} center / 20px no-repeat; }}")
    out.append(f".st-key-side_signout button::before {{ background: {icon_uri('logout', MUTED)} center / 18px no-repeat; }}")
    return "\n".join(out)


def nav_css(nav, active: str | None) -> str:
    """Icons of one nav list in both styles (sidebar "sidenav_<key>", tab bar "nav_<key>") and the active item."""
    out = []
    for item in nav:
        on = item.key == active
        color = PURPLE_DARK if on else MUTED
        out.append(f".st-key-sidenav_{item.key} button::before {{ background: {icon_uri(item.icon, color, 2.2 if on else 2)} "
                   "center / 20px no-repeat; }")
        out.append(f".st-key-nav_{item.key} button::before {{ background: "
                   f"{icon_uri(item.icon, PURPLE if on else MUTED, 2.2 if on else 2)} center / 24px no-repeat; }}")
        if on:
            out.append(f".st-key-sidenav_{item.key} button {{ background: {ACTIVE_BG} !important; }}"
                       f".st-key-sidenav_{item.key} button p {{ color: {PURPLE_DARK} !important; font-weight: 700 !important; }}"
                       f".st-key-nav_{item.key} button p {{ color: {PURPLE} !important; font-weight: 700 !important; }}")
    return "<style>" + "\n".join(out) + "</style>"


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

/* ---------- page ---------- */
[data-testid="stElementContainer"]:has(style) { display: none !important; }   /* style-only markdown takes no space */
html, body { overflow-x: hidden; }
html, body, .stApp { font-family: 'Roboto', sans-serif; color: #1D1B3A; }
.stApp { background: #F5F2FC; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stBottom"] { background: transparent; }
.stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp li,
.stApp summary, .stApp td, .stApp th, .stApp [data-testid="stMarkdownContainer"] { font-family: 'Roboto', sans-serif; }
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
#MainMenu, footer, [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="stMain"] { padding: 0 !important; }
.sr-only { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* the centred column: phone and tablet, and every page outside the vendor shell. The bottom padding keeps the last
   element clear of the tab bar. */
[data-testid="stMainBlockContainer"] { max-width: 430px !important; width: 100%; box-sizing: border-box;
  margin: 0 auto !important; padding: 16px 16px 120px 16px !important; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap: 16px; }
[data-testid="stVerticalBlock"] { gap: 12px; }
.st-key-shell_main { gap: 16px !important; }

/* ---------- laptop shell (from 1024px) ---------- */
.st-key-shell_side, [data-testid="stLayoutWrapper"]:has(> .st-key-shell_side) { display: none !important; }
@media (min-width: 1024px) {
  [data-testid="stMainBlockContainer"]:has(.st-key-shell_side) { max-width: none !important; margin: 0 !important;
    padding: 0 0 48px 240px !important; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-shell_side) { display: block !important; height: 0; }
  .st-key-shell_side { display: flex !important; position: fixed; top: 0; left: 0; bottom: 0; width: 240px !important;
    box-sizing: border-box; background: #FFFFFF; border-right: 1px solid #E3DDF5; padding: 22px 14px 18px 14px;
    gap: 6px !important; z-index: 999; overflow-y: auto; }
  .st-key-shell_main { max-width: 1100px; padding: 28px 36px 0 36px; box-sizing: border-box; gap: 20px !important; }
  .st-key-bottom_nav, .st-key-topbar_menu, .st-key-topbar_avatar,
  [data-testid="stLayoutWrapper"]:has(> .st-key-bottom_nav) { display: none !important; }
}
.side-brand { display: flex; align-items: center; gap: 10px; font-size: 18px; font-weight: 700; color: #1D1B3A;
  padding: 0 6px 18px 6px; }
.side-logo { display: inline-flex; align-items: center; justify-content: center; width: 36px; height: 36px;
  flex: 0 0 36px; border-radius: 10px; background: #5B3FC4; }
.st-key-side_nav { gap: 4px !important; }
[class*="st-key-sidenav_"] button { justify-content: flex-start !important; gap: 12px !important; height: 44px;
  min-height: 44px !important; padding: 0 12px !important; border: none !important; background: transparent !important;
  border-radius: 10px !important; box-shadow: none !important; width: 100%; }
[class*="st-key-sidenav_"] button::before { content: ""; width: 20px; height: 20px; flex: 0 0 20px; display: block; }
[class*="st-key-sidenav_"] button > div { flex: 1 1 auto; justify-content: flex-start !important; }
[class*="st-key-sidenav_"] button p { color: #1D1B3A !important; font-size: 14px !important; font-weight: 500 !important;
  text-align: left !important; }
[class*="st-key-sidenav_"] button:hover { background: #F5F2FC !important; }
.st-key-shell_side > [data-testid="stLayoutWrapper"]:has(> .st-key-side_user) { margin-top: auto; }
.st-key-side_user { border-top: 1px solid #E3DDF5; padding-top: 14px; gap: 4px !important; }
.side-user { display: flex; align-items: center; gap: 10px; padding: 0 6px; }
.side-avatar { width: 36px; height: 36px; flex: 0 0 36px; border-radius: 50%; background: #E8DFFB; color: #4A2FB0;
  font-weight: 700; font-size: 13px; display: inline-flex; align-items: center; justify-content: center; }
.side-name { font-size: 14px; font-weight: 500; color: #1D1B3A; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.st-key-side_signout button { justify-content: flex-start !important; gap: 8px !important; padding: 0 6px !important;
  min-height: 36px !important; }
.st-key-side_signout button::before { content: ""; width: 18px; height: 18px; flex: 0 0 18px; display: block; }
.st-key-side_signout button p { color: #6B6B85 !important; font-size: 13px !important; }

/* ---------- page header: phone top bar / laptop page header ---------- */
.st-key-page_head { flex-wrap: wrap !important; align-items: center; gap: 12px !important; }
.st-key-page_head > [data-testid="stElementContainer"] { width: auto; }
.st-key-page_head > [data-testid="stElementContainer"]:has(.ph-text) { flex: 1 1 0; min-width: 0; }
.ph-sub { font-size: 13px; color: #6B6B85; line-height: 1.3; }
.ph-title { font-size: 20px; font-weight: 700; color: #1D1B3A; line-height: 1.25; margin: 0; }
[data-testid="stLayoutWrapper"]:has(> .st-key-head_actions) { flex: 1 0 100%; order: 10; }
.st-key-head_actions { flex-wrap: nowrap !important; gap: 10px !important; }
.st-key-head_actions > [data-testid="stElementContainer"] { flex: 1 1 0; min-width: 0; }
.st-key-head_actions button { width: 100%; }
@media (min-width: 1024px) {
  .ph-title { font-size: 26px; }
  .st-key-page_head { flex-wrap: nowrap !important; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-head_actions) { flex: 0 0 auto; width: auto !important; }
  .st-key-head_actions { width: auto !important; }
  .st-key-head_actions > [data-testid="stElementContainer"] { flex: 0 0 auto; }
  .st-key-head_actions button { width: auto; padding: 0 20px !important; }
}
.st-key-topbar_avatar { align-self: center !important; display: flex; align-items: center; }
.st-key-topbar_avatar .stButton { margin: 0 !important; display: flex; }
.st-key-topbar_avatar button { width: 44px !important; height: 44px; min-height: 44px !important; padding: 0 !important;
  border-radius: 50% !important; background: #E8DFFB !important; border: none !important; box-shadow: none !important; }
.st-key-topbar_avatar button p { color: #4A2FB0 !important; font-weight: 700 !important; font-size: 14px !important; }
.st-key-topbar_menu { align-self: center !important; }
.st-key-topbar_menu button { width: 44px !important; height: 44px; min-height: 44px !important; padding: 0 !important;
  border-radius: 12px !important; background: #FFFFFF !important; border: 1px solid #E3DDF5 !important;
  box-shadow: none !important; }
.st-key-topbar_menu button::before { content: ""; width: 22px; height: 22px; display: block; }
.st-key-topbar_menu button > div, .st-key-topbar_menu button p { position: absolute !important; width: 1px !important;
  height: 1px !important; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; margin: -1px; padding: 0; }

/* ---------- two columns from 1024px ---------- */
[class*="st-key-grid_"] { gap: 16px !important; }
@media (min-width: 1024px) {
  [class*="st-key-grid_"] { flex-direction: row !important; align-items: flex-start !important; gap: 20px !important; }
  [class*="st-key-grid_"] > [data-testid="stLayoutWrapper"] { flex: 1 1 0; min-width: 0; }
  [class*="st-key-grid_fixed_"] > [data-testid="stLayoutWrapper"]:first-child { flex: 0 0 min(420px, 46%); }
  [class*="st-key-grid_rev_"] { flex-direction: row-reverse !important; }
}
[class*="st-key-col_"] { gap: 16px !important; }

/* ---------- type ---------- */
.stApp p, .stApp li { font-size: 14px; }
/* Streamlit pulls markdown up with a negative margin meant for <p>; these blocks are divs, so remove it */
[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.stMarkdown [data-testid="stMarkdownContainer"] > div > p:last-child, .stMarkdown p:last-child { margin-bottom: 0; }
.title { font-size: 26px; font-weight: 700; color: #1D1B3A; line-height: 1.2; margin: 0; }
.section { font-size: 16px; font-weight: 700; color: #1D1B3A; margin: 0; line-height: 1.3; }
.muted, .caption { font-size: 13px; color: #6B6B85; margin: 0; }
.center { text-align: center; }
.alert-text { display: flex; align-items: flex-start; gap: 6px; color: #B42318; font-weight: 500; font-size: 14px;
  margin: 0; line-height: 1.35; }
.alert-text svg { flex: 0 0 16px; margin-top: 2px; }

/* ---------- cards ---------- */
[class*="st-key-card_"] { background: #FFFFFF; border: 1px solid #E3DDF5; border-radius: 16px; padding: 18px;
  gap: 12px !important; box-sizing: border-box; }
.icon-circle { width: 48px; height: 48px; border-radius: 50%; background: #E8DFFB; display: flex; align-items: center;
  justify-content: center; flex: 0 0 48px; }
.noscore { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 8px; padding: 8px 4px 4px; }
.noscore .muted { max-width: 360px; }

/* score card */
.sc-label { font-size: 13px; color: #6B6B85; }
.sc-score { font-size: 46px; font-weight: 700; line-height: 1.05; color: #1D1B3A; letter-spacing: -0.5px; margin-top: 2px; }
.sc-of { font-size: 14px; font-weight: 400; color: #6B6B85; letter-spacing: 0; margin-left: 8px; }
.sc-pd { font-size: 13px; color: #6B6B85; margin-top: 6px; }
.score-chart { margin-top: 12px; }
.score-chart svg { display: block; height: auto; overflow: visible; }

/* estimated limit card */
.lc-stats { display: flex; gap: 18px; flex-wrap: wrap; font-size: 13px; color: #6B6B85; }
.lc-stats b { color: #1D1B3A; font-weight: 700; }
.lc-rule { height: 1px; background: #EFEAFA; margin: 12px 0; }
.lc-limit { font-size: 16px; font-weight: 700; color: #1D1B3A; line-height: 1.3; }
.lc-unknown { color: #6B6B85; }
.lc-sub { font-size: 13px; color: #6B6B85; margin-top: 4px; }
.limit-big { font-size: 26px; font-weight: 700; color: #1D1B3A; line-height: 1.2; }

/* rows inside cards */
.row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 0;
  border-bottom: 1px solid #EFEAFA; font-size: 14px; }
.row:last-child { border-bottom: none; padding-bottom: 2px; }
.row:first-child { padding-top: 2px; }
.row .k { color: #1D1B3A; display: flex; align-items: center; gap: 12px; }
.row .v { color: #6B6B85; text-align: right; }
.reason { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 12px 0;
  border-bottom: 1px solid #EFEAFA; font-size: 14px; }
.reason:last-child { border-bottom: none; padding-bottom: 2px; }
.reason:first-child { padding-top: 2px; }
.reason .txt { color: #1D1B3A; line-height: 1.4; }
.reason .dir { flex: 0 0 auto; font-size: 13px; white-space: nowrap; }

/* expandable rows (Business health, History on a phone): details/summary, chevron turns when open */
.xrow { border-bottom: 1px solid #EFEAFA; }
.xrow:last-child { border-bottom: none; }
.xrow summary { list-style: none; display: flex; align-items: center; gap: 10px; padding: 12px 2px; cursor: pointer;
  border-radius: 8px; }
.xrow summary::-webkit-details-marker { display: none; }
.xrow summary:focus-visible { outline: 2px solid #5B3FC4; outline-offset: 2px; }
.x-main { flex: 1 1 auto; min-width: 0; font-size: 14px; font-weight: 500; color: #1D1B3A; }
.x-main .x-sub { display: block; font-size: 12px; font-weight: 400; color: #6B6B85; margin-top: 2px; }
.x-side { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; white-space: nowrap; text-align: right; }
.x-side svg { flex: 0 0 16px; }
.x-chev { display: inline-flex; transition: transform 0.15s; }
.xrow[open] .x-chev { transform: rotate(90deg); }
.x-body { font-size: 13px; color: #6B6B85; padding: 0 2px 12px 2px; line-height: 1.45; }
.x-body .row { font-size: 13px; padding: 8px 0; }

/* tables (History on a laptop); a wide table scrolls inside its card, never the page */
.tbl-wrap { overflow-x: auto; max-width: 100%; }
table.tbl { width: 100%; border-collapse: collapse; font-size: 13px; margin: 0; }
.tbl th { text-align: left; color: #6B6B85; font-weight: 500; padding: 8px 10px; border: none;
  border-bottom: 1px solid #E3DDF5; white-space: nowrap; background: transparent; }
.tbl td { padding: 11px 10px; border: none; border-bottom: 1px solid #EFEAFA; color: #1D1B3A; white-space: nowrap;
  background: transparent; }
.tbl tr:last-child td { border-bottom: none; }
.tbl td.note { white-space: normal; min-width: 160px; color: #6B6B85; }
.only-wide { display: none; }
@media (min-width: 1024px) { .only-wide { display: block; } .only-narrow { display: none; } }

/* ---------- buttons ---------- */
.stButton > button, .stFormSubmitButton > button { border-radius: 12px; min-height: 44px; font-weight: 500; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primaryFormSubmit"] { background: #5B3FC4;
  border: none; color: #FFFFFF; height: 48px; min-height: 48px; border-radius: 12px; box-shadow: none; }
.stButton > button[kind="primary"] p, .stFormSubmitButton > button[kind="primaryFormSubmit"] p { font-size: 15px;
  font-weight: 700; color: #FFFFFF; }
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover { background: #4A2FB0; }
.stButton > button[kind="primary"]:disabled { background: #DDD5F7; }
.stButton > button[kind="primary"]:disabled p { color: #4A2FB0; }
.stButton > button[kind="secondary"], .stFormSubmitButton > button[kind="secondaryFormSubmit"] { background: #FFFFFF;
  border: 1.5px solid #5B3FC4; height: 46px; border-radius: 12px; }
.stButton > button[kind="secondary"] p, .stFormSubmitButton > button[kind="secondaryFormSubmit"] p { color: #5B3FC4;
  font-weight: 700; font-size: 14px; }
.stButton > button[kind="secondary"]:hover { background: #F5F2FC; }
.stButton > button[kind="tertiary"] { min-height: 32px; padding: 2px 4px; }
.stButton > button[kind="tertiary"] p { color: #5B3FC4; font-weight: 500; font-size: 14px; }
.stButton > button[kind="tertiary"]:hover p { text-decoration: underline; }
.st-key-delete_results button p, .st-key-confirm_delete button p { color: #B42318 !important; }
.st-key-delete_results button, .st-key-confirm_delete button { border-color: #E3DDF5 !important; }
/* one visible keyboard focus ring for every control */
.stApp button:focus-visible, .stApp summary:focus-visible, .stApp a:focus-visible, .stApp [role="slider"]:focus-visible,
.stApp [role="radio"]:focus-visible { outline: 2px solid #5B3FC4 !important; outline-offset: 2px; }

[data-testid="stMain"]:focus-visible, [data-testid="stAppViewContainer"]:focus-visible,
[data-testid="stMainBlockContainer"]:focus-visible { outline: 2px solid #5B3FC4; outline-offset: -2px; }

/* list rows as buttons: label left, chevron right */
[class*="st-key-row_"] button { background: transparent !important; border: none !important; box-shadow: none !important;
  justify-content: space-between !important; width: 100%; padding: 4px 0 !important; min-height: 44px !important;
  height: auto !important; border-radius: 0 !important; border-bottom: 1px solid #EFEAFA !important; }
[class*="st-key-row_"] button > div, [class*="st-key-row_"] button [data-testid="stMarkdownContainer"] {
  flex: 1 1 auto; text-align: left !important; justify-content: flex-start !important; }
[class*="st-key-row_"] button p { text-align: left !important; color: #1D1B3A !important; font-size: 14px !important;
  font-weight: 500 !important; }
[class*="st-key-row_"] button::after { content: ""; flex: 0 0 20px; height: 20px; background: CHEVRON center / 20px no-repeat; }
[class*="st-key-card_"] [data-testid="stElementContainer"]:last-child [class*="st-key-row_"] button,
[class*="st-key-card_"] [class*="st-key-row_"]:last-child button { border-bottom: none !important; }
.st-key-latest_head { gap: 8px !important; }

/* ---------- menu dialog (phone) ---------- */
[data-testid="stDialog"] div:has(> [role="dialog"]) { width: min(430px, calc(100vw - 32px)) !important;
  max-width: 430px !important; background: transparent !important; box-shadow: none !important; border: none !important; }
[data-testid="stDialog"] [role="dialog"] { width: 100% !important; max-width: 100% !important;
  border-radius: 20px !important; background: #FFFFFF; font-family: 'Roboto', sans-serif;
  box-shadow: 0 20px 60px rgba(74,47,176,0.25) !important; }
[class*="st-key-menu_"] button > div { flex: 1 1 auto; text-align: left !important; justify-content: flex-start !important; }
[class*="st-key-menu_"] button p { text-align: left !important; }
[data-testid="stDialog"] [role="dialog"] h2, [data-testid="stDialog"] [role="dialog"] h2 * { font-size: 20px !important;
  font-weight: 700 !important; color: #1D1B3A; }
[class*="st-key-menu_"] button { background: transparent !important; border: none !important; box-shadow: none !important;
  justify-content: flex-start !important; gap: 14px !important; height: 52px !important; min-height: 52px !important;
  padding: 0 4px !important; border-radius: 14px !important; }
[class*="st-key-menu_"] button:hover { background: #F5F2FC !important; }
[class*="st-key-menu_"] button::before { content: ""; width: 38px; height: 38px; border-radius: 12px; display: block; flex: 0 0 38px; }
[class*="st-key-menu_"] button p { color: #1D1B3A !important; font-size: 15px !important; font-weight: 500 !important; }
.st-key-menu_signout button p { color: #B42318 !important; }

/* ---------- tab bar (phone), fixed to the bottom of the screen ---------- */
.st-key-bottom_nav { position: fixed; left: 0; right: 0; bottom: 0; width: 100% !important; box-sizing: border-box;
  background: #FFFFFF; border-top: 1px solid #E3DDF5; padding: 6px max(8px, calc(50% - 215px)) 8px; z-index: 1000;
  flex-wrap: nowrap !important; gap: 0 !important; }
.st-key-bottom_nav [data-testid="stElementContainer"], .st-key-bottom_nav .stButton { flex: 1 1 0; min-width: 0; }
.st-key-bottom_nav button { background: transparent !important; border: none !important; box-shadow: none !important;
  flex-direction: column !important; gap: 3px !important; min-height: 52px !important; height: auto !important;
  padding: 2px 0 !important; width: 100%; }
.st-key-bottom_nav button::before { content: ""; width: 24px; height: 24px; display: block; }
.st-key-bottom_nav button p { font-size: 12px !important; color: #6B6B85 !important; font-weight: 500 !important; }

/* ---------- inputs ---------- */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { font-size: 13px !important; font-weight: 500 !important;
  color: #1D1B3A; }
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"] {
  background: #FFFFFF !important; border: 1.5px solid #E3DDF5 !important; border-radius: 12px !important;
  height: 48px !important; min-height: 48px; overflow: hidden; box-sizing: border-box; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within {
  border-color: #5B3FC4 !important; box-shadow: 0 0 0 3px rgba(91,63,196,0.30); }
[data-testid="stTextInputRootElement"] input, [data-testid="stNumberInputContainer"] input { font-size: 15px !important;
  padding-left: 14px !important; background: #FFFFFF !important; height: 100% !important; }
[data-testid="stNumberInput"] button { background: #FFFFFF !important; border: none !important; }
[data-testid="InputInstructions"] { display: none; }
[data-testid="stCheckbox"] label p { font-size: 14px !important; }
[data-testid="stCheckbox"] label:has(input:focus-visible) { outline: 2px solid #5B3FC4; outline-offset: 2px; border-radius: 6px; }

/* uploader: dashed drop zone with the upload icon; the widget's own type list is replaced by the card's caption */
[data-testid="stFileUploaderDropzone"] { border: 2px dashed #B6A6EE !important; border-radius: 14px !important;
  background: #FBFAFF !important; padding: 16px !important; }
[data-testid="stFileUploaderDropzone"]:focus-within { border-color: #5B3FC4 !important; }
[data-testid="stFileUploaderDropzoneInstructions"] span { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"] > div::after { content: "or drop the file here"; font-size: 13px;
  color: #6B6B85; }
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] { color: #5B3FC4; }

/* lender choice as radio rows */
.st-key-apply_lender [data-testid="stRadioGroup"] { gap: 8px; width: 100%; flex-direction: column; }
.st-key-apply_lender, .st-key-apply_lender [data-testid="stRadio"], .st-key-apply_lender [data-testid="stRadioGroup"] > div {
  width: 100% !important; }
.st-key-apply_lender [data-testid="stRadioOption"] { width: 100%; box-sizing: border-box; margin: 0; padding: 12px 14px;
  border: 1px solid #E3DDF5; border-radius: 12px; background: #FFFFFF; }
.st-key-apply_lender [data-testid="stRadioOption"]:has(input:checked) { border-color: #5B3FC4; }
.st-key-apply_lender [data-testid="stRadioOption"]:has(input:focus-visible) { outline: 2px solid #5B3FC4; outline-offset: 2px; }

/* filter chips (Business health) */
.st-key-health_filter [data-testid="stButtonGroup"] { flex-wrap: wrap; gap: 6px; }
.st-key-health_filter button { min-height: 32px !important; height: 32px; border-radius: 999px !important;
  border: 1px solid #E3DDF5 !important; background: #FFFFFF !important; padding: 0 12px !important; }
.st-key-health_filter button p { font-size: 13px !important; color: #1D1B3A !important; font-weight: 500 !important; }
.st-key-health_filter button[kind="pillsActive"] { border-color: #5B3FC4 !important; background: #EFEAFB !important; }
.st-key-health_filter button[kind="pillsActive"] p { color: #4A2FB0 !important; font-weight: 700 !important; }

/* Check score: numbered steps */
.steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.stApp .steps li { display: flex; gap: 12px; align-items: flex-start; margin: 0; font-size: 14px; color: #1D1B3A; line-height: 1.4; }
.num { width: 28px; height: 28px; border-radius: 50%; background: #E8DFFB; color: #4A2FB0; font-weight: 700;
  font-size: 13px; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 28px; }
.lock-line { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #6B6B85; line-height: 1.4; }
.lock-line svg { flex: 0 0 16px; }

/* Reasons: Test an amount */
.big-amount { font-size: 40px; font-weight: 700; color: #1D1B3A; line-height: 1.1; }
.band-line { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 14px; color: #1D1B3A; }
/* the big amount above is the slider's value: hide the duplicate value bubble and the min/max ticks */
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] { display: none; }

/* sent */
.done-circle { width: 88px; height: 88px; border-radius: 50%; margin: 8px auto 0 auto; background: #5B3FC4;
  display: flex; align-items: center; justify-content: center; }

/* profile */
.profile-id { display: flex; align-items: center; gap: 14px; }
.avatar-lg { width: 56px; height: 56px; flex: 0 0 56px; border-radius: 50%; background: #E8DFFB; color: #4A2FB0;
  font-size: 20px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.profile-id .section { word-break: break-word; }
.profile-id .muted { word-break: break-all; }
.st-key-sign_out button { justify-content: flex-start !important; }
.st-key-sign_out button p { color: #B42318 !important; font-weight: 700 !important; }
[data-testid="stForm"] { border: none; padding: 0; }

/* expanders (Change password) */
[data-testid="stExpander"] details { background: #FFFFFF; border-radius: 12px !important; border: 1px solid #E3DDF5 !important; }
[data-testid="stExpander"] summary p { font-size: 14px; font-weight: 500; }
</style>
""".replace("CHEVRON", icon_uri("chevron", MUTED))


def css() -> str:
    return CSS.replace("</style>", _icon_css() + "\n</style>")


# Sign in and Create account only (injected by those two pages, after the main theme). Every rule is scoped to the
# navy band (.auth-band), the card (st-key-auth_card) or the footer (.auth-foot), so nothing here reaches other pages.
NAVY = "#0F172A"
AUTH_POINT = "#C7D2FE"      # the three lines in the band
AUTH_TICK = "#A5B4FC"       # their check-circle icons
ERROR = "#B42318"

AUTH_CSS = """
<style>
/* the band and card fill the frame edge to edge, so the frame drops its side and top padding on these pages */
[data-testid="stMainBlockContainer"]:has(.auth-band) { padding: 0 0 32px 0 !important; }

/* navy header band */
.auth-band { background: #0F172A; color: #FFFFFF; padding: 26px 24px 58px 24px; }
.auth-brand { display: flex; align-items: center; gap: 10px; font-size: 18px; font-weight: 500; line-height: 1.2;
  color: #FFFFFF; }
.auth-logo { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px;
  flex: 0 0 40px; border-radius: 12px; background: #5B3FC4; }
.auth-headline { font-size: 22px; font-weight: 500; line-height: 1.3; color: #FFFFFF; margin: 22px 0 14px 0; }
.auth-headline .nowrap { white-space: nowrap; }
.stApp ul.auth-points { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.stApp ul.auth-points li { display: flex; align-items: center; gap: 8px; margin: 0; padding: 0; font-size: 13px;
  line-height: 1.35; color: #C7D2FE; }
.auth-points svg { flex: 0 0 16px; }

/* white card overlapping the band by 36px (the extra 12px cancels the block gap above it) */
.st-key-auth_card { background: #FFFFFF; border: 0.5px solid #E3DDF5; border-radius: 20px; padding: 18px;
  margin: -48px 14px 0 14px; width: auto !important; box-sizing: border-box; position: relative; z-index: 1;
  gap: 14px !important; }
.st-key-auth_card [data-testid="stForm"] { border: none; padding: 0; border-radius: 0; }
.st-key-auth_card [data-testid="stForm"] [data-testid="stVerticalBlock"] { gap: 12px; }
.auth-title { font-size: 20px; font-weight: 500; line-height: 1.25; color: #1D1B3A; margin: 0; }
.auth-sub { font-size: 13px; color: #6B6B85; margin: 2px 0 0 0; }

/* fields: 46px, 12px radius, hairline lavender border, purple focus ring */
.st-key-auth_card [data-testid="stWidgetLabel"] p { font-size: 13px !important; font-weight: 500 !important; }
.st-key-auth_card [data-testid="stTextInputRootElement"] { height: 46px !important; min-height: 46px;
  border: 1.5px solid #E3DDF5 !important; border-radius: 12px !important; background: #FFFFFF !important; }
.st-key-auth_card [data-testid="stTextInputRootElement"]:focus-within { border-color: #5B3FC4 !important;
  box-shadow: 0 0 0 3px rgba(91,63,196,0.30); }
.st-key-auth_card input::placeholder { color: #6B6B85; opacity: 1; }
/* Streamlit's "Press Enter to submit form" hint crowds the field (and the reveal icon) at phone width; Enter still submits */
.st-key-auth_card [data-testid="InputInstructions"] { display: none; }
/* Streamlit's own password reveal button sits inside the field (which clips overflow): ring drawn inside it */
.st-key-auth_card [data-testid="stTextInputRootElement"] button { background: #FFFFFF !important; }
.st-key-auth_card [data-testid="stTextInputRootElement"] button:focus-visible { outline: 2px solid #5B3FC4 !important;
  outline-offset: -4px; border-radius: 10px; }

/* full-width submit button; a small spinner shows on it while the sign-in or sign-up runs */
.st-key-auth_card .stFormSubmitButton > button { width: 100%; height: 48px; min-height: 48px; border-radius: 14px;
  background: #5B3FC4; border: none; box-shadow: none; color: #FFFFFF; gap: 8px; }
.st-key-auth_card .stFormSubmitButton > button p { font-size: 15px; font-weight: 500; color: #FFFFFF; }
.st-key-auth_card .stFormSubmitButton > button:hover { background: #4A2FB0; color: #FFFFFF; }
.st-key-auth_card .stFormSubmitButton > button:focus-visible { outline: 2px solid #5B3FC4; outline-offset: 2px; }
.stApp[data-test-script-state="running"] .st-key-auth_card [data-testid="stForm"]:focus-within .stFormSubmitButton > button {
  background: #4A2FB0; pointer-events: none; cursor: progress; }
.stApp[data-test-script-state="running"] .st-key-auth_card [data-testid="stForm"]:focus-within .stFormSubmitButton > button::after {
  content: ""; width: 16px; height: 16px; flex: 0 0 16px; box-sizing: border-box; border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.45); border-top-color: #FFFFFF; animation: auth-spin 0.7s linear infinite; }
@keyframes auth-spin { to { transform: rotate(360deg); } }

/* "New vendor? Create an account": muted question, purple link (the label's bold part) */
.st-key-to_signup button, .st-key-to_signin button { min-height: 32px !important; height: auto !important;
  padding: 4px 8px !important; border-radius: 8px !important; }
.st-key-to_signup button p, .st-key-to_signin button p { font-size: 13px !important; font-weight: 400 !important;
  color: #6B6B85 !important; }
.st-key-to_signup button p strong, .st-key-to_signin button p strong { color: #5B3FC4; font-weight: 500; }
.st-key-to_signup button:hover p strong, .st-key-to_signin button:hover p strong { text-decoration: underline; }
.st-key-to_signup button:focus-visible, .st-key-to_signin button:focus-visible { outline: 2px solid #5B3FC4 !important;
  outline-offset: 0; }

/* errors: red text with a small icon, no box */
.auth-error { display: flex; align-items: flex-start; gap: 6px; margin: -4px 0 0 0; font-size: 13px; font-weight: 500;
  line-height: 1.35; color: #B42318; }
.auth-error svg { flex: 0 0 16px; margin-top: 1px; }

/* footer line under the card */
.auth-foot { display: flex; align-items: center; justify-content: center; gap: 6px; margin: 4px 16px 0 16px;
  font-size: 12px; line-height: 1.35; color: #6B6B85; text-align: center; }
.auth-foot svg { flex: 0 0 14px; }
/* laptop (from 1024px): split screen. Left half flat navy with the headline; right half lavender with the card
   (400px, centred) and the footer line under it. */
@media (min-width: 1024px) {
  [data-testid="stMainBlockContainer"]:has(.auth-band) { max-width: none !important; margin: 0 !important;
    padding: 0 0 0 50% !important; }
  [data-testid="stMainBlockContainer"]:has(.auth-band) > [data-testid="stVerticalBlock"] { min-height: 100vh;
    justify-content: center; align-items: center; gap: 16px; padding: 40px 24px; box-sizing: border-box; }
  .auth-band { position: fixed; top: 0; left: 0; bottom: 0; width: 50%; box-sizing: border-box;
    padding: 48px clamp(40px, 6vw, 96px); display: flex; flex-direction: column; justify-content: center; }
  .auth-headline { font-size: 38px; font-weight: 700; line-height: 1.2; max-width: 520px; margin: 40px 0 26px 0; }
  .stApp ul.auth-points { gap: 12px; }
  .stApp ul.auth-points li { font-size: 15px; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-auth_card) { width: 400px; max-width: 100%; margin: 0 auto; }
  .st-key-auth_card { margin: 0 !important; width: 400px !important; max-width: 100%; padding: 24px; }
  .auth-foot { margin: 0; }
}
</style>
"""


def inject_auth() -> None:
    """The Sign in / Create account styles, injected like the main theme (st.markdown, hidden wrapper)."""
    st.markdown(AUTH_CSS, unsafe_allow_html=True)


def inject() -> None:
    """Inject the theme with st.markdown: style-only st.html goes to a separate event container that can be dropped on
    a rerun, which left some screens unstyled. The empty wrapper is hidden (a hidden <style> still applies)."""
    st.markdown(css(), unsafe_allow_html=True)


def favicon():
    """A simple purple rounded-square favicon with the white logo line (drawn, so no image file is needed)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 63, 63), radius=16, fill=PURPLE)
    d.line([(14, 44), (26, 32), (35, 41), (50, 22)], fill="white", width=6, joint="curve")
    return img
