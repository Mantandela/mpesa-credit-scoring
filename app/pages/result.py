"""Result: score, tier, chance of default, score over time, the seven areas."""
import pandas as pd
import streamlit as st

from app import components as ui, service
from app.pages import current_result

PROTOTYPE_NOTE = "Prototype, trained on simulated data"


def render(conn, user) -> None:
    result = current_result(conn, user)
    if result is None:
        ui.title("Your result")
        st.button("Check your score", type="primary", key="result_cta", on_click=ui.go, args=("score",), width="stretch")
        return
    ui.title("Your result", PROTOTYPE_NOTE)
    ui.hero(result["score"], result["tier"], f"Chance of default {ui.pct(result['pd'])}")

    history = service.score_history(conn, user["id"])
    if len(history) >= 2:
        with st.container(key="card_trend"):
            ui.section("Score over time")
            df = pd.DataFrame(history, columns=["Date", "Score"])
            df["Date"] = pd.to_datetime(df["Date"])
            st.line_chart(df, x="Date", y="Score", color=ui.theme.PURPLE, height=180)

    with st.container(key="card_areas"):
        ui.section("Your seven areas")
        ui.html("".join(ui.row(p["name"], ui.status_text(p["label"])) for p in result["pillars"]))
    st.button("See reasons and loan check", type="primary", key="to_reasons", on_click=ui.go, args=("reasons",),
              width="stretch")
