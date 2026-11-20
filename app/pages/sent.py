"""Application sent."""
from html import escape

import streamlit as st

from app import components as ui


def render(conn, user) -> None:
    sent = st.session_state.get("sent")
    if not sent:
        ui.go("history")
        st.rerun()
    ui.top_bar(user)
    ui.html(f'<div class="done-circle">{ui.icon("check", "#FFFFFF", 46, "Done", stroke=2.6)}</div>'
            f'<div class="center" style="margin-top:14px"><div class="title">Application sent</div>'
            f'<div class="caption" style="margin-top:4px">{escape(sent["lender"])}</div></div>')
    with st.container(key="card_sent"):
        ui.html(ui.row("Lender", escape(sent["lender"])) + ui.row("Reference", escape(sent["ref"]))
                + ui.row("Status", ui.status_text(sent["status"].capitalize())))
    st.button("View my applications", type="primary", key="sent_history", on_click=ui.go, args=("history",), width="stretch")
    st.button("Back to home", key="sent_home", on_click=ui.go, args=("home",), width="stretch")
