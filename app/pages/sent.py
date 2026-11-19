"""Application sent."""
from html import escape

import streamlit as st

from app import components as ui


def render(conn, user) -> None:
    sent = st.session_state.get("sent")
    if not sent:
        ui.go("history")
        st.rerun()
    with st.container(key="card_sent"):
        ui.html(f'<div class="center">{ui.icon("check", "#067647", 64, "Done")}'
                f'<div class="title">Application sent</div><div class="muted">{escape(sent["lender"])}</div></div>')
        ui.html(ui.row("Reference", escape(sent["ref"])) + ui.row("Status", ui.status_text(sent["status"].capitalize())))
    st.button("View my applications", type="primary", key="sent_history", on_click=ui.go, args=("history",), width="stretch")
    st.button("Back to home", key="sent_home", on_click=ui.go, args=("home",), width="stretch")
