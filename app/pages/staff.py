"""Lender and admin screens: stage 2. Stubs with a sign-out button for now."""
from html import escape

import streamlit as st

from app import components as ui


def _stub(user, heading) -> None:
    ui.title(heading, user.get("org_name") or user["name"])
    with st.container(key="card_stage2"):
        ui.section("Stage 2")
        ui.html(f'<div class="muted">Signed in as {escape(user["email"])}</div>')
    st.button("Sign out", key="sign_out", on_click=ui.sign_out, width="stretch")


def render_lender(conn, user) -> None:
    _stub(user, "Lender")


def render_admin(conn, user) -> None:
    _stub(user, "Admin")
