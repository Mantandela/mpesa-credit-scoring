"""Reasons, plus a what-if "Test an amount" tool. The slider recomputes ONLY the affordability band from monthly
income; it never re-scores and never changes the estimated limit."""
from html import escape

import streamlit as st

from app import components as ui, service
from app.pages import current_result

SLIDER_MIN, SLIDER_MAX, SLIDER_STEP = 1000, 150000, 500


def render(conn, user) -> None:
    result = current_result(conn, user)
    ui.top_bar(user, "Reasons", "What affects your score")
    if result is None:
        ui.hero(cta=True)
        return

    with st.container(key="card_reasons"):
        ui.section("What affects your score")
        ui.html("".join(ui.reason_row(r["direction"], r["phrase"]) for r in result["reasons"]))
        if result["data_notes"]:
            ui.html(f'<div class="muted">No data in this statement on: {escape(", ".join(result["data_notes"]))}</div>')

    requested = float(result["request_amount"])
    top = max(SLIDER_MAX, int(requested))
    start = int(min(max(requested, SLIDER_MIN), top))
    amount = st.session_state.get("loan_amount", start)
    check = service.affordability(amount, result["monthly_income"])
    el = result["eligibility"]

    with st.container(key="card_loan"):
        ui.section("Test an amount")
        limit = (f"Up to {ui.money(el['max_amount'])}" if el["status"] == "eligible"
                 else "Not eligible right now" if el["status"] == "not_eligible" else "Not enough income data")
        ui.html(f'<div class="row"><span class="k"><span class="big-amount">{ui.money(amount)}</span></span>'
                f'<span class="v">Your limit<br><b style="color:#1D1B3A">{escape(limit)}</b></span></div>')
        st.slider("Loan amount (KES)", min_value=SLIDER_MIN, max_value=top, value=start, step=SLIDER_STEP,
                  key="loan_amount", format="%d", label_visibility="collapsed")   # the amount above is its visible label
        share = check["share_of_monthly_income"]
        income = f"{ui.pct(share)} of monthly income" if share is not None else "Monthly income not found"
        ui.html(ui.row(income, ui.status_text(check["band"].capitalize())))
        if check["outside_typical_range"]:
            ui.muted("Outside typical range")

    st.button("Apply for a loan", type="primary", key="reasons_apply", on_click=ui.go, args=("apply",), width="stretch")
