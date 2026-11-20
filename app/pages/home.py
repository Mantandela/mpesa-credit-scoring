"""Home: top bar with greeting, score hero, business health (the seven areas) and the latest applications."""
import streamlit as st

from app import components as ui, service
from app.pages import current_result

N_LATEST = 3


def render(conn, user) -> None:
    ui.top_bar(user, home=True)
    result = current_result(conn, user)        # this session's check, else the latest saved one
    if result is None:
        ui.hero(cta=True)
    else:
        ui.hero(result["score"], result["tier"])
        with st.container(key="card_health"):
            ui.section("Business health")
            ui.html("".join(ui.row(p["name"], ui.status_text(p["label"])) for p in result["pillars"]))

    apps = service.list_applications(conn, user["id"])[:N_LATEST]
    with st.container(key="card_latest"):
        ui.section("Latest applications")
        if not apps:
            ui.muted("No applications yet")
        for a in apps:
            st.button(f"{a['lender']}  {ui.status_md(a['status'].capitalize())}", key=f"row_app_{a['id']}",
                      on_click=ui.go, args=("history",), width="stretch")
