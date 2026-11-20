"""Apply: choose a lender, see the summary that will be shared, consent, send."""
import streamlit as st

from app import components as ui, service
from app.pages import current_result


def render(conn, user) -> None:
    ui.top_bar(user, "Apply", "Choose a lender")
    result = current_result(conn, user)
    if result is None:
        ui.hero(cta=True)
        return
    lenders = service.list_lenders(conn)
    if not lenders:
        with st.container(key="card_no_lenders"):
            ui.muted("No lenders available yet.")
        return
    amount = float(st.session_state.get("apply_amount", result["request_amount"]))
    term = float(result["request_term"])

    with st.container(key="card_lenders"):
        names = {l["id"]: l["org_name"] for l in lenders}
        lender_id = st.radio("Lender", list(names), format_func=names.get, key="apply_lender")
    with st.container(key="card_summary"):
        ui.section("Summary")
        ui.html(ui.row("Score", f"{result['score']} / 850")
                + ui.row("Risk level", ui.status_text(result["tier"]))
                + ui.row("Request", f"{ui.money(amount)}, {term:.0f} days"))
    consent = st.checkbox("Share this summary with the lender", key="apply_consent")
    if st.button("Send application", type="primary", key="send_application", width="stretch", disabled=not consent):
        try:
            sent = service.create_application(conn, user, lender_id, result, amount=amount, term=term, consent=consent)
        except service.UserError as e:
            ui.alert(str(e))
        else:
            st.session_state.pop("apply_consent", None)
            ui.go("sent", sent=sent)
            st.rerun()
