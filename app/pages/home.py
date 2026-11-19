"""Home: greeting, latest score, quick actions, latest application, score breakdown."""
import streamlit as st

from app import components as ui, service
from app.pages import current_result


def render(conn, user) -> None:
    first = (user["name"] or "").split()[0] if user["name"] else ""
    ui.title(f"{ui.greeting()}, {first}")
    result = current_result(conn, user)
    if result is None:
        with st.container(key="card_cta"):
            ui.section("Check your score")
            ui.muted("Upload your M-Pesa statement to start.")
            st.button("Check your score", type="primary", key="cta_score", on_click=ui.go, args=("score",), width="stretch")
        return

    ui.hero(result["score"], result["tier"])
    with st.container(key="quick_actions"):
        cols = st.columns(4)
        actions = (("qa_score", "Check score", ":material/speed:", "score"),
                   ("qa_loan", "Loan check", ":material/payments:", "reasons"),
                   ("qa_history", "History", ":material/receipt_long:", "history"),
                   ("qa_more", "More", ":material/more_horiz:", "profile"))
        for col, (key, label, ico, page) in zip(cols, actions):
            with col:
                st.button(label, key=key, icon=ico, on_click=ui.go, args=(page,), width="stretch")

    apps = service.list_applications(conn, user["id"])
    with st.container(key="card_home_rows"):
        if apps:
            ui.html('<div class="muted">Latest application</div>')
            a = apps[0]
            st.button(f"{a['lender']}  {ui.status_md(a['status'].capitalize())}", key="row_latest_app",
                      on_click=ui.go, args=("history",), width="stretch")
        st.button("Score breakdown", key="row_breakdown", on_click=ui.go, args=("result",), width="stretch")
