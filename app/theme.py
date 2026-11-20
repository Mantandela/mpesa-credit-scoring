"""Alama theme (the approved "Finova style"): Roboto, a phone-style frame, white cards, purple primary.

The four base colours are in .streamlit/config.toml; everything else is the CSS below, injected once per run with
st.html (a style-only st.html takes no space in the layout).

Layout: on screens wider than 600px the app is a centred 430px phone frame on a soft gradient, scrolling inside the
frame, with the tab bar fixed to the frame's bottom edge. At 600px and below the frame fills the screen.

Containers are styled through their keys: "card_*" white card, "hero" gradient card, "row_*" list row with a chevron,
"topbar" the top bar ("topbar_menu" its menu button), "menu_*" the items of the menu dialog, "bottom_nav" the tab bar.

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

ICONS = {
    "logo": '<path d="M4 17l5-5 4 4 7-8"/><path d="M15 8h5v5"/>',
    "check": '<path d="M5.5 12.5l4 4L18.5 7.5"/>',
    "check_circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
    "upload": '<path d="M12 16V5"/><path d="M7 10l5-5 5 5"/><path d="M5 19h14"/>',
    "chevron": '<path d="M9 6l6 6-6 6"/>',
    "menu": '<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h10"/>',
    "bell": '<path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
    "home": '<path d="M4 11l8-7 8 7"/><path d="M6 9.5V20h12V9.5"/><path d="M10 20v-5h4v5"/>',
    "gauge": '<path d="M4 16a8 8 0 1 1 16 0"/><path d="M12 16l4-5"/><path d="M4 19h16"/>',
    "receipt": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6"/><path d="M9 12h6"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
    "wallet": '<rect x="3" y="6" width="18" height="13" rx="3"/><path d="M3 10h18"/><path d="M15.5 14.5h2.5"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "grid": ('<rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/>'
             '<rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/>'),
    "inbox": '<path d="M4 13l2.5-7h11L20 13v6H4z"/><path d="M4 13h4.5l1 2h5l1-2H20"/>',
    "shield": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>',
    "chart": '<path d="M4 19h16"/><path d="M6 15l4-4 3 3 5-6"/>',
    "logout": '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4"/><path d="M10 16l-4-4 4-4"/><path d="M6 12h10"/>',
}


def svg(name: str, color: str = PURPLE, size: int = 24, stroke: float = 2) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')


def icon_uri(name: str, color: str, stroke: float = 2) -> str:
    """The icon as a CSS url() (for button icons, which cannot hold SVG markup)."""
    return f'url("data:image/svg+xml;utf8,{quote(svg(name, color, stroke=stroke))}")'


NAV_ICONS = {"home": "home", "score": "gauge", "history": "receipt", "profile": "user"}
MENU_ICONS = {"home": "home", "score": "gauge", "apply": "wallet", "history": "receipt", "profile": "user", "signout": "logout"}


def _icon_css() -> str:
    out = [f".st-key-topbar_menu button::before {{ background: {icon_uri('menu', INK)} center / 22px no-repeat; }}"]
    for page, ico in NAV_ICONS.items():
        out.append(f".st-key-nav_{page} button::before {{ background: {icon_uri(ico, MUTED)} center / 24px no-repeat; }}")
    for key, ico in MENU_ICONS.items():
        out.append(f".st-key-menu_{key} button::before {{ background: #E8DFFB {icon_uri(ico, PURPLE_DARK)} center / 20px no-repeat; }}")
    return "\n".join(out)


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');

/* ---------- page and phone frame ---------- */
[data-testid="stElementContainer"]:has(style) { display: none !important; }   /* style-only markdown takes no space */
html, body { overflow-x: hidden; }
html, body, .stApp { font-family: 'Roboto', sans-serif; color: #1D1B3A; }
.stApp { background: linear-gradient(160deg, #E9E3FA 0%, #DCD2F7 100%) fixed; }
[data-testid="stAppViewContainer"], [data-testid="stMain"], [data-testid="stBottom"] { background: transparent; }
.stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp li,
.stApp summary, .stApp [data-testid="stMarkdownContainer"] { font-family: 'Roboto', sans-serif; }
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"],
#MainMenu, footer, [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="stMain"] { padding: 0 !important; }
[data-testid="stMainBlockContainer"] {
  max-width: 430px !important; width: 100%; box-sizing: border-box; background: #F5F2FC; border-radius: 28px;
  box-shadow: 0 20px 60px rgba(74,47,176,0.18); margin: 24px auto !important; padding: 18px 20px 110px 20px !important;
  height: calc(100vh - 48px); overflow-y: auto; overflow-x: hidden; scrollbar-width: none; position: relative; }
[data-testid="stMainBlockContainer"]::-webkit-scrollbar { display: none; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap: 18px; }
[data-testid="stVerticalBlock"] { gap: 12px; }
@media (max-width: 600px) {
  /* stMain is a flex column: without flex-shrink 0 the frame would shrink to the screen height and the content
     (and its bottom padding) would spill past it, under the tab bar */
  [data-testid="stMainBlockContainer"] { max-width: 100% !important; border-radius: 0; box-shadow: none;
    margin: 0 !important; height: auto; min-height: 100vh; overflow: visible; flex: 0 0 auto; }
}

/* ---------- type ---------- */
.stApp p, .stApp li { font-size: 14px; }
/* Streamlit pulls markdown up with a negative margin meant for <p>; these blocks are divs, so remove it */
[data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }
.stMarkdown [data-testid="stMarkdownContainer"] > div > p:last-child, .stMarkdown p:last-child { margin-bottom: 0; }
.title { font-size: 26px; font-weight: 700; color: #1D1B3A; line-height: 1.2; margin: 0; }
.section { font-size: 18px; font-weight: 700; color: #1D1B3A; margin: 0; }
.muted, .caption { font-size: 13px; color: #6B6B85; margin: 0; }
.center { text-align: center; }
.alert-text { color: #B42318; font-weight: 500; font-size: 14px; margin: 0; }
.big-amount { font-size: 34px; font-weight: 700; color: #1D1B3A; line-height: 1.15; }
.elig-max { font-size: 28px; font-weight: 700; color: #1D1B3A; line-height: 1.2; }
.elig-comf { font-size: 15px; color: #1D1B3A; margin-top: 2px; }
.elig-no { font-size: 18px; line-height: 1.3; }

/* ---------- top bar ---------- */
.st-key-topbar { align-items: center; gap: 12px !important; flex-wrap: nowrap !important; }
.st-key-topbar [data-testid="stElementContainer"] { width: auto; }
.icon-box { width: 44px; height: 44px; border-radius: 14px; background: #FFFFFF; display: flex; align-items: center;
  justify-content: center; box-shadow: 0 4px 12px rgba(91,63,196,0.08); flex: 0 0 44px; }
.tb-greet { font-size: 13px; color: #6B6B85; line-height: 1.2; }
.tb-name { font-size: 20px; font-weight: 700; color: #1D1B3A; line-height: 1.25; }
.tb-title { font-size: 26px; font-weight: 700; color: #1D1B3A; line-height: 1.2; }
.tb-caption { font-size: 13px; color: #6B6B85; }
.st-key-topbar_avatar { align-self: center !important; display: flex; align-items: center; }
.st-key-topbar_avatar .stButton, .st-key-topbar_avatar [data-testid="stTooltipHoverTarget"] { margin: 0 !important; display: flex; }
.st-key-topbar_avatar button { width: 44px !important; height: 44px; min-height: 44px !important; padding: 0 !important;
  border-radius: 50% !important; background: #E8DFFB !important; border: none !important; box-shadow: none !important; }
.st-key-topbar_avatar button p { color: #4A2FB0 !important; font-weight: 700 !important; font-size: 14px !important; }

/* ---------- cards ---------- */
[class*="st-key-card_"] { background: #FFFFFF; border-radius: 20px; box-shadow: 0 6px 20px rgba(91,63,196,0.08);
  padding: 16px; gap: 10px !important; }
.st-key-hero { background: linear-gradient(135deg, #4A2FB0 0%, #7C5CE0 100%); border-radius: 24px; padding: 22px 20px;
  box-shadow: 0 12px 28px rgba(74,47,176,0.28); position: relative; overflow: hidden; gap: 6px !important; }
.st-key-hero::after { content: ""; position: absolute; width: 190px; height: 190px; border-radius: 50%;
  background: rgba(255,255,255,0.10); top: -80px; right: -60px; pointer-events: none; }
.st-key-hero::before { content: ""; position: absolute; width: 110px; height: 110px; border-radius: 50%;
  background: rgba(255,255,255,0.07); bottom: -50px; right: 40px; pointer-events: none; }
.hero-label { font-size: 14px; font-weight: 500; color: #FFFFFF; }
.hero-score { font-size: 52px; font-weight: 700; line-height: 1.05; color: #FFFFFF; letter-spacing: -0.5px; }
.hero-score span { font-size: 20px; font-weight: 500; letter-spacing: 0; }
.hero-tier { font-size: 19px; font-weight: 700; }
.hero-line { font-size: 14px; color: #FFFFFF; }
.st-key-hero_cta button { background: #FFFFFF !important; border: none !important; height: 50px; border-radius: 16px !important;
  box-shadow: none !important; }
.st-key-hero_cta button p { color: #5B3FC4 !important; font-weight: 700 !important; font-size: 15px !important; }

/* rows inside cards */
.row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 0;
  border-bottom: 1px solid #EFEAFA; font-size: 14px; }
.row:last-child { border-bottom: none; padding-bottom: 2px; }
.row:first-child { padding-top: 2px; }
.row .k { color: #1D1B3A; display: flex; align-items: center; gap: 12px; }
.row .v { color: #6B6B85; text-align: right; }
.num { width: 32px; height: 32px; border-radius: 10px; background: #E8DFFB; color: #4A2FB0; font-weight: 700;
  font-size: 13px; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 32px; }
.reason { display: flex; align-items: flex-start; gap: 12px; padding: 12px 0; border-bottom: 1px solid #EFEAFA; font-size: 14px; }
.reason:last-child { border-bottom: none; padding-bottom: 2px; }
.reason:first-child { padding-top: 2px; }
.reason .dir { flex: 0 0 92px; font-size: 13px; }
.reason .txt { color: #1D1B3A; }

/* ---------- buttons ---------- */
.stButton > button, .stFormSubmitButton > button { border-radius: 16px; min-height: 48px; font-weight: 500; }
.stButton > button[kind="primary"] { background: #5B3FC4; border: none; color: #FFFFFF; height: 54px; min-height: 54px;
  border-radius: 16px; box-shadow: 0 8px 20px rgba(91,63,196,0.30); }
.stButton > button[kind="primary"] p { font-size: 16px; font-weight: 700; color: #FFFFFF; }
.stButton > button[kind="primary"]:hover { background: #4A2FB0; }
.stButton > button[kind="primary"]:disabled { background: #DDD5F7; box-shadow: none; }
.stButton > button[kind="primary"]:disabled p { color: #4A2FB0; }
.stButton > button[kind="secondary"] { background: #FFFFFF; border: 1.5px solid #E3DDF5; height: 52px; border-radius: 16px; }
.stButton > button[kind="secondary"] p { color: #5B3FC4; font-weight: 700; font-size: 15px; }
.stButton > button[kind="secondary"]:hover { border-color: #5B3FC4; }
.stButton > button[kind="tertiary"] p { color: #5B3FC4; font-weight: 500; font-size: 14px; }
.st-key-delete_results button p, .st-key-confirm_delete button p { color: #B42318 !important; }

/* list rows as buttons: label left, chevron right */
[class*="st-key-row_"] button { background: transparent !important; border: none !important; box-shadow: none !important;
  justify-content: space-between !important; width: 100%; padding: 4px 0 !important; min-height: 44px !important;
  height: auto !important; }
[class*="st-key-row_"] button > div, [class*="st-key-row_"] button [data-testid="stMarkdownContainer"] {
  flex: 1 1 auto; text-align: left !important; justify-content: flex-start !important; }
[class*="st-key-row_"] button p { text-align: left !important; }
[class*="st-key-row_"] button p { color: #1D1B3A !important; font-size: 15px !important; font-weight: 500 !important; }
[class*="st-key-row_"] button::after { content: ""; flex: 0 0 20px; height: 20px; background: CHEVRON center / 20px no-repeat; }

/* rows of one card share dividers (Latest applications) */
[class*="st-key-card_"] [class*="st-key-row_"] button { border-radius: 0 !important;
  border-bottom: 1px solid #EFEAFA !important; padding: 10px 0 !important; }
[class*="st-key-card_"] [data-testid="stElementContainer"]:last-child [class*="st-key-row_"] button,
[class*="st-key-card_"] [class*="st-key-row_"]:last-child button { border-bottom: none !important; }

/* menu button in the top bar: a white 44px icon box; the label "Menu" is hidden visually but stays its accessible name */
.st-key-topbar_menu { align-self: center !important; }
.st-key-topbar_menu button { width: 44px !important; height: 44px; min-height: 44px !important; padding: 0 !important;
  border-radius: 14px !important; background: #FFFFFF !important; border: none !important;
  box-shadow: 0 4px 12px rgba(91,63,196,0.08) !important; }
.st-key-topbar_menu button::before { content: ""; width: 22px; height: 22px; display: block; }
.st-key-topbar_menu button:focus-visible, .st-key-topbar_avatar button:focus-visible, [class*="st-key-menu_"] button:focus-visible {
  outline: 2px solid #5B3FC4 !important; outline-offset: 2px; }
.st-key-topbar_menu button > div, .st-key-topbar_menu button p { position: absolute !important; width: 1px !important;
  height: 1px !important; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; margin: -1px; padding: 0; }

/* the menu dialog: a card the width of the frame (Streamlit wraps role=dialog in a wider panel: size that one) */
[data-testid="stDialog"] div:has(> [role="dialog"]) { width: min(430px, calc(100vw - 32px)) !important;
  max-width: 430px !important; background: transparent !important; box-shadow: none !important; border: none !important; }
[data-testid="stDialog"] [role="dialog"] { width: 100% !important; max-width: 100% !important;
  border-radius: 24px !important; background: #FFFFFF; font-family: 'Roboto', sans-serif;
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

/* ---------- bottom tab bar, fixed to the bottom of the frame ---------- */
.st-key-bottom_nav { position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); width: 430px; max-width: 100%;
  box-sizing: border-box; background: #FFFFFF; box-shadow: 0 -6px 20px rgba(91,63,196,0.08); border-radius: 22px 22px 28px 28px;
  padding: 8px 10px 10px 10px; z-index: 1000; flex-wrap: nowrap !important; gap: 0 !important; }
.st-key-bottom_nav [data-testid="stElementContainer"], .st-key-bottom_nav .stButton { flex: 1 1 0; min-width: 0; }
.st-key-bottom_nav button { background: transparent !important; border: none !important; box-shadow: none !important;
  flex-direction: column !important; gap: 3px !important; min-height: 52px !important; height: auto !important;
  padding: 2px 0 !important; width: 100%; }
.st-key-bottom_nav button::before { content: ""; width: 24px; height: 24px; display: block; }
.st-key-bottom_nav button p { font-size: 12px !important; color: #6B6B85 !important; font-weight: 500 !important; }
@media (max-width: 600px) {
  .st-key-bottom_nav { bottom: 0; width: 100%; border-radius: 22px 22px 0 0; }
}

/* ---------- inputs ---------- */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { font-size: 13px !important; font-weight: 500 !important;
  color: #1D1B3A; }
[data-testid="stTextInputRootElement"], [data-testid="stNumberInputContainer"], [data-testid="stNumberInputRootElement"] {
  background: #FFFFFF !important; border: 1.5px solid #E3DDF5 !important; border-radius: 16px !important;
  height: 52px !important; min-height: 52px; overflow: hidden; box-sizing: border-box; }
[data-testid="stTextInputRootElement"]:focus-within, [data-testid="stNumberInputContainer"]:focus-within,
[data-testid="stNumberInputRootElement"]:focus-within { border-color: #5B3FC4 !important; }
[data-testid="stTextInputRootElement"] input, [data-testid="stNumberInputContainer"] input,
[data-testid="stNumberInputRootElement"] input { font-size: 15px !important; padding-left: 14px !important;
  background: #FFFFFF !important; height: 100% !important; }
[data-testid="stNumberInput"] button { background: #FFFFFF !important; border: none !important; }

/* upload area */
[data-testid="stFileUploaderDropzone"] { border: 2px dashed #B6A6EE !important; border-radius: 16px !important;
  background: #FBFAFF !important; padding: 14px !important; }
.upload-head { display: flex; align-items: center; gap: 12px; }
.icon-circle { width: 48px; height: 48px; border-radius: 50%; background: #E8DFFB; display: flex; align-items: center;
  justify-content: center; flex: 0 0 48px; }
.icon-circle.lg { width: 64px; height: 64px; flex-basis: 64px; margin: 4px auto 0 auto; }

/* sign in / sign up header */
.auth-head { position: relative; overflow: hidden; margin: -18px -20px 6px -20px; padding: 34px 24px 30px 24px;
  background: linear-gradient(160deg, #4A2FB0 0%, #7C5CE0 100%); border-radius: 0 0 36px 36px; color: #FFFFFF; }
.auth-head::after { content: ""; position: absolute; width: 200px; height: 200px; border-radius: 50%;
  background: rgba(255,255,255,0.10); top: -70px; right: -60px; }
.auth-brand { display: flex; align-items: center; gap: 10px; font-size: 20px; font-weight: 700; color: #FFFFFF; }
.logo { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px;
  border-radius: 12px; background: #FFFFFF; }
.auth-title { font-size: 28px; font-weight: 700; margin-top: 26px; color: #FFFFFF; }
.auth-sub { font-size: 14px; color: #FFFFFF; margin-top: 4px; }

/* sent */
.done-circle { width: 96px; height: 96px; border-radius: 50%; margin: 8px auto 0 auto;
  background: linear-gradient(135deg, #4A2FB0 0%, #7C5CE0 100%); display: flex; align-items: center; justify-content: center;
  box-shadow: 0 12px 28px rgba(74,47,176,0.30); }

/* profile */
.avatar-lg { width: 76px; height: 76px; border-radius: 50%; background: #E8DFFB; color: #4A2FB0; font-size: 26px;
  font-weight: 700; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto; }
[data-testid="stCheckbox"] label p { font-size: 14px !important; }

/* History: one card per application */
[data-testid="stExpander"] details { background: #FFFFFF; border-radius: 20px !important; border: none !important;
  box-shadow: 0 6px 20px rgba(91,63,196,0.08); }
[data-testid="stExpander"] summary { padding: 16px !important; }
/* chevron on the right of the line (the icon and the label share an inner wrapper) */
[data-testid="stExpander"] summary, [data-testid="stExpander"] summary > span, [data-testid="stExpander"] summary > div {
  display: flex; flex-direction: row-reverse; justify-content: space-between; align-items: center; width: 100%; }
[data-testid="stExpander"] summary p { font-size: 15px; font-weight: 500; }

/* slider: the big amount above is its value; hide the duplicate value bubble and the min/max ticks */
[data-testid="stSliderThumbValue"], [data-testid="stSliderTickBarMin"], [data-testid="stSliderTickBarMax"] { display: none; }

/* charts */
[data-testid="stVegaLiteChart"] { background: transparent; }
</style>
""".replace("CHEVRON", icon_uri("chevron", MUTED))


def css() -> str:
    return CSS.replace("</style>", _icon_css() + "\n</style>")


def inject() -> None:
    """Inject the theme with st.markdown: style-only st.html goes to a separate event container that can be dropped on
    a rerun, which left some screens unstyled. The empty wrapper is hidden (a hidden <style> still applies)."""
    st.markdown(css(), unsafe_allow_html=True)


def active_tab_css(tab: str) -> str:
    return (f"<style>.st-key-nav_{tab} button p {{ color: {PURPLE} !important; font-weight: 700 !important; }}"
            f".st-key-nav_{tab} button::before {{ background: {icon_uri(NAV_ICONS[tab], PURPLE, 2.2)} center / 24px no-repeat; }}"
            "</style>")


def favicon():
    """A simple purple rounded-square favicon with the white logo line (drawn, so no image file is needed)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 63, 63), radius=16, fill=PURPLE)
    d.line([(14, 44), (26, 32), (35, 41), (50, 22)], fill="white", width=6, joint="curve")
    return img
