"""History: "My applications" and "Score checks". Never shows a file name (none is stored).

One render: each list is drawn as a table (shown from 900px; a wide table scrolls inside its card) and as expandable
rows (shown below 900px). Both are plain HTML from the same rows, so the page state is not involved. Statuses and risk
levels are pills; the lender's note is shown for every status that has one. Approved loans also show the repayment
status the lender recorded (a pill) and the due date; the vendor can see it but never change it."""
from html import escape

import streamlit as st

from app import components as ui, service
from app.pages import checks_and_result

CHECK_REF_OFFSET = 100              # display reference of a saved check: "C-" + (check id + 100), like "A-" for applications


def check_ref(check: dict) -> str:
    return f"C-{CHECK_REF_OFFSET + int(check['check_id'])}"


def _limit_text(el: dict) -> str:
    if el["status"] == "eligible":
        return f"Up to {ui.money(el['max_amount'])}"
    return "Not eligible" if el["status"] == "not_eligible" else "Not enough income data"


def _table(head: list, rows: list) -> str:
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(r) + "</tr>" for r in rows)
    return f'<div class="only-wide tbl-wrap"><table class="tbl"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def _td(text: str = "", html_value: str | None = None, cls: str = "") -> str:
    c = f' class="{cls}"' if cls else ""
    return f"<td{c}>{html_value if html_value is not None else escape(text)}</td>"


def _xrow(main: str, sub: str, side_html: str, details: list) -> str:
    rows = "".join(ui.row(k, v) for k, v in details)
    return (f'<details class="xrow"><summary><span class="x-main">{escape(main)}<span class="x-sub">{escape(sub)}</span>'
            f'</span><span class="x-side">{side_html}</span><span class="x-chev">{ui.icon("chevron", ui.MUTED_HEX, 18)}'
            f'</span></summary><div class="x-body">{rows}</div></details>')


def _checks_card(checks: list) -> None:
    with st.container(key="card_checks"):
        ui.section("Score checks")
        if not checks:
            ui.muted("No score checks yet.")
            st.button("Check score", key="history_cta", type="tertiary", on_click=ui.go, args=("score",))
            return
        table = _table(["Date", "Reference", "Score", "Risk", "Default risk", "Estimated limit"], [
            [_td(ui.date_time(c["created_at"])), _td(check_ref(c)), _td(str(c["score"])),
             _td(html_value=ui.pill(c["tier"])), _td(ui.pct(c["pd"])), _td(_limit_text(c["eligibility"]))]
            for c in checks])
        rows = "".join(_xrow(ui.short_date(c["created_at"]), check_ref(c),
                             f'<b>{c["score"]}</b>&nbsp;{ui.pill(c["tier"])}',
                             [("Date", escape(ui.date_time(c["created_at"]))), ("Default risk", ui.pct(c["pd"])),
                              ("Estimated limit", escape(_limit_text(c["eligibility"])))]) for c in checks)
        ui.html(table + f'<div class="only-narrow">{rows}</div>')


def _apps_card(apps: list) -> None:
    with st.container(key="card_apps"):
        ui.section("My applications")
        if not apps:
            ui.muted("No applications yet.")
            st.button("Apply to a lender", key="history_apply", type="tertiary", on_click=ui.go, args=("apply",))
            return

        def request(a):
            return f"{ui.money(a['request']['amount'])} · {a['request']['term_days']:.0f} days"

        def note(a):                                   # pending, approved or declined: shown whenever there is one
            return a["lender_note"] or ""

        def repayment(a):
            r = a.get("repayment")
            if not r:
                return "-"
            return (f'<span class="rcell">{ui.pill(r["label"])}<span class="rdue">Due '
                    f'{escape(ui.date_only(r["due_date"]))}</span></span>')

        table = _table(["Lender", "Reference", "Date", "Request", "Status", "Repayment", "Lender note"], [
            [_td(a["lender"]), _td(a["ref"]), _td(ui.short_date(a["created_at"])), _td(request(a)),
             _td(html_value=ui.pill(a["status"].capitalize())), _td(html_value=repayment(a)),
             _td(note(a) or "-", cls="note")]
            for a in apps])
        rows = "".join(_xrow(a["lender"], a["ref"], ui.pill(a["status"].capitalize()),
                             [("Date", ui.short_date(a["created_at"])), ("Request", escape(request(a))),
                              ("Score", f"{a['score']} / 850")]
                             + ([("Repayment", ui.pill(a["repayment"]["label"])),
                                 ("Due", escape(ui.date_only(a["repayment"]["due_date"])))] if a.get("repayment") else [])
                             + ([("Lender note", escape(note(a)))] if note(a) else [])) for a in apps)
        ui.html(table + f'<div class="only-narrow">{rows}</div>')


def render(conn, user) -> None:
    checks, _ = checks_and_result(conn, user, limit=None)          # the one checks query, all checks
    apps = service.list_applications(conn, user["id"])
    n_c, n_a = len(checks), len(apps)
    ui.page_header(user, "History", f"{n_c} check{'s' * (n_c != 1)} · {n_a} application{'s' * (n_a != 1)}")
    _apps_card(apps)
    _checks_card(checks)
