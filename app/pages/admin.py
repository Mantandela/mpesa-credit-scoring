"""Admin screens: Overview, Users (and Add a lender or admin), Audit.

Every screen reads and writes through app/staff_service.py, which checks the admin role on the server side. An admin
sees counts, accounts and the audit log in plain language: never snapshots, lender notes, vendor names, amounts, file
names or statement data, and cannot decide applications.
"""
import re
from functools import lru_cache
from html import escape

import streamlit as st

from app import auth, components as ui, service, staff_service as SS, theme

ROLE_LABEL = {"vendor": "Vendor", "lender": "Lender", "admin": "Admin"}
NOT_RECORDED = "Not recorded"
MODEL_REPORT = theme.ROOT / "docs" / "model_report.md"


# ------------------------------------------------------------------ overview
METRICS = (("Scores run (7 days)", "scores_7d", "gauge", "Last 7 days"),
           ("Applications sent", "applications", "send", "All time"),
           ("Applications decided", "decided", "check_circle", "All time"),
           ("Uploads rejected", "uploads_rejected", "x_circle", "Last 7 days"))


def _metric(label: str, value, icon_name: str, sub: str = "") -> str:
    return (f'<div class="metric" role="group" aria-label="{escape(label)}"><div class="m-top">{ui.cap(label)}'
            f'<span class="icon-circle">{ui.icon(icon_name, theme.INDIGO, 20)}</span></div>'
            f'<div class="m-value">{value:,}</div>' + (f'<div class="m-sub">{escape(sub)}</div>' if sub else "") + "</div>")


@lru_cache(maxsize=8)
def test_auc(stem: str) -> str | None:
    """The test AUC of the active model from the results table of docs/model_report.md (the model files carry no
    metrics). None when the report or the model's row is missing: shown as "Not recorded", never guessed."""
    try:
        text = MODEL_REPORT.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = [ln for ln in text.splitlines() if ln.startswith("|")]
    for i, ln in enumerate(lines):
        head = [c.strip().lower() for c in ln.strip("|").split("|")]
        if "model" in head and "test auc" in head:
            col = head.index("test auc")
            for row in lines[i + 2:]:
                cells = [c.strip() for c in row.strip("|").split("|")]
                if cells and cells[0] == stem and len(cells) > col and re.fullmatch(r"0?\.\d+|1(\.0+)?", cells[col]):
                    return cells[col]
            return None
    return None


def render_overview(conn, user) -> None:
    o = SS.admin_overview(conn, user)
    ui.page_header(user, "Overview", "Platform activity")
    ui.html('<div class="metrics">' + "".join(_metric(label, o[key], ico, sub) for label, key, ico, sub in METRICS)
            + "</div>")
    left, right = ui.two_columns("overview", "fixed")
    with left:
        with st.container(key="card_tiers"):
            ui.section("Scores by risk level")
            ui.muted("Share of saved score checks in the last 30 days")
            total = sum(o["tiers_30d"].values())
            if not total:
                ui.muted("No saved score checks in the last 30 days.")
            else:
                words = ", ".join(f"{ui.tier_word(t)} {100 * n / total:.0f}%" for t, n in o["tiers_30d"].items())
                ui.html(ui.risk_bars(o["tiers_30d"], f"Scores by risk level: {words}."))
    with right:
        with st.container(key="card_model"):
            ui.section("Model")
            features = service.reference().get("features") if _model_files_ok() else None
            ui.html(ui.row("Active model", escape(o["model"]))
                    + ui.row("Test AUC", escape(test_auc(o["model_stem"]) or NOT_RECORDED))
                    + ui.row("Training data", "Trained on simulated data")
                    + ui.row("Features", str(len(features)) if features else NOT_RECORDED))


def _model_files_ok() -> bool:
    try:
        return service.reference_path().exists()
    except Exception:                      # noqa: BLE001 - a missing or odd path: "Not recorded"
        return False


# ------------------------------------------------------------------ users
def _status_html(u: dict) -> str:
    if u["status"] == "disabled":
        return ui.pill("Disabled", "neutral")
    if u["status"] == "locked":
        return ui.pill(f"Locked for {u['minutes']} min", "bad")
    return ui.pill("Active", "good")


def _role_text(u: dict) -> str:
    return ROLE_LABEL[u["role"]] + (f" · {u['org_name']}" if u["org_name"] else "")


def _act(action: str, user_id: int) -> None:
    """Row button callback: only records the intent; the page applies it with the run's connection."""
    st.session_state["user_action"] = (action, int(user_id))


def _apply_action(conn, user) -> str | None:
    intent = st.session_state.pop("user_action", None)
    if not intent:
        return None
    action, uid = intent
    try:
        if action == "unlock":
            SS.unlock_user(conn, user, uid)
        else:
            SS.set_user_active(conn, user, uid, action == "enable")
    except service.UserError as e:
        return str(e)
    return None


def render_users(conn, user) -> None:
    message = _apply_action(conn, user)
    people = SS.list_users(conn, user)                             # the one query of the page
    ui.page_header(user, "Users", f"{len(people)} account{'s' * (len(people) != 1)}",
                   actions=(("Add a lender or admin", "add_user", "admin_add", "primary"),))
    with st.container(key="card_users"):
        if message:
            ui.alert(message)
        with st.container(key="utable"):
            ui.html('<div class="trow thead ugrid-head"><div class="tcells ugrid"><span>Email</span><span>Role</span>'
                    '<span>Status</span></div><span class="uact-h"></span></div>')
            for u in people:
                with st.container(horizontal=True, key=f"urow_{u['id']}", vertical_alignment="center"):
                    ui.html(f'<div class="tcells ugrid"><span class="c email">{ui.avatar(u["email"], "sm")}'
                            f'<span class="t">{escape(u["email"])}</span></span>'
                            f'<span class="c m">{escape(_role_text(u))}</span><span class="c">{_status_html(u)}</span></div>',
                            width="stretch")
                    if u["status"] == "locked":
                        st.button("Unlock", key=f"unlock_{u['id']}", on_click=_act, args=("unlock", u["id"]))
                    elif u["status"] == "disabled":
                        st.button("Enable", key=f"enable_{u['id']}", on_click=_act, args=("enable", u["id"]))
                    elif u["is_self"]:
                        ui.html('<span class="uself">This is you</span>', width="content")
                    else:
                        st.button("Disable", key=f"disable_{u['id']}", on_click=_act, args=("disable", u["id"]))


def render_add_user(conn, user) -> None:
    """Add a lender or an admin. The one-time password is drawn on THIS run only (a local variable): it is not put in
    session state, the database (only its hash), the audit log or any log line, so it cannot be shown again."""
    ui.page_header(user, "Add a lender or admin", "Users",
                   actions=(("Back to users", "back_users", "admin_users", "secondary"),))
    with st.container(key="card_add_user"):
        ui.section("New account")
        ui.muted("Vendors and lenders can also sign up themselves. One lender account per organisation.")
        with st.form("add_user_form", border=False, clear_on_submit=True):
            email = st.text_input("Email", key="new_email", autocomplete="off")
            role = st.radio("Account type: Lender or Admin", ("lender", "admin"), format_func=ROLE_LABEL.get,
                            key="new_role", horizontal=True)
            org = st.text_input("Organisation (lenders only)", key="new_org", autocomplete="off")
            submitted = st.form_submit_button("Create account", type="primary", key="create_user", width="stretch")
        if submitted:
            try:
                new, password = SS.create_staff_user(conn, user, email, role, org)
            except (auth.AuthError, service.UserError) as e:
                ui.alert(str(e))
            else:
                with st.container(key="card_password"):
                    ui.section(f"Lender account created for {new['org_name']}" if new["role"] == "lender"
                               else "Admin account created")
                    ui.html(ui.row("Email", escape(new["email"])) + ui.row("Role", escape(ROLE_LABEL[new["role"]])))
                    ui.html('<div class="pwd-line">One-time password. It is shown only now and is not stored: copy it and '
                            'give it to the person safely.</div>')
                    st.code(password, language=None)
                password = None


# ------------------------------------------------------------------ audit
def _page_to(n: int) -> None:
    st.session_state["audit_page"] = max(0, n)


def render_audit(conn, user) -> None:
    page = int(st.session_state.get("audit_page", 0))
    data = SS.audit_page(conn, user, page)
    if not data["rows"] and page > 0:                               # e.g. the log got shorter: back to the first page
        _page_to(0)
        data = SS.audit_page(conn, user, 0)
    rows = data["rows"]
    ui.page_header(user, "Audit", f"Newest first · page {data['page'] + 1}")
    with st.container(key="card_audit"):
        if not rows:
            ui.muted("Nothing recorded yet.")
        else:
            body = "".join(f"<tr><td>{escape(r['who'])}</td><td class=\"note\">{escape(r['what'])}</td>"
                           f"<td>{escape(ui.date_time(r['when']))}</td></tr>" for r in rows)
            table = ('<div class="only-wide tbl-wrap"><table class="tbl"><thead><tr><th>Who</th><th>What</th><th>When</th>'
                     f'</tr></thead><tbody>{body}</tbody></table></div>')
            items = "".join(f'<div class="arow"><div class="a-what">{escape(r["what"])}</div>'
                            f'<div class="a-sub">{escape(r["who"])} · {escape(ui.date_time(r["when"]))}</div></div>'
                            for r in rows)
            ui.html(table + f'<div class="only-narrow">{items}</div>')
        with st.container(horizontal=True, key="audit_pager"):
            st.button("Previous", key="audit_prev", on_click=_page_to, args=(data["page"] - 1,),
                      disabled=data["page"] == 0)
            st.button("Next", key="audit_next", on_click=_page_to, args=(data["page"] + 1,), disabled=not data["has_next"])
