"""One module per screen. Each exposes render(conn, user); app/main.py routes between them.

Helpers shared by several vendor screens live here.
"""
import streamlit as st

from app import service

CHART_CHECKS = 5          # the score chart shows the last 5 checks


def current_result(conn, user) -> dict | None:
    """The result to show: the check made in this session, else the latest saved one."""
    return st.session_state.get("result") or service.latest_check(conn, user["id"])


def checks_and_result(conn, user, limit: int | None = CHART_CHECKS) -> tuple:
    """(saved checks newest first, the result to show) from ONE checks query: the session's result, else the latest
    saved check. Home and Result use the last 5 (score card and chart), History all checks."""
    checks = service.recent_checks(conn, user["id"], limit)
    return checks, st.session_state.get("result") or (checks[0] if checks else None)


def chart_points(checks: list, result: dict | None, n: int = CHART_CHECKS) -> list:
    """[(created_at ISO, score)] for the chart, oldest first, at most n. A result of this session that is not saved
    (save_results off, or the fresh result of an Apply) is the latest point, so the chart ends at the score shown."""
    points = [(c["created_at"], c["score"]) for c in reversed(checks[:n])]
    if result is not None and result.get("created_at") and (
            result.get("check_id") is None or result["check_id"] not in {c["check_id"] for c in checks}):
        points.append((result["created_at"], result["score"]))
    return points[-n:]


def comfortable_amount(result: dict | None) -> int | None:
    """The estimated comfortable amount when it is known and above 0 (used to prefill amounts), else None."""
    el = (result or {}).get("eligibility") or {}
    amt = el.get("comfortable_amount")
    return int(amt) if el.get("status") == "eligible" and amt else None
