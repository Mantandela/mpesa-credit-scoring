"""Check score: upload a statement and give the loan request."""
import streamlit as st

from app import components as ui, service


def render(conn, user) -> None:
    ui.title("Check your score", "Excel or CSV statement from M-Pesa")
    try:
        med_amount, med_term = service.median_request()
    except service.UserError as e:
        ui.alert(str(e))
        return
    n = st.session_state.setdefault("upload_n", 0)          # a new key clears the uploader after scoring
    with st.container(key="card_upload"):
        file = st.file_uploader("Statement file", type=[e.lstrip(".") for e in service.ALLOWED_EXTENSIONS],
                                key=f"upload_{n}", help="xlsx, xls, csv, or a PDF with selectable text. Up to 10 MB.")
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
