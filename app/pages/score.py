"""Check score: upload a statement and give the loan request."""
import streamlit as st

from app import components as ui, service, theme


def render(conn, user) -> None:
    ui.top_bar(user, "Check score", "Excel or CSV from M-Pesa")
    try:
        med_amount, med_term = service.median_request()
    except service.UserError as e:
        ui.alert(str(e))
        return
    n = st.session_state.setdefault("upload_n", 0)          # a new key clears the uploader after scoring
    with st.container(key="card_upload"):
        ui.html(f'<div class="upload-head"><span class="icon-circle">{ui.icon("upload", theme.PURPLE, 24)}</span>'
                '<div><div class="section" style="font-size:16px">Upload statement</div>'
                '<div class="caption">PDF only if its text can be selected</div></div></div>')
        file = st.file_uploader("Statement file", type=[e.lstrip(".") for e in service.ALLOWED_EXTENSIONS],
                                key=f"upload_{n}")
    with st.container(key="card_request"):
        ui.section("Loan request")
        amount = st.number_input("Amount (KES)", min_value=1, value=int(med_amount), step=500, key="req_amount")
        term = st.number_input("Repay within (days)", min_value=1, value=int(med_term), step=1, key="req_term")
    if st.button("Get my score", type="primary", key="get_score", width="stretch", disabled=file is None):
        try:
            with st.spinner("Reading your statement"):
                result = service.run_score_check(conn, user, file, amount, term)
        except service.UserError as e:
            ui.alert(str(e))
        else:
            st.session_state["upload_n"] = n + 1
            st.session_state.pop("loan_amount", None)
            ui.go("result", result=result)
            st.rerun()
