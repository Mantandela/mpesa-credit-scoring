"""Nuru theme (the approved redesign): Outfit headings and big numbers, Roboto body, a light grey page, white cards
with a 1px border and 24px radius, indigo primary, pill-shaped buttons, and status pills whose BACKGROUND carries the
meaning (their text is always #0E1226).

Everything is CSS injected with st.markdown (style-only st.html can be dropped on a rerun): CSS once per run for every
page, AUTH_CSS on Sign in and Create account only, MOTION_CSS on the vendor's Check score, Result and Reasons only (the
only place a tilt is used; never on auth, lender or admin pages).

Responsive layout (one render per page, laid out by media queries):
- below 900px (phone and small tablet): a centred column (padding 20px 16px), the page header as a top bar (menu
  button, title, avatar) and a tab bar fixed to the bottom of the screen.
- from 900px (laptop): a fixed 252px white sidebar (logo, "Menu", nav pills, the user and a sign-out icon button) and
  the content area padded 32px 44px. Two-column grids sit side by side from 1100px.

Containers are styled through their keys: "card_*" white card (card_hero: the indigo score card), "grid_<kind>_*" two
columns ("fixed", "even", "rev", "side"), "page_head" the header, "shell_side" the sidebar ("sidenav_*" its items),
"shell_main" the content area, "bottom_nav" the tab bar, "menu_*" the items of the phone menu, "qa_*" the quick actions.

Icons are inline SVG line icons. Buttons cannot hold SVG markup, so their icons are the same SVGs as CSS data URIs
(see icon_uri); everywhere else they are inline <svg> elements (components.icon).
"""
import base64
import functools
from pathlib import Path
from urllib.parse import quote

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
BRAND_DIR = ROOT / "assets" / "brand"
LOGO_FILE, ICON_FILE = "nuru-logo.png", "nuru-icon.png"

# ------------------------------------------------------------------ design tokens
INDIGO = "#3B2FC9"            # primary
INDIGO_DARK = "#2F25A8"       # hover
INDIGO_LIGHT = "#7A6CF2"      # end of the hero gradient
TINT = "#F0EEFF"              # light purple tint: active nav item, icon circles
GOLD = "#F5B83D"              # golden yellow: hero chart, hero tier pill, auth ticks
NAVY = "#0E1226"              # dark navy: text, auth panel
NAVY_2 = "#171B3D"            # end of the auth panel gradient
PAGE = "#F6F7F9"
CARD = "#FFFFFF"
BORDER = "#E6E8EF"
MUTED = "#5B6078"             # muted text (6.2:1 on white)
LABEL = "#6B7089"             # small-caps labels. The brief says #7A7F96, which is 4.0:1 on white and fails WCAG AA for
                              # 11px text; this is the nearest shade that passes (4.9:1 on white, 4.6:1 on the page)
DANGER = "#B42318"
DANGER_LINE = "#F3C1BC"
INPUT_LINE = "#E1E3EC"
SECONDARY_LINE = "#CFCBF5"
PILL_BG = {"good": "#BFEBCF", "moderate": "#FBE2A0", "high": "#FFD1B0", "bad": "#F8BDB6", "neutral": "#E4E1FF",
           "brand": GOLD}
BAR_COLORS = {"Low risk": "#2E9E5B", "Moderate risk": GOLD, "High risk": "#F08A3C", "Very high risk": "#D9483B"}

# names kept for the modules that used the old theme
PURPLE, PURPLE_DARK, INK, ERROR = INDIGO, INDIGO_DARK, NAVY, DANGER

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
    "bars": '<path d="M5 20V11"/><path d="M12 20V5"/><path d="M19 20v-6"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c1-3.5 3.5-5.5 6.5-5.5s5.5 2 6.5 5.5"/><path d="M15.5 4.8a3.5 3.5 0 0 1 0 6.4"/><path d="M18 14.8c1.7.8 2.9 2.6 3.5 5.2"/>',
    "minus_circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    "trend": '<path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/>',
    "scale": '<path d="M12 4v16"/><path d="M7 20h10"/><path d="M5 8h14"/><path d="M5 8l-2.5 6a3 3 0 0 0 5 0z"/><path d="M19 8l-2.5 6a3 3 0 0 0 5 0z"/>',
    "calendar": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16"/><path d="M9 3v4"/><path d="M15 3v4"/>',
    "credit": '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 10h18"/><path d="M7 15h3"/>',
    "spark": '<path d="M12 3v4"/><path d="M12 17v4"/><path d="M3 12h4"/><path d="M17 12h4"/><path d="M6 6l2.5 2.5"/><path d="M15.5 15.5L18 18"/><path d="M18 6l-2.5 2.5"/><path d="M8.5 15.5L6 18"/>',
    "list": '<path d="M9 6h11"/><path d="M9 12h11"/><path d="M9 18h11"/><path d="M4.5 6h.01"/><path d="M4.5 12h.01"/><path d="M4.5 18h.01"/>',
    "send": '<path d="M21 3L10 14"/><path d="M21 3l-7 18-4-7-7-4z"/>',
    "x_circle": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6"/><path d="M15 9l-6 6"/>',
}


def svg(name: str, color: str = INDIGO, size: int = 24, stroke: float = 2) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def icon_uri(name: str, color: str, stroke: float = 2) -> str:
    """The icon as a CSS url() (for button icons, which cannot hold SVG markup)."""
    return f'url("data:image/svg+xml;utf8,{quote(svg(name, color, stroke=stroke))}")'


# ------------------------------------------------------------------ brand assets
@functools.lru_cache(maxsize=None)
def brand_uri(name: str) -> str | None:
    """A file of assets/brand as a base64 data URI (cached), or None when it is missing or unreadable."""
    try:
        data = (BRAND_DIR / name).read_bytes()
    except OSError:
        return None
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii") if data else None


def page_icon():
    """The browser-tab icon: assets/brand/nuru-icon.png, else a drawn indigo tile (so a missing file never crashes)."""
    path = BRAND_DIR / ICON_FILE
    if path.is_file():
        try:
            from PIL import Image
            with Image.open(path) as img:
                return img.copy()
        except Exception:                      # noqa: BLE001 - an unreadable file: fall back to the drawn icon
            pass
    return favicon()


def favicon():
    """An indigo rounded square with the white logo line (drawn, so no image file is needed)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 63, 63), radius=16, fill=INDIGO)
    d.line([(14, 44), (26, 32), (35, 41), (50, 22)], fill="white", width=6, joint="curve")
    return img


# ------------------------------------------------------------------ icons on buttons
MENU_ICONS = {"home": "home", "score": "gauge", "apply": "wallet", "history": "receipt", "profile": "user", "signout": "logout",
              "queue": "inbox", "decided": "check_circle", "lprofile": "user", "overview": "bars", "users": "users",
              "audit": "clock", "aprofile": "user"}
QUICK_ICONS = {"qa_score": "gauge", "qa_apply": "send", "qa_reasons": "list", "qa_history": "receipt"}


def _icon_css() -> str:
    out = [f".st-key-topbar_menu button::before {{ background: {icon_uri('menu', NAVY)} center / 22px no-repeat; }}"]
    for key, ico in MENU_ICONS.items():
        out.append(f".st-key-menu_{key} button::before {{ background: {TINT} {icon_uri(ico, INDIGO)} center / 20px no-repeat; }}")
    out.append(f".st-key-menu_signout button::before {{ background: #FDECEA {icon_uri('logout', DANGER)} center / 20px no-repeat; }}")
    out.append(f".st-key-side_signout button::before {{ background: {icon_uri('logout', MUTED)} center / 20px no-repeat; }}")
    for key, ico in QUICK_ICONS.items():
        on = key == "qa_score"
        out.append(f".st-key-{key} button::before {{ background: {INDIGO if on else TINT} "
                   f"{icon_uri(ico, '#FFFFFF' if on else INDIGO)} center / 26px no-repeat; }}")
    return "\n".join(out)


def nav_css(nav, active: str | None) -> str:
    """Icons of one nav list in both styles (sidebar "sidenav_<key>", tab bar "nav_<key>") and the active item."""
    out = []
    for item in nav:
        on = item.key == active
        out.append(f".st-key-sidenav_{item.key} button::before {{ background: "
                   f"{icon_uri(item.icon, INDIGO if on else MUTED, 2.2 if on else 2)} center / 20px no-repeat; }}")
        out.append(f".st-key-nav_{item.key} button::before {{ background: "
                   f"{icon_uri(item.icon, INDIGO if on else MUTED, 2.2 if on else 2)} center / 24px no-repeat; }}")
        if on:
            out.append(f".st-key-sidenav_{item.key} button {{ background: {TINT} !important; }}"
                       f".st-key-sidenav_{item.key} button p {{ color: {INDIGO} !important; font-weight: 700 !important; }}"
                       f".st-key-nav_{item.key} button p {{ color: {INDIGO} !important; font-weight: 700 !important; }}")
    return "<style>" + "\n".join(out) + "</style>"


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@600;700&family=Roboto:wght@400;500;700&display=swap');

/* ---------- page ---------- */
[data-testid="stElementContainer"]:has(style) { display: none !important; }   /* style-only markdown takes no space */
html, body { overflow-x: hidden; }
html, body, .stApp { font-family: 'Roboto', sans-serif; color: #0E1226; }
.stApp { background: #F6F7F9; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stBottom"] { background: transparent; }
.stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li, .stApp summary, .stApp td, .stApp th,
.stApp [data-testid="stMarkdownContainer"] { font-family: 'Roboto', sans-serif; }
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
#MainMenu, footer, [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="stMain"] { padding: 0 !important; }
.sr-only { position: absolute !important; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* the centred column: phone and small tablet, and every page outside the shell. The bottom padding keeps the last
   element clear of the tab bar. */
[data-testid="stMainBlockContainer"] { max-width: 600px !important; width: 100%; box-sizing: border-box;
  margin: 0 auto !important; padding: 20px 16px 120px 16px !important; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap: 16px; }
[data-testid="stVerticalBlock"] { gap: 12px; }
.st-key-shell_main { gap: 20px !important; }

/* ---------- laptop shell (from 900px) ---------- */
.st-key-shell_side, [data-testid="stLayoutWrapper"]:has(> .st-key-shell_side) { display: none !important; }
@media (min-width: 900px) {
  [data-testid="stMainBlockContainer"]:has(.st-key-shell_side) { max-width: none !important; margin: 0 !important;
    padding: 0 0 48px 252px !important; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-shell_side) { display: block !important; height: 0; }
  .st-key-shell_side { display: flex !important; position: fixed; top: 0; left: 0; bottom: 0; width: 252px !important;
    box-sizing: border-box; background: #FFFFFF; border-right: 1px solid #E6E8EF; padding: 26px 16px 18px 16px;
    gap: 6px !important; z-index: 999; overflow-y: auto; }
  .st-key-shell_main { max-width: 1240px; padding: 32px 44px 0 44px; box-sizing: border-box; gap: 24px !important; }
  .st-key-bottom_nav, .st-key-topbar_menu, .st-key-topbar_avatar,
  [data-testid="stLayoutWrapper"]:has(> .st-key-bottom_nav) { display: none !important; }
}
.side-brand { display: flex; align-items: center; padding: 0 8px 22px 8px; min-height: 40px; }
.side-brand img { width: 150px; height: auto; display: block; }
.wordmark { font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 26px; color: #3B2FC9; letter-spacing: -0.3px;
  line-height: 1; }
.side-menu-cap { padding: 0 12px 6px 12px; }
.st-key-side_nav { gap: 4px !important; }
[class*="st-key-sidenav_"] button { justify-content: flex-start !important; gap: 12px !important; height: 48px;
  min-height: 48px !important; padding: 0 16px !important; border: none !important; background: transparent !important;
  border-radius: 999px !important; box-shadow: none !important; width: 100%; }
[class*="st-key-sidenav_"] button::before { content: ""; width: 20px; height: 20px; flex: 0 0 20px; display: block; }
[class*="st-key-sidenav_"] button > div { flex: 1 1 auto; justify-content: flex-start !important; }
[class*="st-key-sidenav_"] button p { color: #0E1226 !important; font-size: 15px !important; font-weight: 500 !important;
  text-align: left !important; }
[class*="st-key-sidenav_"] button:hover { background: #F6F7F9 !important; }
.st-key-shell_side > [data-testid="stLayoutWrapper"]:has(> .st-key-side_user) { margin-top: auto; }
.st-key-side_user { border-top: 1px solid #E6E8EF; padding-top: 14px; gap: 8px !important; flex-wrap: nowrap !important;
  align-items: center !important; }
.st-key-side_user > [data-testid="stElementContainer"]:first-child { flex: 1 1 auto; min-width: 0; }
.side-user { display: flex; align-items: center; gap: 10px; padding: 0 4px; min-width: 0; }
.avatar { width: 40px; height: 40px; flex: 0 0 40px; border-radius: 50%; background: #F0EEFF; color: #3B2FC9;
  font-weight: 700; font-size: 14px; display: inline-flex; align-items: center; justify-content: center;
  font-family: 'Outfit', sans-serif; }
.avatar.sm { width: 32px; height: 32px; flex: 0 0 32px; font-size: 12px; }
.side-who { display: flex; flex-direction: column; min-width: 0; }
.side-name { font-size: 14px; font-weight: 700; color: #0E1226; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.side-role { font-size: 12px; color: #5B6078; line-height: 1.3; overflow-wrap: anywhere; }
.st-key-side_signout { flex: 0 0 auto; width: auto !important; }
.st-key-side_signout button { width: 40px !important; height: 40px !important; min-height: 40px !important;
  padding: 0 !important; border-radius: 50% !important; border: 1px solid #E6E8EF !important; background: #FFFFFF !important; }
.st-key-side_signout button::before { content: ""; width: 20px; height: 20px; display: block; }
.st-key-side_signout button > div, .st-key-side_signout button p, .st-key-topbar_menu button > div,
.st-key-topbar_menu button p { position: absolute !important; width: 1px !important; height: 1px !important;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; margin: -1px; padding: 0; }
.menu-user { display: flex; flex-direction: column; gap: 2px; padding: 0 4px 12px 4px; border-bottom: 1px solid #E6E8EF; }
.menu-name { font-size: 15px; font-weight: 700; color: #0E1226; overflow-wrap: anywhere; }
.menu-role { font-size: 13px; color: #5B6078; overflow-wrap: anywhere; }

/* ---------- small caps labels, page header ---------- */
.cap { font-size: 11px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; color: #6B7089;
  line-height: 1.4; margin: 0; }
.st-key-page_head { flex-wrap: wrap !important; align-items: center; gap: 12px !important; }
.st-key-page_head > [data-testid="stElementContainer"] { width: auto; }
.st-key-page_head > [data-testid="stElementContainer"]:has(.ph-text) { flex: 1 1 0; min-width: 0; }
.ph-text .cap { margin-bottom: 4px; }
.ph-title { font-family: 'Outfit', sans-serif; font-size: 30px; font-weight: 600; color: #0E1226; line-height: 1.15;
  margin: 0; letter-spacing: -0.3px; overflow-wrap: anywhere; }
[data-testid="stLayoutWrapper"]:has(> .st-key-head_actions) { flex: 1 0 100%; order: 10; }
.st-key-head_actions { flex-wrap: nowrap !important; gap: 10px !important; }
.st-key-head_actions > [data-testid="stElementContainer"] { flex: 1 1 0; min-width: 0; }
.st-key-head_actions button { width: 100%; }
@media (min-width: 900px) {
  .ph-title { font-size: 40px; }
  .st-key-page_head { flex-wrap: nowrap !important; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-head_actions) { flex: 0 0 auto; width: auto !important; }
  .st-key-head_actions { width: auto !important; }
  .st-key-head_actions > [data-testid="stElementContainer"] { flex: 0 0 auto; }
  .st-key-head_actions button { width: auto; padding: 0 26px !important; }
}
.st-key-topbar_avatar { align-self: center !important; display: flex; align-items: center; }
.st-key-topbar_avatar .stButton { margin: 0 !important; display: flex; }
.st-key-topbar_avatar button { width: 44px !important; height: 44px !important; min-height: 44px !important;
  padding: 0 !important; border-radius: 50% !important; background: #F0EEFF !important; border: none !important; }
.st-key-topbar_avatar button p { color: #3B2FC9 !important; font-weight: 700 !important; font-size: 14px !important; }
.st-key-topbar_menu { align-self: center !important; }
.st-key-topbar_menu button { width: 44px !important; height: 44px !important; min-height: 44px !important;
  padding: 0 !important; border-radius: 50% !important; background: #FFFFFF !important; border: 1px solid #E6E8EF !important; }
.st-key-topbar_menu button::before { content: ""; width: 22px; height: 22px; display: block; }
.topbar-initials { width: 44px; height: 44px; border-radius: 50%; background: #F0EEFF; color: #3B2FC9; font-weight: 700;
  font-size: 14px; display: flex; align-items: center; justify-content: center; }
@media (min-width: 900px) { [data-testid="stElementContainer"]:has(.topbar-initials) { display: none !important; } }

/* ---------- two columns from 1100px ---------- */
[class*="st-key-grid_"] { gap: 20px !important; }
@media (min-width: 1100px) {
  [class*="st-key-grid_"] { flex-direction: row !important; align-items: flex-start !important; gap: 24px !important; }
  [class*="st-key-grid_"] > [data-testid="stLayoutWrapper"] { flex: 1 1 0; min-width: 0; }
  [class*="st-key-grid_fixed_"] > [data-testid="stLayoutWrapper"]:first-child { flex: 1.25 1 0; }
  [class*="st-key-grid_rev_"] { flex-direction: row-reverse !important; }
  [class*="st-key-grid_side_"] > [data-testid="stLayoutWrapper"]:last-child { flex: 0 0 380px; }
}
[class*="st-key-col_"] { gap: 20px !important; }

/* ---------- type ---------- */
.stApp p, .stApp li { font-size: 14px; }
[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.stMarkdown [data-testid="stMarkdownContainer"] > div > p:last-child, .stMarkdown p:last-child { margin-bottom: 0; }
.title { font-family: 'Outfit', sans-serif; font-size: 30px; font-weight: 600; color: #0E1226; line-height: 1.2; margin: 0; }
.section { font-family: 'Outfit', sans-serif; font-size: 19px; font-weight: 600; color: #0E1226; margin: 0; line-height: 1.3; }
.muted, .caption { font-size: 14px; color: #5B6078; margin: 0; line-height: 1.45; }
.center { text-align: center; }
.alert-text { display: flex; align-items: flex-start; gap: 6px; color: #B42318; font-weight: 500; font-size: 14px;
  margin: 0; line-height: 1.35; }
.alert-text svg { flex: 0 0 16px; margin-top: 2px; }

/* ---------- status pills: black text, the background carries the meaning ---------- */
.pill { display: inline-flex; align-items: center; height: 28px; padding: 0 12px; border-radius: 999px; font-size: 12px;
  font-weight: 700; color: #0E1226; white-space: nowrap; line-height: 1; box-sizing: border-box; }
.pill-good { background: #BFEBCF; }
.pill-moderate { background: #FBE2A0; }
.pill-high { background: #FFD1B0; }
.pill-bad { background: #F8BDB6; }
.pill-neutral { background: #E4E1FF; }
.pill-brand { background: #F5B83D; }

/* ---------- cards ---------- */
[class*="st-key-card_"] { background: #FFFFFF; border: 1px solid #E6E8EF; border-radius: 24px; padding: 24px;
  gap: 14px !important; box-sizing: border-box; box-shadow: none; }
@media (max-width: 899px) { [class*="st-key-card_"] { padding: 20px; } }
.icon-circle { width: 44px; height: 44px; border-radius: 50%; background: #F0EEFF; display: inline-flex; align-items: center;
  justify-content: center; flex: 0 0 44px; }
.noscore { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 10px; padding: 8px 4px 4px; }
.noscore .muted { max-width: 380px; }

/* hero score card: indigo gradient (the light end top right, away from the small text), white text */
.st-key-card_hero { background: linear-gradient(225deg, #7A6CF2 0%, #3B2FC9 62%) !important; border: none !important;
  color: #FFFFFF; }
.hero { display: flex; flex-direction: column; gap: 18px; }
.hero .cap { color: #E4E1FF; }
.hero-score { font-family: 'Outfit', sans-serif; font-size: 72px; font-weight: 700; line-height: 1; color: #FFFFFF;
  letter-spacing: -1px; margin-top: 6px; }
.hero-of { font-family: 'Roboto', sans-serif; font-size: 15px; font-weight: 500; color: #E4E1FF; letter-spacing: 0;
  margin-left: 10px; }
.hero-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 14px; font-size: 14px;
  color: #FFFFFF; }
.hero-chart svg { display: block; width: 100%; height: auto; overflow: visible; }
.hero-pts { display: flex; justify-content: space-between; gap: 6px; margin-top: 8px; }
.hero-pt { display: flex; flex-direction: column; align-items: center; min-width: 0; flex: 1 1 0; }
.hero-pt b { font-size: 14px; color: #FFFFFF; }
.hero-pt span { font-size: 12px; color: #E4E1FF; white-space: nowrap; }
.st-key-card_hero .stButton > button { background: #FFFFFF !important; border: none !important; }
.st-key-card_hero .stButton > button p { color: #3B2FC9 !important; }
@media (min-width: 900px) { .hero-score { font-size: 88px; } }

/* estimated limit */
.limit-big { font-family: 'Outfit', sans-serif; font-size: 30px; font-weight: 700; color: #0E1226; line-height: 1.15; }
.lc-sub { font-size: 14px; color: #5B6078; margin-top: 6px; line-height: 1.45; }
.lc-stats { display: flex; gap: 18px; flex-wrap: wrap; font-size: 13px; color: #5B6078; padding-top: 12px;
  border-top: 1px solid #E6E8EF; margin-top: 4px; }
.lc-stats b { color: #0E1226; font-weight: 700; }

/* quick actions: four 60px circles with a label under each */
.st-key-quick_row { flex-wrap: nowrap !important; justify-content: space-between; gap: 6px !important; }
.st-key-quick_row > [data-testid="stElementContainer"] { flex: 1 1 0; min-width: 0; }
[class*="st-key-qa_"] button { flex-direction: column !important; gap: 8px !important; background: transparent !important;
  border: none !important; box-shadow: none !important; height: auto !important; min-height: 0 !important;
  padding: 2px 0 !important; width: 100%; border-radius: 16px !important; }
[class*="st-key-qa_"] button::before { content: ""; width: 60px; height: 60px; border-radius: 50%; display: block;
  flex: 0 0 60px; }
[class*="st-key-qa_"] button p { font-size: 13px !important; font-weight: 500 !important; color: #0E1226 !important;
  white-space: nowrap; }
[class*="st-key-qa_"] button:hover::before { filter: brightness(0.96); }

/* tile grid (Business health): 3 columns on a laptop */
.tiles { display: grid; grid-template-columns: 1fr; gap: 16px; }
@media (min-width: 600px) { .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (min-width: 1100px) { .tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
.tile { background: #FFFFFF; border: 1px solid #E6E8EF; border-radius: 24px; padding: 20px; display: flex;
  flex-direction: column; gap: 8px; min-width: 0; }
.tile-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.tile-title { font-family: 'Outfit', sans-serif; font-size: 17px; font-weight: 600; color: #0E1226; line-height: 1.25; }
.tile-desc { font-size: 13px; color: #5B6078; line-height: 1.45; }

/* rows inside cards */
.row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 13px 0;
  border-bottom: 1px solid #E6E8EF; font-size: 14px; }
.row:last-child { border-bottom: none; padding-bottom: 2px; }
.row:first-child { padding-top: 2px; }
.row .k { color: #5B6078; display: flex; align-items: center; gap: 12px; }
.row .v { color: #0E1226; text-align: right; font-weight: 500; }
.reason { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 0;
  border-bottom: 1px solid #E6E8EF; font-size: 14px; }
.reason:last-child { border-bottom: none; padding-bottom: 2px; }
.reason:first-child { padding-top: 2px; }
.reason .txt { color: #0E1226; line-height: 1.4; }
.reason .dir { flex: 0 0 auto; }

/* activity rows (Home) */
.act { display: flex; align-items: center; gap: 12px; padding: 12px 0; border-bottom: 1px solid #E6E8EF; }
.act:last-child { border-bottom: none; padding-bottom: 2px; }
.act:first-child { padding-top: 2px; }
.act-main { flex: 1 1 auto; min-width: 0; }
.act-title { font-size: 14px; font-weight: 500; color: #0E1226; overflow-wrap: anywhere; }
.act-date { font-size: 12px; color: #5B6078; margin-top: 2px; }
.st-key-activity_head { gap: 8px !important; align-items: center !important; }

/* expandable rows (History and the lender list on a phone): details/summary, chevron turns when open */
.xrow { border-bottom: 1px solid #E6E8EF; }
.xrow:last-child { border-bottom: none; }
.xrow summary { list-style: none; display: flex; align-items: center; gap: 10px; padding: 12px 2px; cursor: pointer;
  border-radius: 8px; }
.xrow summary::-webkit-details-marker { display: none; }
.x-main { flex: 1 1 auto; min-width: 0; font-size: 14px; font-weight: 500; color: #0E1226; }
.x-main .x-sub { display: block; font-size: 12px; font-weight: 400; color: #5B6078; margin-top: 2px; }
.x-side { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; white-space: nowrap; text-align: right; }
.x-chev { display: inline-flex; transition: transform 0.15s; }
.xrow[open] .x-chev { transform: rotate(90deg); }
.x-body { font-size: 13px; color: #5B6078; padding: 0 2px 12px 2px; line-height: 1.45; }
.x-body .row { font-size: 13px; padding: 8px 0; }

/* tables; a wide table scrolls inside its card, never the page */
.tbl-wrap { overflow-x: auto; max-width: 100%; }
table.tbl { width: 100%; border-collapse: collapse; font-size: 14px; margin: 0; }
.tbl th { text-align: left; color: #6B7089; font-weight: 700; font-size: 12px; letter-spacing: .07em;
  text-transform: uppercase; padding: 10px 12px; border: none; border-bottom: 1.5px solid #E6E8EF; white-space: nowrap;
  background: transparent; }
.tbl td { padding: 14px 12px; border: none; border-bottom: 1px solid #E6E8EF; color: #0E1226; white-space: nowrap;
  background: transparent; vertical-align: middle; }
.tbl tr:last-child td { border-bottom: none; }
.tbl td.note { white-space: normal; min-width: 180px; color: #5B6078; }
.tbl .who { display: inline-flex; align-items: center; gap: 10px; }
.only-wide { display: none; }
@media (min-width: 900px) { .only-wide { display: block; } .only-narrow { display: none !important; } }

/* ---------- buttons: pills, 48px ---------- */
.stButton > button, .stFormSubmitButton > button, .stLinkButton > a, .stDownloadButton > button {
  border-radius: 999px !important; min-height: 48px;
  height: 48px; font-weight: 700; padding: 0 22px; box-shadow: none !important; }
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primaryFormSubmit"], .stLinkButton > a[kind="primary"],
.stDownloadButton > button[kind="primary"] { background: #3B2FC9; border: none; color: #FFFFFF; }
.stDownloadButton > button[kind="primary"] p { font-size: 15px; font-weight: 700; color: #FFFFFF; }
.stDownloadButton > button[kind="primary"]:disabled { background: #DCD8FB; }
.stDownloadButton > button[kind="primary"]:disabled p { color: #2F25A8; }
.stButton > button[kind="primary"] p, .stFormSubmitButton > button[kind="primaryFormSubmit"] p,
.stLinkButton > a[kind="primary"] p { font-size: 15px; font-weight: 700; color: #FFFFFF; }
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primaryFormSubmit"]:hover { background: #2F25A8; }
.stButton > button[kind="primary"]:disabled { background: #DCD8FB; }
.stButton > button[kind="primary"]:disabled p { color: #2F25A8; }
.stButton > button[kind="secondary"], .stFormSubmitButton > button[kind="secondaryFormSubmit"],
.stLinkButton > a[kind="secondary"] { background: #FFFFFF; border: 1.5px solid #CFCBF5; }
.stButton > button[kind="secondary"] p, .stFormSubmitButton > button[kind="secondaryFormSubmit"] p,
.stLinkButton > a[kind="secondary"] p { color: #3B2FC9; font-weight: 700; font-size: 14px; }
.stButton > button[kind="secondary"]:hover { background: #F0EEFF; border-color: #3B2FC9; }
.stButton > button[kind="tertiary"] { min-height: 32px; height: auto; padding: 2px 4px; border-radius: 8px !important; }
.stButton > button[kind="tertiary"] p { color: #3B2FC9; font-weight: 700; font-size: 14px; }
.stButton > button[kind="tertiary"]:hover p { text-decoration: underline; }
/* danger pills: white, red text, light red border */
:is(.st-key-sign_out, .st-key-decline, .st-key-delete_results, .st-key-confirm_delete) button {
  background: #FFFFFF !important; border: 1.5px solid #F3C1BC !important; }
:is(.st-key-sign_out, .st-key-decline, .st-key-delete_results, .st-key-confirm_delete) button p { color: #B42318 !important; }
:is(.st-key-sign_out, .st-key-decline, .st-key-delete_results, .st-key-confirm_delete) button:hover {
  background: #FEF3F2 !important; border-color: #B42318 !important; }
/* one visible keyboard focus ring for every control */
.stApp button:focus-visible, .stApp summary:focus-visible, .stApp a:focus-visible, .stApp [role="slider"]:focus-visible,
.stApp [role="radio"]:focus-visible { outline: 2px solid #3B2FC9 !important; outline-offset: 2px; }
[data-testid="stMain"]:focus-visible, [data-testid="stAppViewContainer"]:focus-visible,
[data-testid="stMainBlockContainer"]:focus-visible { outline: 2px solid #3B2FC9; outline-offset: -2px; }

/* ---------- menu dialog (phone) ---------- */
[data-testid="stDialog"] div:has(> [role="dialog"]) { width: min(430px, calc(100vw - 32px)) !important;
  max-width: 430px !important; background: transparent !important; box-shadow: none !important; border: none !important; }
[data-testid="stDialog"] [role="dialog"] { width: 100% !important; max-width: 100% !important;
  border-radius: 24px !important; background: #FFFFFF; font-family: 'Roboto', sans-serif;
  box-shadow: 0 20px 60px rgba(14,18,38,0.22) !important; }
[data-testid="stDialog"] [role="dialog"] h2, [data-testid="stDialog"] [role="dialog"] h2 * { font-family: 'Outfit', sans-serif;
  font-size: 22px !important; font-weight: 600 !important; color: #0E1226; }
[class*="st-key-menu_"] button { background: transparent !important; border: none !important;
  justify-content: flex-start !important; gap: 14px !important; height: 52px !important; min-height: 52px !important;
  padding: 0 4px !important; border-radius: 999px !important; }
[class*="st-key-menu_"] button > div { flex: 1 1 auto; text-align: left !important; justify-content: flex-start !important; }
[class*="st-key-menu_"] button:hover { background: #F6F7F9 !important; }
[class*="st-key-menu_"] button::before { content: ""; width: 40px; height: 40px; border-radius: 50%; display: block; flex: 0 0 40px; }
[class*="st-key-menu_"] button p { color: #0E1226 !important; font-size: 15px !important; font-weight: 500 !important;
  text-align: left !important; }
.st-key-menu_signout button p { color: #B42318 !important; }

/* ---------- tab bar (phone), fixed to the bottom of the screen ---------- */
.st-key-bottom_nav { position: fixed; left: 0; right: 0; bottom: 0; width: 100% !important; box-sizing: border-box;
  background: #FFFFFF; border-top: 1px solid #E6E8EF; padding: 6px max(8px, calc(50% - 300px)) 8px; z-index: 1000;
  flex-wrap: nowrap !important; gap: 0 !important; }
.st-key-bottom_nav [data-testid="stElementContainer"], .st-key-bottom_nav .stButton { flex: 1 1 0; min-width: 0; }
.st-key-bottom_nav button { background: transparent !important; border: none !important;
  flex-direction: column !important; gap: 3px !important; min-height: 54px !important; height: auto !important;
  padding: 2px 0 !important; width: 100%; border-radius: 14px !important; }
.st-key-bottom_nav button::before { content: ""; width: 24px; height: 24px; display: block; }
.st-key-bottom_nav button p { font-size: 12px !important; color: #5B6078 !important; font-weight: 500 !important;
  white-space: nowrap; }

/* ---------- inputs: 52px, 16px radius ---------- */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { font-size: 13px !important; font-weight: 500 !important;
  color: #0E1226; }
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"] {
  background: #FFFFFF !important; border: 1.5px solid #E1E3EC !important; border-radius: 16px !important;
  height: 52px !important; min-height: 52px; overflow: hidden; box-sizing: border-box; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within {
  border-color: #3B2FC9 !important; box-shadow: 0 0 0 3px rgba(59,47,201,0.22); }
[data-testid="stTextInputRootElement"] input, [data-testid="stNumberInputContainer"] input { font-size: 15px !important;
  padding-left: 16px !important; background: #FFFFFF !important; height: 100% !important; color: #0E1226; }
[data-testid="stTextInputRootElement"] input::placeholder { color: #5B6078; opacity: 1; }
[data-testid="stTextInputRootElement"] button { background: #FFFFFF !important; }
[data-testid="stTextInputRootElement"] button:focus-visible { outline: 2px solid #3B2FC9 !important; outline-offset: -4px;
  border-radius: 12px; }
[data-testid="stNumberInput"] button { background: #FFFFFF !important; border: none !important; }
[data-testid="InputInstructions"] { display: none; }
[data-testid="stCheckbox"] label p { font-size: 14px !important; }
[data-testid="stCheckbox"] label:has(input:focus-visible) { outline: 2px solid #3B2FC9; outline-offset: 2px; border-radius: 6px; }
[data-testid="stTextArea"] textarea { font-size: 14px !important; background: #FFFFFF !important; }
[data-testid="stTextAreaRootElement"] { border: 1.5px solid #E1E3EC !important; border-radius: 16px !important;
  background: #FFFFFF !important; overflow: hidden; }
[data-testid="stTextAreaRootElement"]:focus-within { border-color: #3B2FC9 !important; box-shadow: 0 0 0 3px rgba(59,47,201,0.22); }

/* uploader: dashed drop zone; the widget's own type list is replaced by the card's caption */
[data-testid="stFileUploaderDropzone"] { border: 2px dashed #CFCBF5 !important; border-radius: 20px !important;
  background: #F0EEFF !important; padding: 22px 16px !important; }
[data-testid="stFileUploaderDropzone"]:focus-within { border-color: #3B2FC9 !important; }
[data-testid="stFileUploaderDropzoneInstructions"] span { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"] > div::after { content: "or drop the file here"; font-size: 13px;
  color: #5B6078; }
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"] { color: #3B2FC9; }
[data-testid="stFileUploaderDropzone"] button { border-radius: 999px !important; border: 1.5px solid #CFCBF5 !important;
  background: #FFFFFF !important; color: #3B2FC9 !important; font-weight: 700; }

/* lender choice as radio rows */
.st-key-apply_lender [data-testid="stRadioGroup"] { gap: 8px; width: 100%; flex-direction: column; }
.st-key-apply_lender, .st-key-apply_lender [data-testid="stRadio"], .st-key-apply_lender [data-testid="stRadioGroup"] > div {
  width: 100% !important; }
.st-key-apply_lender [data-testid="stRadioOption"] { width: 100%; box-sizing: border-box; margin: 0; padding: 14px 16px;
  border: 1.5px solid #E1E3EC; border-radius: 16px; background: #FFFFFF; }
.st-key-apply_lender [data-testid="stRadioOption"]:has(input:checked) { border-color: #3B2FC9; background: #F0EEFF; }
.st-key-apply_lender [data-testid="stRadioOption"]:has(input:focus-visible) { outline: 2px solid #3B2FC9; outline-offset: 2px; }

/* filter chips: pills, the chosen one indigo with white text */
:is(.st-key-lender_filter, .st-key-lender_decided_filter) [data-testid="stButtonGroup"] { flex-wrap: wrap; gap: 8px; }
:is(.st-key-lender_filter, .st-key-lender_decided_filter) button { min-height: 36px !important; height: 36px;
  border-radius: 999px !important; border: 1.5px solid #E1E3EC !important; background: #FFFFFF !important;
  padding: 0 16px !important; }
:is(.st-key-lender_filter, .st-key-lender_decided_filter) button p { font-size: 13px !important; color: #0E1226 !important;
  font-weight: 700 !important; }
:is(.st-key-lender_filter, .st-key-lender_decided_filter) :is(button[kind="pillsActive"], button[aria-checked="true"],
  button[aria-pressed="true"]) { border-color: #3B2FC9 !important; background: #3B2FC9 !important; }
:is(.st-key-lender_filter, .st-key-lender_decided_filter) :is(button[kind="pillsActive"], button[aria-checked="true"],
  button[aria-pressed="true"]) p { color: #FFFFFF !important; }

/* Check score: numbered steps, the reading card */
.steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 16px; }
.stApp .steps li { display: flex; gap: 12px; align-items: flex-start; margin: 0; font-size: 14px; color: #0E1226; line-height: 1.45; }
.num { width: 30px; height: 30px; border-radius: 50%; background: #F0EEFF; color: #3B2FC9; font-weight: 700;
  font-size: 13px; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 30px;
  font-family: 'Outfit', sans-serif; }
.lock-line { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #5B6078; line-height: 1.4; }
.lock-line svg { flex: 0 0 16px; }
.progress { height: 8px; border-radius: 999px; background: #F0EEFF; overflow: hidden; position: relative; margin-top: 14px; }
.progress span { position: absolute; top: 0; bottom: 0; width: 40%; border-radius: 999px; background: #3B2FC9;
  animation: nuru-progress 1.1s ease-in-out infinite; }
@keyframes nuru-progress { 0% { left: -40%; } 100% { left: 100%; } }
@media (prefers-reduced-motion: reduce) { .progress span { animation: none; left: 0; width: 100%; opacity: .5; } }

/* Reasons: test an amount */
.big-amount { font-family: 'Outfit', sans-serif; font-size: 40px; font-weight: 700; color: #0E1226; line-height: 1.1; }
.band-line { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 14px; color: #0E1226; }
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] { display: none; }

/* sent */
.done-circle { width: 88px; height: 88px; border-radius: 50%; margin: 8px auto 0 auto; background: #3B2FC9;
  display: flex; align-items: center; justify-content: center; }

/* profile */
.profile-id { display: flex; align-items: center; gap: 16px; }
.avatar-lg { width: 64px; height: 64px; flex: 0 0 64px; border-radius: 50%; background: #F0EEFF; color: #3B2FC9;
  font-size: 22px; font-weight: 700; display: flex; align-items: center; justify-content: center;
  font-family: 'Outfit', sans-serif; }
.profile-id .section { word-break: break-word; }
.profile-id .muted { word-break: break-all; }
[data-testid="stForm"] { border: none; padding: 0; }
[data-testid="stExpander"] details { background: #FFFFFF; border-radius: 16px !important; border: 1px solid #E6E8EF !important; }
[data-testid="stExpander"] summary p { font-size: 14px; font-weight: 500; }

/* ---------- lender and admin ---------- */
.st-key-qtable, .st-key-utable { overflow-x: auto; gap: 0 !important; }
.trow { display: flex; align-items: center; }
.trow.thead { border-bottom: 1.5px solid #E6E8EF; }
.trow .tref { flex: 0 0 96px; }
.tcells { flex: 1 1 auto; display: grid; align-items: center; column-gap: 12px; min-width: 0; }
.thead span, .thead .tcells span { font-size: 12px; color: #6B7089; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; padding: 10px 0; white-space: nowrap; }
.tcells .c { font-size: 14px; color: #0E1226; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 12px 0;
  display: flex; align-items: center; gap: 8px; min-width: 0; }
.tcells .c .t { overflow: hidden; text-overflow: ellipsis; }
.tcells .c.m { color: #5B6078; }
.tcells .c:has(> .m) { white-space: normal; line-height: 1.3; }     /* "Not enough income data" wraps, never cut */
.tcells .c .m { color: #5B6078; }
@media (min-width: 1100px) { .st-key-col_review_a .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.qgrid { grid-template-columns: 1.6fr 1.4fr 0.55fr 0.95fr 1.3fr 0.9fr; }
.ugrid { grid-template-columns: 2.4fr 1.6fr 1.1fr; }
[class*="st-key-qrow_"], [class*="st-key-urow_"] { flex-wrap: nowrap !important; align-items: center !important;
  gap: 0 !important; border-bottom: 1px solid #E6E8EF; box-sizing: border-box; }
[class*="st-key-qrow_"]:last-child, [class*="st-key-urow_"]:last-child { border-bottom: none; }
[class*="st-key-qrow_"] > [data-testid="stElementContainer"]:first-child { flex: 0 0 96px; width: 96px !important; }
[class*="st-key-qrow_"] > [data-testid="stElementContainer"]:has(.tcells) { flex: 1 1 auto; min-width: 0; }
/* Decided: the repayment column and the Record action (110px) */
.dgrid { grid-template-columns: 1.5fr 1.3fr 0.5fr 0.85fr 0.85fr 1.9fr; }
[class*="st-key-qrow_"] > [class*="st-key-rec_"],
[class*="st-key-qrow_"] > [data-testid="stElementContainer"]:has(.ract-none) { flex: 0 0 110px; width: 110px !important;
  display: flex; justify-content: flex-end; }
.ract-h, .ract-none { flex: 0 0 110px; width: 110px; display: block; }
[class*="st-key-rec_"] button { min-height: 34px !important; height: 34px !important; padding: 0 16px !important; }
[class*="st-key-rec_"] button p { font-size: 13px !important; text-decoration: none !important; }
[class*="st-key-rec_"] button, [class*="st-key-rec_"] button > div { justify-content: center !important; }
.trow.thead:has(.dgrid), [class*="st-key-qrow_"]:has(.dgrid) { min-width: 980px; }
.tcells .c:has(.rcell) { white-space: normal; overflow: visible; }
.rcell { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.rdue { font-size: 12px; color: #5B6078; white-space: nowrap; }
.rsum { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
@media (min-width: 600px) { .rsum { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
.rsum-i { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; padding: 14px 16px;
  border: 1px solid #E6E8EF; border-radius: 18px; min-width: 0; }
.rsum-n { font-family: 'Outfit', sans-serif; font-size: 28px; font-weight: 700; color: #0E1226; line-height: 1; }
.ok-line { font-size: 14px; font-weight: 500; color: #0E1226; }
.repay-confirm { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 15px; color: #0E1226; }
.st-key-repay_buttons { justify-content: flex-end; gap: 10px !important; }
[class*="st-key-qrow_"] button { min-height: 36px !important; height: 36px !important; padding: 2px 0 !important;
  justify-content: flex-start !important; }
[class*="st-key-qrow_"] button > div { justify-content: flex-start !important; }
[class*="st-key-qrow_"] button p { font-weight: 700 !important; font-size: 14px !important; color: #3B2FC9 !important; }
.st-key-qtable { display: none !important; }
.st-key-qlist { gap: 12px !important; }
[class*="st-key-qcard_"] { border: 1px solid #E6E8EF; border-radius: 20px; padding: 16px; gap: 10px !important; }
.qc-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.qc-ref { font-weight: 700; color: #3B2FC9; font-size: 14px; }
.qc-who { display: flex; align-items: center; gap: 10px; margin-top: 8px; font-weight: 500; overflow-wrap: anywhere; }
@media (min-width: 900px) {
  .st-key-qtable { display: flex !important; }
  .st-key-qlist, [data-testid="stLayoutWrapper"]:has(> .st-key-qlist) { display: none !important; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-qtable) { display: block !important; }
}
.st-key-qtable .thead, [class*="st-key-qrow_"] { min-width: 860px; }

/* Users: the same row on a laptop; on a phone the cells stack (email, then role and status) */
[class*="st-key-urow_"] > [data-testid="stElementContainer"]:first-child { flex: 1 1 auto; min-width: 0; }
[class*="st-key-urow_"] > [data-testid="stElementContainer"]:last-child { flex: 0 0 110px; width: 110px !important;
  display: flex; justify-content: flex-end; }
.uact-h { flex: 0 0 110px; }
[class*="st-key-urow_"] .stButton > button { min-height: 34px !important; height: 34px !important; padding: 0 16px !important; }
[class*="st-key-urow_"] .stButton > button p { font-size: 13px !important; }
.uself { font-size: 13px; color: #5B6078; padding: 0 6px; white-space: nowrap; }
.ugrid-head { display: none; }
@media (max-width: 899px) {
  .ugrid { grid-template-columns: 1fr; row-gap: 0; }
  .ugrid .c { white-space: normal; overflow: visible; }
  .ugrid .c.email { font-weight: 500; word-break: break-all; padding-bottom: 2px; }
  .ugrid .c:not(.email) { padding: 3px 0; }
  .ugrid .c.email .avatar { display: none; }
}
@media (min-width: 900px) {
  .ugrid-head { display: flex; }
  .st-key-utable .trow, [class*="st-key-urow_"] { min-width: 640px; }
}
.arow { padding: 12px 0; border-bottom: 1px solid #E6E8EF; }
.arow:last-child { border-bottom: none; }
.a-what { font-size: 14px; color: #0E1226; line-height: 1.4; }
.a-sub { font-size: 12px; color: #5B6078; margin-top: 2px; word-break: break-all; }

/* lender review */
.decision-out { display: flex; flex-direction: column; gap: 8px; }
.note-box { font-size: 14px; color: #0E1226; background: #F6F7F9; border: 1px solid #E6E8EF; border-radius: 16px;
  padding: 12px 14px; white-space: pre-wrap; word-break: break-word; }
.st-key-decision_buttons { flex-wrap: nowrap !important; gap: 10px !important; }
.st-key-decision_buttons > [data-testid="stElementContainer"] { flex: 1 1 0; min-width: 0; }
.st-key-decision_buttons button { width: 100%; }

/* admin overview */
.metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
@media (min-width: 1100px) { .metrics { grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 16px; } }
.metric { background: #FFFFFF; border: 1px solid #E6E8EF; border-radius: 24px; padding: 20px; box-sizing: border-box;
  min-width: 0; display: flex; flex-direction: column; gap: 10px; }
.metric .m-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.metric .m-value { font-family: 'Outfit', sans-serif; font-size: 36px; font-weight: 700; color: #0E1226; line-height: 1.05; }
.metric .m-sub { font-size: 12px; color: #5B6078; }
.bars { display: flex; flex-direction: column; gap: 14px; }
.bar-row { display: grid; grid-template-columns: 96px minmax(0, 1fr) 84px; align-items: center; gap: 12px; font-size: 14px; }
.bar-track { height: 12px; border-radius: 999px; background: #F0EEFF; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 999px; }
.bar-val { text-align: right; color: #5B6078; font-size: 13px; white-space: nowrap; }
.pwd-line { font-size: 13px; color: #5B6078; line-height: 1.4; }
.st-key-audit_pager { align-items: center; gap: 10px !important; }
</style>
"""


def css() -> str:
    return CSS.replace("</style>", _icon_css() + "\n</style>")


# Sign in and Create account only (injected by those two pages, after the main theme). NO tilt or perspective here.
AUTH_TICK = GOLD
AUTH_CSS = """
<style>
.stApp:has(.auth-band) { background: #FFFFFF; }
[data-testid="stMainBlockContainer"]:has(.auth-band) { padding: 0 0 32px 0 !important; max-width: 600px !important; }

/* phone: a short dark header strip with the icon and the headline; the form follows on white */
.auth-band { background: linear-gradient(160deg, #0E1226 0%, #171B3D 100%); color: #FFFFFF; padding: 22px 20px 24px 20px;
  display: flex; flex-direction: column; gap: 14px; }
.auth-mark { width: 44px; height: 44px; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center;
  background: #3B2FC9; overflow: hidden; flex: 0 0 44px; }
.auth-mark img { width: 100%; height: 100%; object-fit: contain; display: block; }
.auth-mark:has(img) { background: transparent; border-radius: 0; }       /* the brand icon sits on the navy itself */
.auth-headline { font-family: 'Outfit', sans-serif; font-size: 26px; font-weight: 700; line-height: 1.15; color: #FFFFFF;
  margin: 0; letter-spacing: -0.3px; }
.auth-lead { font-size: 15px; color: #C9CCE0; line-height: 1.5; margin: 0; display: none; }
.stApp ul.auth-points { list-style: none; margin: 0; padding: 0; display: none; flex-direction: column; gap: 12px; }
.stApp ul.auth-points li { display: flex; align-items: center; gap: 10px; margin: 0; padding: 0; font-size: 15px;
  line-height: 1.35; color: #FFFFFF; }
.auth-points svg { flex: 0 0 18px; }

/* the form column (white) */
.st-key-auth_card { background: #FFFFFF; padding: 24px 20px 8px 20px; width: auto !important; box-sizing: border-box;
  gap: 16px !important; }
.st-key-auth_card [data-testid="stForm"] { border: none; padding: 0; border-radius: 0; }
.st-key-auth_card [data-testid="stForm"] [data-testid="stVerticalBlock"] { gap: 14px; }
.auth-logo { margin-bottom: 6px; }
.auth-logo img { width: 132px; height: auto; display: block; }
.auth-title { font-family: 'Outfit', sans-serif; font-size: 30px; font-weight: 600; line-height: 1.15; color: #0E1226;
  margin: 0; letter-spacing: -0.3px; }
.auth-sub { font-size: 14px; color: #5B6078; margin: 4px 0 0 0; }
.auth-hint { font-size: 13px; color: #5B6078; text-align: center; margin: 0; line-height: 1.4; }

/* the account type: two pill chips, the chosen one indigo with white text */
.st-key-signup_type [data-testid="stButtonGroup"] { width: 100%; }
.st-key-signup_type [data-testid="stButtonGroup"] > div { display: flex; width: 100%; gap: 10px; }
.st-key-signup_type button { flex: 1 1 0; min-height: 44px; height: 44px; border-radius: 999px !important;
  background: #FFFFFF; border: 1.5px solid #E1E3EC !important; }
.st-key-signup_type button p { font-size: 14px; font-weight: 700; color: #0E1226; }
.st-key-signup_type button[aria-checked="true"] { background: #3B2FC9 !important; border-color: #3B2FC9 !important; }
.st-key-signup_type button[aria-checked="true"] p { color: #FFFFFF; }
.st-key-signup_type button:focus-visible { outline: 2px solid #3B2FC9; outline-offset: 2px; }

/* full-width submit pill; a small spinner shows on it while the sign-in or sign-up runs */
.st-key-auth_card .stFormSubmitButton > button { width: 100%; gap: 8px; }
.stApp[data-test-script-state="running"] .st-key-auth_card [data-testid="stForm"]:focus-within .stFormSubmitButton > button {
  background: #2F25A8; pointer-events: none; cursor: progress; }
.stApp[data-test-script-state="running"] .st-key-auth_card [data-testid="stForm"]:focus-within .stFormSubmitButton > button::after {
  content: ""; width: 16px; height: 16px; flex: 0 0 16px; box-sizing: border-box; border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.45); border-top-color: #FFFFFF; animation: auth-spin 0.7s linear infinite; }
@keyframes auth-spin { to { transform: rotate(360deg); } }

/* "New to Nuru? Create an account": muted question, indigo link (the label's bold part) */
.st-key-to_signup button, .st-key-to_signin button { min-height: 32px !important; height: auto !important;
  padding: 4px 8px !important; border-radius: 8px !important; }
.st-key-to_signup button p, .st-key-to_signin button p { font-size: 14px !important; font-weight: 400 !important;
  color: #5B6078 !important; }
.st-key-to_signup button p strong, .st-key-to_signin button p strong { color: #3B2FC9; font-weight: 700; }

.auth-error { display: flex; align-items: flex-start; gap: 6px; margin: -4px 0 0 0; font-size: 13px; font-weight: 500;
  line-height: 1.35; color: #B42318; }
.auth-error svg { flex: 0 0 16px; margin-top: 1px; }
.auth-foot { display: flex; align-items: center; justify-content: center; gap: 6px; margin: 0 20px;
  font-size: 13px; line-height: 1.35; color: #5B6078; text-align: center; }
.auth-foot svg { flex: 0 0 14px; }

/* laptop (from 900px): two columns. Left: the navy panel (fixed); right: white with the logo and the form. */
@media (min-width: 900px) {
  [data-testid="stMainBlockContainer"]:has(.auth-band) { max-width: none !important; margin: 0 !important;
    padding: 0 0 0 48% !important; }
  [data-testid="stMainBlockContainer"]:has(.auth-band) > [data-testid="stVerticalBlock"] { min-height: 100vh;
    justify-content: center; align-items: center; gap: 18px; padding: 40px 32px; box-sizing: border-box; }
  .auth-band { position: fixed; top: 0; left: 0; bottom: 0; width: 48%; box-sizing: border-box;
    padding: 56px clamp(40px, 6vw, 96px); justify-content: center; gap: 26px; }
  .auth-mark { width: 56px; height: 56px; border-radius: 16px; flex-basis: 56px; }
  .auth-headline { font-size: 48px; line-height: 1.08; max-width: 560px; letter-spacing: -0.8px; }
  .auth-lead { display: block; max-width: 480px; }
  .stApp ul.auth-points { display: flex; }
  [data-testid="stLayoutWrapper"]:has(> .st-key-auth_card) { width: 420px; max-width: 100%; margin: 0 auto; }
  .st-key-auth_card { width: 420px !important; max-width: 100%; padding: 0; }
  .auth-title { font-size: 34px; }
  .auth-foot { margin: 0; }
}
</style>
"""

# Vendor Check score, Result and Reasons only: the ONE place a tilt is used. Off for prefers-reduced-motion.
TILT_FROM = "perspective(1800px) rotateY(-32deg) rotateZ(4deg) translateX(220px) scale(.86)"
EASE = "cubic-bezier(.22,.8,.2,1)"
MOTION_CSS = f"""
<style>
@media (prefers-reduced-motion: no-preference) {{
  @keyframes nuru-tilt-in {{ from {{ opacity: 0; transform: {TILT_FROM}; }} to {{ opacity: 1; transform: none; }} }}
  @keyframes nuru-tilt-out {{ from {{ opacity: 1; transform: none; }}
    to {{ opacity: 0; transform: perspective(1800px) rotateY(32deg) rotateZ(-4deg) translateX(-160px) scale(.9); }} }}
  .stApp:has(.tilt-in-hero) .st-key-card_hero, .stApp:has(.tilt-in-reasons) .st-key-card_reasons {{
    animation: nuru-tilt-in .9s {EASE} both; transform-origin: 70% 50%; }}
  .stApp:has(.tilt-out-upload) .st-key-card_upload {{ animation: nuru-tilt-out .6s {EASE} forwards;
    transform-origin: 30% 50%; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .st-key-card_hero, .st-key-card_reasons, .st-key-card_upload {{ animation: none !important; transform: none !important; }}
}}
</style>
"""


def inject_auth() -> None:
    """The Sign in / Create account styles, injected like the main theme (st.markdown, hidden wrapper)."""
    st.markdown(AUTH_CSS, unsafe_allow_html=True)


def inject_motion(*classes: str) -> None:
    """The tilt animation (vendor Check score, Result, Reasons only). `classes` switch it on for this run, e.g.
    "tilt-in-hero" right after a score was computed, "tilt-out-upload" while it is being computed."""
    marks = "".join(f'<span class="{c}"></span>' for c in classes)
    st.markdown(MOTION_CSS + (f'<div class="motion-marks" hidden>{marks}</div>' if marks else ""), unsafe_allow_html=True)


def inject() -> None:
    """Inject the theme with st.markdown: style-only st.html goes to a separate event container that can be dropped on
    a rerun, which left some screens unstyled. The empty wrapper is hidden (a hidden <style> still applies)."""
    st.markdown(css(), unsafe_allow_html=True)
