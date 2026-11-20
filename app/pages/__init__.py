"""One module per screen. Each exposes render(conn, user); app/main.py routes between them.

Helpers shared by several vendor screens live here.
"""
import streamlit as st

from app import service


def current_result(conn, user) -> dict | None:
    """The result to show: the check made in this session, else the latest saved one."""
    return st.session_state.get("result") or service.latest_check(conn, user["id"])


def comfortable_amount(result: dict | None) -> int | None:
    """The estimated comfortable amount when it is known and above 0 (used to prefill amounts), else None."""
    el = (result or {}).get("eligibility") or {}
    amt = el.get("comfortable_amount")
    return int(amt) if el.get("status") == "eligible" and amt else None
