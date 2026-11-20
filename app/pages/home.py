"""Home: top bar with greeting, score hero, quick actions, latest application, score breakdown."""
from html import escape

import streamlit as st

from app import components as ui, service
from app.pages import current_result


def render(conn, user) -> None:
    ui.top_bar(user, home=True)
    result = current_result(conn, user)
    if result is None:
        ui.hero(cta=True)
    else:
        ui.hero(result["score"], result["tier"])

    with st.container(horizontal=True, key="quick_actions"):
        for key, label, page in (("qa_score", "Check score", "score"),
                                 ("qa_loan", "Loan check", "reasons" if result else "score"),
                                 ("qa_history", "History", "history"),
                                 ("qa_more", "More", "profile")):
            st.button(label, key=key, on_click=ui.go, args=(page,), width="stretch")

    ui.section("Latest application")
    apps = service.list_applications(conn, user["id"])
    with st.container(key="card_latest"):
        if apps:
            a = apps[0]
            st.button(f"{a['lender']}  {ui.status_md(a['status'].capitalize())}", key="row_latest_app",
                      on_click=ui.go, args=("history",), width="stretch")
        else:
            ui.html(f'<div class="muted">{escape("No applications yet")}</div>')

    if result is not None:
        with st.container(key="card_breakdown"):
            st.button("Score breakdown", key="row_breakdown", on_click=ui.go, args=("result",), width="stretch")
