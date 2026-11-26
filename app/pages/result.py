"""Result: the hero score card (with the score over time) and the estimated limit, then the Business health tiles and
"Apply to a lender". The score itself comes from Check score; nothing is re-scored here. Right after a score was
computed the hero card tilts in (theme.MOTION_CSS)."""
import streamlit as st

from app import components as ui, theme
from app.pages import chart_points, checks_and_result

FINAL_DECISION = ui.FINAL_DECISION


def render(conn, user) -> None:
    theme.inject_motion(*(("tilt-in-hero",) if st.session_state.pop("just_scored", False) else ()))
    checks, result = checks_and_result(conn, user)        # one checks query: the latest 5 (card and chart)
    if result is None:
        ui.page_header(user, "Your result", "Result")
        ui.no_score_card()
        return
    ui.page_header(user, "Your result", ui.date_time(result["created_at"]))
    if result.get("save_error"):                          # scored, but the database could not store it
        ui.alert(result["save_error"])
    left, right = ui.two_columns("result", "fixed")
    with left:
        ui.score_hero(result, chart_points(checks, result), reasons_button=True)
    with right:
        ui.limit_card(result)
        st.button("Apply to a lender", type="primary", key="to_apply", on_click=ui.go, args=("apply",), width="stretch")
    ui.health_tiles(result["pillars"])
