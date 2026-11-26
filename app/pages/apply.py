"""Apply to a lender with the vendor's latest SAVED score check: the check (date, score, risk level, estimated limit,
comfortable amount), then the amount, the repay-within days, the lender and consent. There is no upload: the
application is bound to that check, and the lender receives a summary built from it. The rules (the check is the
vendor's own, at most service.APPLY_CHECK_MAX_AGE_DAYS old, the amount within its limit, no duplicate pending
application) are enforced in service.submit_application, not only here.

Without a saved check, or with only an expired one, the page says "Check your score again to apply" and offers
Check score. Laptop: the check and the lender on the right, the request on the left. Phone: check, lender, request."""
from html import escape

import streamlit as st

from app import components as ui, service
from app.pages.history import check_ref

MSG_ABOVE = "You can apply for up to {}. Lower the amount and try again."
MSG_NOT_ELIGIBLE = "Not eligible right now."
MSG_NO_INCOME = "Not enough income data."
CONSENT = "Share my score summary with the lender. My statement is never shared."
FINAL_DECISION = "The lender makes the final decision."
WHY_NO_CHECK = {
    "none": "Applications use a saved score check from the last {days} days. You have none yet.",
    "expired": "Applications use a saved score check from the last {days} days. Your latest check is older.",
    "not_saved": "Applications use a saved score check. Turn on \"Save my score results\" in Profile, then check your "
                 "score.",
}


def _check_again(why: str) -> None:
    with st.container(key="card_check_again"):
        ui.section(service.MSG_CHECK_AGAIN)
        ui.muted(WHY_NO_CHECK[why].format(days=service.APPLY_CHECK_MAX_AGE_DAYS))
        st.button("Check score", key="apply_check_score", type="primary", on_click=ui.go, args=("score",),
                  width="stretch")


def _check_card(check: dict) -> None:
    """The check this application will use."""
    el = check["eligibility"]
    if el["status"] == "eligible":
        limit = (ui.row("Estimated limit", f"Up to {ui.money(el['max_amount'])}")
                 + ui.row("Comfortable amount", f"Up to {ui.money(el['comfortable_amount'])}"))
    elif el["status"] == "not_eligible":
        limit = ui.row("Estimated limit", ui.pill(MSG_NOT_ELIGIBLE.rstrip("."), "bad"))
    else:
        limit = ui.row("Estimated limit", escape(MSG_NO_INCOME.rstrip(".")))
    with st.container(key="card_limit"):
        ui.html(ui.cap("Your score check") + ui.row("Date", escape(ui.date_time(check["created_at"])))
                + ui.row("Reference", escape(check_ref(check))) + ui.row("Score", f"{int(check['score'])} / 850")
                + ui.row("Risk level", ui.pill(check["tier"])) + limit)


def render(conn, user) -> None:
    ui.page_header(user, "Apply to a lender", "Uses your latest score check")
    check, why = service.check_for_apply(conn, user)
    if check is None:
        _check_again(why)
        return
    lenders = service.list_lenders(conn)
    if not lenders:
        with st.container(key="card_no_lenders"):
            ui.muted("No lenders available yet.")
        return
    el = check["eligibility"]
    eligible = el["status"] == "eligible"
    start_amount = int(el["comfortable_amount"] or 0) if eligible else 0
    start_amount = start_amount or int(check["request_amount"])

    # drawn first (phone order: check, lender, request); from 1100px this column sits on the RIGHT
    side, main = ui.two_columns("apply", "rev")
    with side:
        _check_card(check)
        with st.container(key="card_lenders"):
            names = {l["id"]: l["org_name"] for l in lenders}
            lender_id = st.radio("Lender", list(names), format_func=names.get, key="apply_lender")
    with main, st.container(key="card_request"):
        ui.html(ui.cap("Your request"))
        amount = st.number_input("Amount (KES)", min_value=1, value=start_amount, step=500, key="apply_amount_in")
        term = st.number_input("Repay within (days)", min_value=1, value=int(check["request_term"]), step=1,
                               key="apply_term_in")
        consent = st.checkbox(CONSENT, key="apply_consent")
        if not eligible:
            ui.alert(MSG_NOT_ELIGIBLE if el["status"] == "not_eligible" else MSG_NO_INCOME)
            if el["status"] == "not_eligible":
                st.button("See why", key="apply_see_why", type="tertiary", on_click=ui.go, args=("reasons",))
        if st.button("Send application", type="primary", key="send_application", width="stretch",
                     disabled=not consent or not eligible):
            try:
                out = service.submit_application(conn, user, lender_id, check["check_id"], amount, term, consent)
            except service.UserError as e:
                ui.alert(str(e))
            else:
                if out["outcome"] == service.OUTCOME_SENT:
                    st.session_state.pop("apply_consent", None)
                    ui.go("sent", sent=out["application"])
                    st.rerun()
                ui.alert({service.OUTCOME_ABOVE_LIMIT: MSG_ABOVE.format(ui.money(out["max_amount"] or 0)),
                          service.OUTCOME_NOT_ELIGIBLE: MSG_NOT_ELIGIBLE,
                          service.OUTCOME_NO_INCOME: MSG_NO_INCOME}[out["outcome"]])
        ui.muted(FINAL_DECISION)
