"""Reasons, plus a what-if "Test an amount" tool. The slider recomputes ONLY the affordability band from monthly
income; it never re-scores and never changes the estimated limit. Laptop: two columns; phone: stacked."""
from html import escape

import streamlit as st

from app import components as ui, service
from app.pages import comfortable_amount, current_result

SLIDER_MIN, SLIDER_MAX, SLIDER_STEP = 1000, 150000, 500
START_NOTE = "Starts at your comfortable amount. Testing an amount never changes your score."


def render(conn, user) -> None:
    result = current_result(conn, user)
    ui.page_header(user, "Reasons", "What shaped your score")
    if result is None:
        ui.no_score_card()
        return

    weighed, test = ui.two_columns("reasons", "even")
    with weighed, st.container(key="card_reasons"):
        ui.section("What the model weighed")
        ui.html("".join(ui.reason_row(r["direction"], r["phrase"]) for r in result["reasons"]))
        if result["data_notes"]:
            ui.html(f'<div class="muted">No data in this statement on: {escape(", ".join(result["data_notes"]))}</div>')

    # start at the estimated comfortable amount when known, else at the request the score used (the median request)
    requested = float(comfortable_amount(result) or result["request_amount"])
    top = max(SLIDER_MAX, int(requested))
    start = int(min(max(requested, SLIDER_MIN), top))
    amount = st.session_state.get("loan_amount", start)
    check = service.affordability(amount, result["monthly_income"])

    with test:
        with st.container(key="card_loan"):
            ui.section("Test an amount")
            ui.html(f'<div class="big-amount" aria-live="polite">{ui.money(amount)}</div>')
            st.slider("Loan amount (KES)", min_value=SLIDER_MIN, max_value=top, value=start, step=SLIDER_STEP,
                      key="loan_amount", format="%d", label_visibility="collapsed")  # the amount above is its label
            share = check["share_of_monthly_income"]
            income = f"{ui.pct(share, 0)} of monthly income" if share is not None else "Monthly income not found"
            ui.html(f'<div class="band-line"><span>{escape(income)}</span>'
                    f'<span>{ui.status_text(check["band"].capitalize())}</span></div>')
            if check["outside_typical_range"]:
                ui.muted("Outside typical range")
            ui.muted(START_NOTE)
        st.button("Apply to a lender", type="primary", key="reasons_apply", on_click=ui.go, args=("apply",),
                  width="stretch")
