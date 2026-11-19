"""One module per screen. Each exposes render(conn, user); app/main.py routes between them.

Helpers shared by several vendor screens live here.
"""
import streamlit as st

from app import service


def current_result(conn, user) -> dict | None:
    """The result to show: the check made in this session, else the latest saved one."""
    return st.session_state.get("result") or service.latest_check(conn, user["id"])
