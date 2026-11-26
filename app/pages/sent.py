"""Application sent: the lender, the reference, the status and the score check it was sent with."""
from html import escape

import streamlit as st

from app import components as ui
from app.pages.history import check_ref

SHARED = "The lender sees the summary of this score check only. Your statement is never shared."


def render(conn, user) -> None:
    sent = st.session_state.get("sent")
    if not sent:
        ui.go("history")
        st.rerun()
    ui.page_header(user, "Application sent", sent["lender"])
    with st.container(key="card_sent"):
        ui.html(f'<div class="done-circle">{ui.icon("check", "#FFFFFF", 42, "Done", stroke=2.6)}</div>')
        check = (ui.row("Score check", escape(check_ref(sent))) if sent.get("check_id") is not None else "")
        ui.html(ui.row("Lender", escape(sent["lender"])) + ui.row("Reference", escape(sent["ref"]))
                + check + ui.row("Status", ui.pill(sent["status"].capitalize())))
        ui.muted(SHARED)
        st.button("View my applications", type="primary", key="sent_history", on_click=ui.go, args=("history",),
                  width="stretch")
        st.button("Back to home", key="sent_home", on_click=ui.go, args=("home",), width="stretch")
