"""Lender screens: Queue and Decided (one table, different default filter), Review application, Profile.

Every screen reads through app/staff_service.py, which checks the lender role and the organisation (applications
addressed to this lender account only) on the server side. A lender sees the snapshot the vendor shared and the vendor's
name, never the statement or the vendor's other checks. Lenders only approve or decline; the decision is final.

Decided also tracks repayment: approved loans show their repayment status and due date, a summary card counts them,
and while a loan is repaying "Record" opens a dialog (outcome, optional note, then a confirm step) whose choice the page
applies on the next full run through staff_service.record_repayment, which enforces every rule server-side.

Laptop: the applications table (one row per application, the reference opens the review). Phone: small cards.
Review: two columns on a laptop (the Decision card on the right), stacked on a phone with the Decision card last.
"""
from datetime import date
from html import escape

import streamlit as st

from app import auth, components as ui, service, staff_service as SS, theme

QUEUE_FILTERS = ("pending", "all")                                   # Queue: Pending N / All N
DECIDED_FILTERS = ("decided", "approved", "declined", "awaiting")    # ... and Awaiting outcome (approved, repaying)
FILTERS_FOR = {"lender": QUEUE_FILTERS, "lender_decided": DECIDED_FILTERS}
FILTER_LABEL = {"pending": "Pending", "approved": "Approved", "declined": "Declined", "all": "All",
                "decided": "All decided", "awaiting": "Awaiting outcome"}
DEFAULT_FILTER = {"lender": "pending", "lender_decided": "decided"}
CAP_FOR = {"lender": "Queue", "lender_decided": "Decided"}
QCOLS = ("Vendor", "Request", "Score", "Risk", "Estimated limit", "Status")
DCOLS = ("Vendor", "Request", "Score", "Risk", "Status", "Repayment")         # the Decided table
REPAY_OPEN, REPAY_STEP, REPAY_INTENT, REPAY_RERUN = "repay_open", "repay_step", "repay_intent", "repay_rerun"
CANNOT_CHANGE = "This cannot be changed afterwards."
SUMMARY_ONLY = "You see this summary only. The statement is never shared. Decisions are final."
NOTE_LABEL = "Note to the vendor (optional)"
INTENT = "lender_decision"                    # (application id, "approved" | "declined") set by the two buttons


def _in(a: dict, f: str) -> bool:
    status = a["status"]
    if f == "awaiting":
        return bool(a.get("repayment")) and a["repayment"]["status"] == service.REPAYING
    return f == "all" or status == f or (f == "decided" and status in ("approved", "declined"))


def _due_words(r: dict) -> str:
    """"Due 10 Dec · 5 days left", "Due today", "Due 10 Dec · 3 days overdue"; for a recorded outcome "Recorded 12 Dec"."""
    if r["terminal"]:
        return f"Recorded {ui.short_date(r['recorded_at'])}" if r.get("recorded_at") else ""
    due = date.fromisoformat(r["due_date"]).strftime("%d %b")
    d = r["days_left"]
    if d == 0:
        return "Due today"
    return f"Due {due} · {d} day{'s' * (d != 1)} left" if d > 0 else f"Due {due} · {-d} day{'s' * (d != -1)} overdue"


def _repay_html(a: dict) -> str:
    r = a.get("repayment")
    if not r:
        return '<span class="m">-</span>'
    return f'<span class="rcell">{ui.pill(r["label"])}<span class="rdue">{escape(_due_words(r))}</span></span>'


def _request(a: dict) -> str:
    return f"{ui.money(a['request']['amount'])} · {a['request']['term_days']:.0f} days"


def _limit_html(el: dict) -> str:
    text, like = ui.snapshot_limit(el)
    if like == "declined":
        return ui.pill(text, "bad")
    return f'<span class="m">{escape(text)}</span>' if like == "unknown" else escape(text)


def _status(a: dict) -> str:
    return ui.pill(a["status"].capitalize())


def _risk(a: dict) -> str:
    return ui.pill(ui.tier_word(a["tier"]), ui.status_kind(a["tier"]))


def _vendor(a: dict) -> str:
    return f'{ui.avatar(a["vendor"], "sm")}<span class="t">{escape(a["vendor"])}</span>'


def _cells(a: dict, decided: bool = False) -> str:
    head = (f'<span class="c">{_vendor(a)}</span><span class="c">{escape(_request(a))}</span>'
            f'<span class="c">{a["score"]}</span><span class="c">{_risk(a)}</span>')
    if decided:
        return f'<div class="tcells dgrid">{head}<span class="c">{_status(a)}</span><span class="c">{_repay_html(a)}</span></div>'
    return (f'<div class="tcells qgrid">{head}<span class="c">{_limit_html(a["eligibility"])}</span>'
            f'<span class="c">{_status(a)}</span></div>')


def _awaiting(a: dict) -> bool:
    return bool(a.get("repayment")) and not a["repayment"]["terminal"]


def _open_record(app_id: int) -> None:
    st.session_state[REPAY_OPEN] = int(app_id)
    st.session_state.pop(REPAY_STEP, None)


def _open(page: str, app_id: int) -> None:
    ui.go("lender_review", review_id=app_id, review_from=page)


def _table(apps: list, page: str) -> None:
    """Laptop: header and one row per application; the reference (indigo, bold) is the button that opens the review.
    On Decided, a last column holds "Record" while a loan is repaying."""
    decided = page == "lender_decided"
    with st.container(key="qtable"):
        head = "".join(f"<span>{escape(h)}</span>" for h in (DCOLS if decided else QCOLS))
        grid = "dgrid" if decided else "qgrid"
        ui.html(f'<div class="trow thead"><span class="tref">Reference</span><div class="tcells {grid}">{head}</div>'
                + ('<span class="ract-h"></span>' if decided else "") + "</div>")
        for a in apps:
            with st.container(horizontal=True, key=f"qrow_{a['id']}", vertical_alignment="center"):
                st.button(a["ref"], key=f"open_{a['id']}", type="tertiary", on_click=_open, args=(page, a["id"]),
                          help=f"Review {a['ref']}")
                ui.html(_cells(a, decided), width="stretch")
                if decided:
                    if _awaiting(a):
                        st.button("Record", key=f"rec_{a['id']}", on_click=_open_record, args=(a["id"],),
                                  help=f"Record the repayment of {a['ref']}")
                    else:
                        ui.html('<span class="ract-none"></span>', width="content")


def _list(apps: list, page: str) -> None:
    """Phone: one small card per application (reference, status, vendor, the details) with a Review button."""
    with st.container(key="qlist"):
        for a in apps:
            with st.container(key=f"qcard_{a['id']}"):
                ui.html(f'<div class="qc-head"><span class="qc-ref">{escape(a["ref"])}</span>{_status(a)}</div>'
                        f'<div class="qc-who">{_vendor(a)}</div>'
                        + ui.row("Request", escape(_request(a))) + ui.row("Score", f"{a['score']} / 850")
                        + ui.row("Risk", _risk(a)) + ui.row("Estimated limit", _limit_html(a["eligibility"]))
                        + ui.row("Submitted", escape(ui.short_date(a["created_at"])))
                        + (ui.row("Repayment", _repay_html(a)) if a.get("repayment") else ""))
                st.button("Review application", key=f"popen_{a['id']}", on_click=_open, args=(page, a["id"]),
                          width="stretch")
                if page == "lender_decided" and _awaiting(a):
                    st.button("Record repayment", key=f"mrec_{a['id']}", type="primary", on_click=_open_record,
                              args=(a["id"],), width="stretch")


# ------------------------------------------------------------------ repayment: dialog and summary
def _continue(app_id: int) -> None:
    st.session_state[REPAY_STEP] = (int(app_id), st.session_state.get(f"repay_choice_{app_id}"),
                                    st.session_state.get(f"repay_note_{app_id}") or "")


def _back() -> None:
    st.session_state.pop(REPAY_STEP, None)


def _confirm(app_id: int) -> None:
    """Confirm: only records the intent; the page applies it on the next full run with that run's connection."""
    step = st.session_state.pop(REPAY_STEP, None)
    if step and step[0] == int(app_id):
        st.session_state[REPAY_INTENT] = step
    st.session_state.pop(REPAY_OPEN, None)
    st.session_state[REPAY_RERUN] = True


def _dismiss() -> None:
    for k in (REPAY_OPEN, REPAY_STEP):
        st.session_state.pop(k, None)


@st.dialog("Record repayment", width="small", on_dismiss=_dismiss)
def record_dialog(a: dict) -> None:
    """Choose the outcome (Defaulted only once the due date has passed) and an optional note, then confirm. A click in
    a dialog reruns only the dialog, so Confirm asks for a full rerun, which applies the choice and closes it."""
    if st.session_state.pop(REPAY_RERUN, False):
        st.rerun()
    r = a["repayment"]
    ui.html(f'<div class="section">{escape(a["ref"])} · {escape(a["vendor"])}</div>'
            f'<div class="muted">{escape(_request(a))} · {escape(_due_words(r))}</div>')
    step = st.session_state.get(REPAY_STEP)
    if not step or step[0] != a["id"]:
        options = [service.ON_TIME, service.LATE] + ([service.DEFAULTED] if r["days_left"] < 0 else [])
        st.radio("Outcome", options, format_func=service.REPAYMENT_LABEL.get, key=f"repay_choice_{a['id']}")
        if service.DEFAULTED not in options:
            ui.muted(f"Defaulted can be recorded after the due date ({ui.date_only(r['due_date'])}).")
        st.text_area("Note (optional)", key=f"repay_note_{a['id']}", max_chars=300, height=90)
        st.button("Continue", key="repay_continue", type="primary", on_click=_continue, args=(a["id"],), width="stretch")
    else:
        _, status, note = step
        ui.html(f'<div class="repay-confirm">Record {ui.pill(service.REPAYMENT_LABEL[status])} for '
                f'{escape(a["ref"])}?</div><div class="alert-text" role="alert">{ui.icon("alert", theme.DANGER, 16)}'
                f'<span>{CANNOT_CHANGE}</span></div>'
                + (f'<div class="note-box">{escape(note)}</div>' if note.strip() else ""))
        with st.container(horizontal=True, key="repay_buttons"):
            st.button("Back", key="repay_back", on_click=_back)
            st.button("Confirm", key="repay_confirm", type="primary", on_click=_confirm, args=(a["id"],))


def _apply_repayment(conn, user) -> tuple:
    """Apply a confirmed outcome (staff_service checks everything again). Returns (kind, message) or None."""
    st.session_state.pop(REPAY_RERUN, None)
    intent = st.session_state.pop(REPAY_INTENT, None)
    if not intent:
        return None
    app_id, status, note = intent
    try:
        a = SS.record_repayment(conn, user, app_id, status, note)
    except SS.RepaymentError as e:
        return ("error", str(e))
    except auth.AccessDenied:
        return ("error", SS.REPAY_REFUSED)
    return ("ok", f"{a['ref']}: {a['repayment']['label']} recorded.")


def _summary_card(apps: list, message) -> None:
    n = SS.repayment_counts(apps)
    items = ((service.REPAYING, "Repaying"), (service.ON_TIME, "On time"), (service.LATE, "Late"),
             (service.DEFAULTED, "Defaulted"))
    with st.container(key="card_rsummary"):
        ui.html(ui.cap("Repayment outcomes") + '<div class="rsum">' + "".join(
            f'<div class="rsum-i"><span class="rsum-n">{n[s]}</span>{ui.pill(label, ui.status_kind(service.REPAYMENT_LABEL[s]))}</div>'
            for s, label in items) + "</div>")
        if message:
            kind, text = message
            ui.alert(text) if kind == "error" else ui.html(f'<div class="ok-line" role="status">{escape(text)}</div>')


def render_queue(conn, user, page: str = "lender") -> None:
    message = _apply_repayment(conn, user) if page == "lender_decided" else None
    apps = SS.lender_applications(conn, user)                       # the one query of the page
    org = user.get("org_name") or user.get("name") or ""
    ui.page_header(user, "Applications", f"{org} · {CAP_FOR[page]}")
    if page == "lender_decided":
        _summary_card(apps, message)
    filters = FILTERS_FOR[page]
    groups = {f: [a for a in apps if _in(a, f)] for f in filters}
    names = {f: f"{FILTER_LABEL[f]} {len(groups[f])}" for f in filters}
    with st.container(key="card_queue"):
        choice = st.pills("Show", filters, format_func=names.get, default=DEFAULT_FILTER[page], key=f"{page}_filter",
                          label_visibility="collapsed") or DEFAULT_FILTER[page]
        shown = groups[choice]
        if not apps:
            ui.muted("No applications yet.")
        elif not shown:
            ui.muted("No decided applications yet." if choice == "decided"
                     else f"No {FILTER_LABEL[choice].lower()} applications.")
        else:
            _table(shown, page)
            _list(shown, page)
    if page == "lender_decided" and st.session_state.get(REPAY_OPEN):
        target = next((a for a in apps if a["id"] == st.session_state[REPAY_OPEN] and _awaiting(a)), None)
        if target is not None:
            record_dialog(target)
        else:
            _dismiss()


def render_decided(conn, user) -> None:
    render_queue(conn, user, "lender_decided")


# ------------------------------------------------------------------ review
def _decide(app_id: int, decision: str) -> None:
    """Button callback: only records the intent. The page applies it on the next run with that run's connection, so a
    database error goes through the app's error card like any other."""
    st.session_state[INTENT] = (int(app_id), decision)


def _apply_intent(conn, user) -> str | None:
    """Apply a decision the buttons asked for (one conditional update in staff_service). Returns a message to show."""
    intent = st.session_state.pop(INTENT, None)
    if not intent:
        return None
    app_id, decision = intent
    try:
        SS.decide_application(conn, user, app_id, decision, st.session_state.get(f"note_{app_id}"))
    except SS.DecisionError as e:
        return str(e)
    except auth.AccessDenied:
        return None                                  # the read below shows "not available"
    return None


def _application_card(a: dict) -> None:
    snap = a["snapshot"]
    band = (snap.get("affordability") or {}).get("band", "unknown")
    band_html = ui.pill("Not enough income data", "neutral") if band == "unknown" else ui.pill(band.capitalize())
    with st.container(key="card_application"):
        ui.section("Application")
        ui.html(ui.row("Vendor", escape(a["vendor"])) + ui.row("Submitted", escape(ui.date_time(a["created_at"])))
                + ui.row("Request", escape(_request(a))) + ui.row("Request compared with monthly income", band_html)
                + ui.row("Estimated limit", _limit_html(a["eligibility"])))


def _score_card(a: dict) -> None:
    """This application's snapshot only: the hero card WITHOUT a score history chart, no earlier checks."""
    ui.score_hero(a, None, label="Applicant score")


def _health_tiles(a: dict) -> None:
    ui.health_tiles(a["snapshot"]["pillars"], label="What the model weighed")


def _reasons_card(a: dict) -> None:
    with st.container(key="card_lreasons"):
        ui.section("Reasons")
        reasons = a["snapshot"].get("reasons") or []
        ui.html("".join(ui.reason_row(r["direction"], r["phrase"]) for r in reasons) if reasons
                else '<div class="muted">No reasons in this summary.</div>')


def _decision_card(a: dict, message: str | None) -> None:
    with st.container(key="card_decision"):
        ui.section("Decision")
        if message:
            ui.alert(message)
        if a["status"] == "pending":
            st.text_area(NOTE_LABEL, key=f"note_{a['id']}", max_chars=SS.NOTE_MAX, height=110)
            with st.container(horizontal=True, key="decision_buttons"):
                st.button("Approve", key="approve", type="primary", on_click=_decide, args=(a["id"], "approved"))
                st.button("Decline", key="decline", on_click=_decide, args=(a["id"], "declined"))
        else:
            note = a["lender_note"]
            ui.html(f'<div class="decision-out"><div>{_status(a)}</div>'
                    f'<div class="muted">Decided {escape(ui.date_time(a["decided_at"]))} · final</div></div>')
            ui.html(ui.cap("Note to the vendor")
                    + (f'<div class="note-box">{escape(note)}</div>' if note else '<div class="muted">No note.</div>'))
            r = a.get("repayment")
            if r:
                ui.html(ui.cap("Repayment") + ui.row("Status", ui.pill(r["label"]))
                        + ui.row("Due", escape(ui.date_only(r["due_date"])))
                        + (ui.row("When", escape(_due_words(r))) if _due_words(r) else "")
                        + (f'<div class="note-box">{escape(r["note"])}</div>' if r.get("note") else ""))
        ui.html(f'<div class="lock-line">{ui.icon("lock", theme.MUTED, 16)}<span>{escape(SUMMARY_ONLY)}</span></div>')


def render_review(conn, user) -> None:
    message = _apply_intent(conn, user)
    try:
        a = SS.lender_application(conn, user, st.session_state.get("review_id"))
    except auth.AccessDenied as e:
        ui.not_available(user, str(e))
        return
    back = st.session_state.get("review_from") if st.session_state.get("review_from") in DEFAULT_FILTER else "lender"
    ui.page_header(user, "Review application", f"{a['ref']} · {user.get('org_name') or ''}",
                   actions=(("Back to queue", "back_queue", back, "secondary"),))
    left, right = ui.two_columns("review", "side")
    with left:
        _score_card(a)
        _application_card(a)
        _health_tiles(a)
        _reasons_card(a)
    with right:
        _decision_card(a, message)


# ------------------------------------------------------------------ profile
def render_profile(conn, user) -> None:
    """The account details (organisation, email), change password and sign out (the same page as the admin's)."""
    from app.pages import profile
    profile.render_account(conn, user)
