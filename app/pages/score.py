"""Check score: upload a statement and get the score with the estimated eligibility. No loan request here."""
import streamlit as st

from app import components as ui, service, theme


def render(conn, user) -> None:
    ui.top_bar(user, "Check score", "Excel or CSV from M-Pesa")
    n = st.session_state.setdefault("upload_n", 0)          # a new key clears the uploader after scoring
    with st.container(key="card_upload"):
        ui.html(f'<div class="upload-head"><span class="icon-circle">{ui.icon("upload", theme.PURPLE, 24)}</span>'
                '<div><div class="section" style="font-size:16px">Upload statement</div>'
                '<div class="caption">PDF only if its text can be selected</div></div></div>')
        file = st.file_uploader("Statement file", type=[e.lstrip(".") for e in service.ALLOWED_EXTENSIONS],
                                key=f"upload_{n}")
    if st.button("Get my score", type="primary", key="get_score", width="stretch", disabled=file is None):
        try:
            with st.spinner("Reading your statement"):
                result = service.run_score_check(conn, user, file)
        except service.UserError as e:
            st.session_state["upload_n"] = n + 1             # never keep the statement after a scoring attempt
            st.session_state["score_error"] = str(e)
            st.rerun()
        else:
            st.session_state["upload_n"] = n + 1
            st.session_state.pop("loan_amount", None)
            ui.go("result", result=result)
            st.rerun()
    if "score_error" in st.session_state:
        ui.alert(st.session_state.pop("score_error"))
