"""Finova-style theme: Roboto, lavender page, white cards, purple primary, phone-width column.

The four base colours are in .streamlit/config.toml; everything else is the CSS below, injected once per run.
Containers are styled through their keys: a container whose key starts with "card_" is a white card, "qa_" a quick
action tile, "row_" a list row with a chevron; "bottom_nav" is the fixed tab bar.
"""
import streamlit as st

PURPLE = "#5B3FC4"
INK = "#1D1B3A"
MUTED = "#6B6B85"
PAGE = "#F5F2FC"
TILE = "#EEE9FB"            # tint for icon tiles only, never for status

_CHEVRON = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' "
            "stroke='%236B6B85' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>"
            "<path d='M9 6l6 6-6 6'/></svg>\")")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
html, body, .stApp { background: #F5F2FC; color: #1D1B3A; font-family: 'Roboto', sans-serif; }
.stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp li,
.stApp summary, .stApp [data-testid="stMarkdownContainer"] { font-family: 'Roboto', sans-serif; }
header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer {
  display: none !important; }
[data-testid="stMainBlockContainer"], .block-container {
  max-width: 430px !important; padding: 16px 16px 120px 16px !important; margin: 0 auto; }
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }

/* text */
.title { font-size: 22px; font-weight: 700; color: #1D1B3A; margin: 4px 0 2px 0; }
.subtitle { font-size: 14px; color: #6B6B85; margin: 0 0 12px 0; }
.section { font-size: 16px; font-weight: 700; color: #1D1B3A; margin: 2px 0 6px 0; }
.muted { font-size: 14px; color: #6B6B85; }
.big-amount { font-size: 32px; font-weight: 700; color: #1D1B3A; line-height: 1.2; }
.alert-text { color: #B42318; font-weight: 500; font-size: 14px; margin: 4px 0; }

/* cards */
[class*="st-key-card_"] { background: #FFFFFF; border-radius: 20px; box-shadow: 0 6px 20px rgba(91,63,196,0.08);
  padding: 16px; margin-bottom: 4px; }
.hero { background: linear-gradient(135deg, #4A2FB0 0%, #7C5CE0 100%); color: #FFFFFF; border-radius: 20px;
  padding: 22px 20px; box-shadow: 0 6px 20px rgba(91,63,196,0.18); margin-bottom: 8px; }
.hero .label { font-size: 14px; color: #FFFFFF; font-weight: 500; }
.hero .score { font-size: 44px; font-weight: 700; line-height: 1.1; color: #FFFFFF; }
.hero .score span { font-size: 20px; font-weight: 500; }
.hero .tier { font-size: 19px; font-weight: 700; margin-top: 6px; }
.hero .line { font-size: 15px; color: #FFFFFF; margin-top: 4px; }
.auth-head { background: linear-gradient(135deg, #4A2FB0 0%, #7C5CE0 100%); color: #FFFFFF; border-radius: 20px;
  padding: 28px 20px 24px 20px; margin-bottom: 12px; }
.auth-head .welcome { font-size: 26px; font-weight: 700; margin-top: 14px; color: #FFFFFF; }
.auth-head .sub { font-size: 15px; color: #FFFFFF; }
.logo { display: inline-flex; align-items: center; justify-content: center; width: 44px; height: 44px;
  border-radius: 14px; background: #FFFFFF; }

/* rows inside cards */
.row { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 11px 0;
  border-bottom: 1px solid #EEEAF8; font-size: 15px; }
.row:last-child { border-bottom: none; }
.row .k { color: #1D1B3A; }
.row .v { color: #6B6B85; text-align: right; }
.avatar { width: 64px; height: 64px; border-radius: 50%; background: #5B3FC4; color: #FFFFFF; font-size: 24px;
  font-weight: 700; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto; }
.center { text-align: center; }

/* buttons */
.stButton > button { border-radius: 14px; min-height: 48px; font-weight: 500; }
.stButton > button[kind="primary"] { background: #5B3FC4; border-color: #5B3FC4; color: #FFFFFF; }
.stButton > button[kind="tertiary"] p { color: #5B3FC4; font-weight: 500; }

/* list rows as buttons: label on the left, chevron on the right */
[class*="st-key-row_"] button { background: transparent !important; border: none !important; box-shadow: none !important;
  justify-content: space-between !important; width: 100%; padding: 6px 0 !important; min-height: 48px; }
[class*="st-key-row_"] button [data-testid="stMarkdownContainer"] { text-align: left; }
[class*="st-key-row_"] button p { color: #1D1B3A; font-size: 15px; }
[class*="st-key-row_"] button::after { content: ""; flex: 0 0 20px; height: 20px; background: CHEVRON no-repeat center; }

/* quick-action tiles (tinted icon tiles; tints are never used for status) */
.st-key-quick_actions [data-testid="stHorizontalBlock"], .st-key-bottom_nav [data-testid="stHorizontalBlock"] {
  flex-wrap: nowrap !important; gap: 4px !important; }
.st-key-quick_actions [data-testid="stColumn"], .st-key-bottom_nav [data-testid="stColumn"] {
  min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
[class*="st-key-qa_"] button { background: transparent !important; border: none !important; box-shadow: none !important;
  flex-direction: column !important; gap: 6px !important; min-height: 88px; padding: 4px 0 !important; width: 100%; }
[class*="st-key-qa_"] button [data-testid="stIconMaterial"] { background: #EEE9FB; color: #5B3FC4; border-radius: 16px;
  padding: 12px; font-size: 26px; }
[class*="st-key-qa_"] button p { font-size: 12px; font-weight: 500; color: #1D1B3A; }

/* bottom tab bar, fixed to the bottom of the column */
.st-key-bottom_nav { position: fixed; bottom: 0; left: 50%; transform: translateX(-50%); width: 100%;
  max-width: 430px; background: #FFFFFF; box-shadow: 0 -4px 16px rgba(91,63,196,0.10); border-radius: 20px 20px 0 0;
  padding: 4px 8px 8px 8px; z-index: 1000; }
.st-key-bottom_nav button { background: transparent !important; border: none !important; box-shadow: none !important;
  flex-direction: column !important; gap: 0 !important; min-height: 56px; padding: 4px 0 !important; width: 100%; }
.st-key-bottom_nav button p { font-size: 12px; color: #6B6B85; }
.st-key-bottom_nav button [data-testid="stIconMaterial"] { font-size: 24px; color: #6B6B85; }

/* destructive text action */
.st-key-delete_results button p, .st-key-confirm_delete button p { color: #B42318 !important; font-weight: 700; }

/* expander rows on History */
[data-testid="stExpander"] details { background: #FFFFFF; border-radius: 20px; border: none;
  box-shadow: 0 6px 20px rgba(91,63,196,0.08); }
[data-testid="stExpander"] summary p { font-size: 15px; }
</style>
""".replace("CHEVRON", _CHEVRON)


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def active_tab_css(tab: str) -> str:
    return (f"<style>.st-key-nav_{tab} button p, .st-key-nav_{tab} button [data-testid=\"stIconMaterial\"] "
            f"{{ color: {PURPLE} !important; font-weight: 700 !important; }}</style>")
