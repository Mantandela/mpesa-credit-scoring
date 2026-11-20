"""My applications: one line per application; open a line for its details."""
from html import escape

import streamlit as st

from app import components as ui, service, theme


def _md_escape(s: str) -> str:
    return "".join("\\" + c if c in "\\`*_[]()#+-.!:|<>~$" else c for c in s)


def render(conn, user) -> None:
    ui.top_bar(user, "Applications", "Sent to lenders")
    apps = service.list_applications(conn, user["id"])
    if not apps:
        with st.container(key="card_empty"):
            ui.html(f'<div class="center"><div class="icon-circle lg">{ui.icon("inbox", theme.PURPLE, 28)}</div>'
                    '<div class="section" style="margin-top:12px">No applications yet</div>'
                    '<div class="caption" style="margin-top:4px">Check your score, then apply to a lender.</div></div>')
            st.button("Check your score", key="history_cta", on_click=ui.go, args=("score",), width="stretch")
        return
    for a in apps:
        status = a["status"].capitalize()
        with st.expander(f"{_md_escape(a['lender'])}  {ui.status_md(status)}", key=f"app_{a['id']}"):
            rows = (ui.row("Reference", escape(a["ref"])) + ui.row("Date", ui.short_date(a["created_at"]))
                    + ui.row("Request", f"{ui.money(a['request']['amount'])}, {a['request']['term_days']:.0f} days")
                    + ui.row("Score", f"{a['score']} / 850"))
            if a["status"] == "declined" and a["lender_note"]:
                rows += ui.row("Lender note", escape(a["lender_note"]))
            ui.html(rows)
