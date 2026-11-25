"""Result: the score card (with the score chart) and the estimated limit on the left, Business health and "Apply to a
lender" on the right (phone: stacked). The score itself comes from Check score; nothing is re-scored here."""
import streamlit as st

from app import components as ui
from app.pages import chart_points, checks_and_result

FINAL_DECISION = "The lender makes the final decision."


def render(conn, user) -> None:
    checks, result = checks_and_result(conn, user)        # one checks query: the latest 5 (card and chart)
    if result is None:
        ui.page_header(user, "Your result")
        ui.no_score_card()
        return
    ui.page_header(user, "Your result", ui.date_time(result["created_at"]))
    if result.get("save_error"):                          # scored, but the database could not store it
        ui.alert(result["save_error"])
    left, right = ui.two_columns("result", "fixed")
    with left:
        ui.score_card(result, chart_points(checks, result))
        ui.limit_card(result)
    with right:
        ui.health_card(result)
        st.button("Apply to a lender", type="primary", key="to_apply", on_click=ui.go, args=("apply",), width="stretch")
