"""Apply for a loan: lender, amount and days, the statement (uploaded again), consent; the statement is scored fresh and
the estimated eligibility of that result decides whether the application is sent."""
import streamlit as st

from app import components as ui, service, theme

MSG_ABOVE = "You can apply for up to {}. Lower the amount and try again."
MSG_NOT_ELIGIBLE = "Not eligible right now."
MSG_NO_INCOME = "Not enough income data."


def render(conn, user) -> None:
    ui.top_bar(user, "Apply", "Checked against your statement")
    lenders = service.list_lenders(conn)
    if not lenders:
        with st.container(key="card_no_lenders"):
            ui.muted("No lenders available yet.")
        return
    try:
        med_amount, med_term = service.median_request()
    except service.UserError as e:
        ui.alert(str(e))
        return

    with st.container(key="card_lenders"):
        names = {l["id"]: l["org_name"] for l in lenders}
        lender_id = st.radio("Lender", list(names), format_func=names.get, key="apply_lender")
    with st.container(key="card_request"):
        ui.section("Loan request")
        amount = st.number_input("Amount (KES)", min_value=1, value=int(med_amount), step=500, key="apply_amount_in")
        term = st.number_input("Repay within (days)", min_value=1, value=int(med_term), step=1, key="apply_term_in")
    n = st.session_state.setdefault("apply_upload_n", 0)     # a new key clears the uploader after every attempt
    with st.container(key="card_apply_upload"):
        ui.html(f'<div class="upload-head"><span class="icon-circle">{ui.icon("upload", theme.PURPLE, 24)}</span>'
                '<div><div class="section" style="font-size:16px">Your statement</div>'
                '<div class="caption">Checked now, then discarded</div></div></div>')
        file = st.file_uploader("Statement file", type=[e.lstrip(".") for e in service.ALLOWED_EXTENSIONS],
                                key=f"apply_upload_{n}")
    consent = st.checkbox("Share this summary with the lender", key="apply_consent")

    if st.button("Check eligibility and send", type="primary", key="send_application", width="stretch",
                 disabled=file is None or not consent):
        msg = None
        try:
            with st.spinner("Checking your statement"):
                out = service.submit_application(conn, user, lender_id, file, amount, term, consent)
        except service.UserError as e:
            msg = ("error", str(e))
        else:
            st.session_state["result"] = out["result"]        # the fresh result (no statement content), for "See why"
            st.session_state.pop("loan_amount", None)
            if out["outcome"] == service.OUTCOME_SENT:
                st.session_state["apply_upload_n"] = n + 1
                st.session_state.pop("apply_consent", None)
                ui.go("sent", sent=out["application"])
                st.rerun()
            msg = {service.OUTCOME_ABOVE_LIMIT: ("above", MSG_ABOVE.format(ui.money(out["max_amount"] or 0))),
                   service.OUTCOME_NOT_ELIGIBLE: ("not_eligible", MSG_NOT_ELIGIBLE),
                   service.OUTCOME_NO_INCOME: ("no_income", MSG_NO_INCOME)}[out["outcome"]]
        st.session_state["apply_upload_n"] = n + 1             # never keep the statement after a scoring attempt
        st.session_state["apply_msg"] = msg
        st.rerun()

    if "apply_msg" in st.session_state:
        kind, text = st.session_state.pop("apply_msg")
        ui.alert(text)
        if kind == "not_eligible":
            st.button("See why", key="apply_see_why", type="tertiary", on_click=ui.go, args=("reasons",))
