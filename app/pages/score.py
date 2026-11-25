"""Check score: upload a statement and get the score with the estimated eligibility. No loan request here.
Laptop: the upload card and "How to export" side by side; phone: stacked."""
from html import escape

import streamlit as st

from app import components as ui, service, theme

FORMATS = "CSV, XLSX or XLS · Max {} MB"
STEPS = ("Open the M-Pesa Business Portal, then Statements", "Select 90 to 180 days", "Download as CSV or Excel")


def render(conn, user) -> None:
    ui.page_header(user, "Check score", "Excel or CSV from M-Pesa")
    n = st.session_state.setdefault("upload_n", 0)          # a new key clears the uploader after scoring
    upload, how = ui.two_columns("score", "even")
    with upload, st.container(key="card_upload"):
        ui.section("Upload statement")
        ui.muted(FORMATS.format(service.MAX_UPLOAD_BYTES // (1024 * 1024)))
        file = st.file_uploader("Statement file", type=[e.lstrip(".") for e in service.ALLOWED_EXTENSIONS],
                                key=f"upload_{n}", label_visibility="collapsed")
        if st.button("Get my score", type="primary", key="get_score", width="stretch", disabled=file is None):
            try:
                with st.spinner("Reading your statement"):
                    result = service.run_score_check(conn, user, file)
            except service.UserError as e:
                st.session_state["upload_n"] = n + 1         # never keep the statement after a scoring attempt
                st.session_state["score_error"] = str(e)
                st.rerun()
            else:
                st.session_state["upload_n"] = n + 1
                st.session_state.pop("loan_amount", None)
                ui.go("result", result=result)
                st.rerun()
        if "score_error" in st.session_state:
            ui.alert(st.session_state.pop("score_error"))
    with how, st.container(key="card_export"):
        ui.section("How to export")
        ui.html('<ol class="steps">' + "".join(f'<li><span class="num">{i}</span><span>{escape(s)}</span></li>'
                                               for i, s in enumerate(STEPS, start=1)) + "</ol>")
        ui.html(f'<div class="lock-line">{ui.icon("lock", theme.MUTED, 16)}<span>{escape(ui.AUTH_FOOTER)}</span></div>')
