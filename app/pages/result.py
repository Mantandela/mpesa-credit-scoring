"""Result: score, tier, chance of default, score over time, the seven areas."""
import altair as alt
import pandas as pd
import streamlit as st

from app import components as ui, service, theme
from app.pages import current_result

def _chart(history) -> alt.Chart:
    df = pd.DataFrame(history, columns=["Date", "Score"])
    df["Date"] = pd.to_datetime(df["Date"])
    lo, hi = max(300, int(df.Score.min()) - 30), min(850, int(df.Score.max()) + 30)
    fmt = "%H:%M" if df.Date.dt.date.nunique() == 1 else "%d %b"          # all checks on one day: show times
    base = alt.Chart(df).encode(
        x=alt.X("Date:T", title=None, axis=alt.Axis(format=fmt, labelColor=theme.MUTED, grid=False,
                                                    values=df.Date.tolist(), labelOverlap="greedy")),
        y=alt.Y("Score:Q", title=None, scale=alt.Scale(domain=[lo, hi]),
                axis=alt.Axis(labelColor=theme.MUTED, gridColor="#EFEAFA", tickCount=4, domain=False)))
    return (base.mark_line(color=theme.PURPLE, strokeWidth=3, interpolate="monotone")
            + base.mark_circle(color=theme.PURPLE, size=60)).properties(height=170, background="#FFFFFF") \
        .configure_view(strokeWidth=0)


def render(conn, user) -> None:
    result = current_result(conn, user)
    ui.top_bar(user, "Your result")
    if result is None:
        ui.hero(cta=True)
        return
    ui.hero(result["score"], result["tier"], f"Chance of default {ui.pct(result['pd'])}")

    history = service.score_history(conn, user["id"])
    if len(history) >= 2:
        with st.container(key="card_trend"):
            ui.section("Score over time")
            st.altair_chart(_chart(history), width="stretch")

    with st.container(key="card_areas"):
        ui.section("Your seven areas")
        ui.html("".join(ui.row(p["name"], ui.status_text(p["label"]), f'<span class="num">{i}</span>')
                        for i, p in enumerate(result["pillars"], start=1)))
    st.button("See reasons and loan check", type="primary", key="to_reasons", on_click=ui.go, args=("reasons",),
              width="stretch")
