"""Reasons and loan check. The slider recomputes ONLY the affordability band from monthly income; it never re-scores."""
from html import escape

import streamlit as st

from app import components as ui, service
from app.pages import current_result

SLIDER_MIN, SLIDER_MAX, SLIDER_STEP = 1000, 150000, 500


def render(conn, user) -> None:
    result = current_result(conn, user)
    ui.top_bar(user, "Loan check", "Score stays the same")
    if result is None:
        ui.hero(cta=True)
        return

    requested = float(result["request_amount"])
    top = max(SLIDER_MAX, int(requested))                   # a typed amount above 150,000 stays reachable
    start = int(min(max(requested, SLIDER_MIN), top))
    amount = st.session_state.get("loan_amount", start)
    check = service.affordability(amount, result["monthly_income"])

    with st.container(key="card_loan"):
        ui.html(f'<div class="caption">Loan amount</div><div class="big-amount">{ui.money(amount)}</div>')
        st.slider("Loan amount (KES)", min_value=SLIDER_MIN, max_value=top, value=start, step=SLIDER_STEP,
                  key="loan_amount", format="%d", label_visibility="collapsed")   # the amount above is its visible label
        share = check["share_of_monthly_income"]
        income = f"{ui.pct(share)} of monthly income" if share is not None else "Monthly income not found"
        ui.html(ui.row(income, ui.status_text(check["band"].capitalize())))
        if check["outside_typical_range"]:
            ui.muted("Outside typical range")

    with st.container(key="card_reasons"):
        ui.section("What affects your score")
        ui.html("".join(ui.reason_row(r["direction"], r["phrase"]) for r in result["reasons"]))
        if result["data_notes"]:
            ui.html(f'<div class="muted">No data in this statement on: {escape(", ".join(result["data_notes"]))}</div>')

    st.button("Apply to a lender", type="primary", key="to_apply", on_click=ui.go, args=("apply",),
              kwargs={"apply_amount": amount}, width="stretch")
