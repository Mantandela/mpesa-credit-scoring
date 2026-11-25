"""Apply to a lender: lender, amount and days, the statement (uploaded again), consent; the statement is scored fresh
and the estimated eligibility of that result decides whether the application is sent.
Laptop: "Your request" on the left, the estimated limit and the lender on the right. Phone: limit, lender, request."""
import streamlit as st

from app import components as ui, service
from app.pages import comfortable_amount, current_result

MSG_ABOVE = "You can apply for up to {}. Lower the amount and try again."
MSG_NOT_ELIGIBLE = "Not eligible right now."
MSG_NO_INCOME = "Not enough income data."
CONSENT = "Share my score summary with the lender. My statement is never shared."
FINAL_DECISION = "The lender makes the final decision."


def _limit_card(result) -> None:
    el = result["eligibility"]
    with st.container(key="card_limit"):
        ui.html('<div class="muted">Your estimated limit</div>')
        if el["status"] == "eligible":
            ui.html(f'<div class="limit-big">Up to {ui.money(el["max_amount"])}</div>'
                    f'<div class="muted">Comfortable up to {ui.money(el["comfortable_amount"])}</div>')
        elif el["status"] == "not_eligible":
            ui.html(f'<div class="limit-big">{ui.colored_text("Not eligible right now", "declined")}</div>')
        else:
            ui.html('<div class="limit-big lc-unknown">Not enough income data</div>')


def render(conn, user) -> None:
    ui.page_header(user, "Apply to a lender", "Your statement is checked again")
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

    result = current_result(conn, user)               # this session's result, else the latest saved check
    start_amount = comfortable_amount(result) or int(med_amount)

    # drawn first (phone order: limit, lender, request); from 1024px this column sits on the RIGHT
    side, main = ui.two_columns("apply", "rev")
    with side:
        if result is not None:
            _limit_card(result)
        with st.container(key="card_lenders"):
            names = {l["id"]: l["org_name"] for l in lenders}
            lender_id = st.radio("Lender", list(names), format_func=names.get, key="apply_lender")
    with main, st.container(key="card_request"):
        ui.section("Your request")
        amount = st.number_input("Amount (KES)", min_value=1, value=int(start_amount), step=500, key="apply_amount_in")
        term = st.number_input("Repay within (days)", min_value=1, value=int(med_term), step=1, key="apply_term_in")
        n = st.session_state.setdefault("apply_upload_n", 0)     # a new key clears the uploader after every attempt
        file = st.file_uploader("Your statement", type=[e.lstrip(".") for e in service.ALLOWED_EXTENSIONS],
                                key=f"apply_upload_{n}")
        consent = st.checkbox(CONSENT, key="apply_consent")

        if st.button("Send application", type="primary", key="send_application", width="stretch",
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
        ui.muted(FINAL_DECISION)
