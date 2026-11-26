"""Lender screens: Queue and Decided (one table, different default filter), Review application, Profile.

Every screen reads through app/staff_service.py, which checks the lender role and the organisation (applications
addressed to this lender account only) on the server side. A lender sees the snapshot the vendor shared and the vendor's
name, never the statement or the vendor's other checks. Lenders only approve or decline; the decision is final.

Laptop: the applications table (one row per application, the reference opens the review). Phone: small cards.
Review: two columns on a laptop (the Decision card on the right), stacked on a phone with the Decision card last.
"""
from html import escape

import streamlit as st

from app import auth, components as ui, service, staff_service as SS, theme

QUEUE_FILTERS = ("pending", "all")                                   # Queue: Pending N / All N
DECIDED_FILTERS = ("decided", "approved", "declined")                # Decided: All decided / Approved / Declined
FILTERS_FOR = {"lender": QUEUE_FILTERS, "lender_decided": DECIDED_FILTERS}
FILTER_LABEL = {"pending": "Pending", "approved": "Approved", "declined": "Declined", "all": "All",
                "decided": "All decided"}
DEFAULT_FILTER = {"lender": "pending", "lender_decided": "decided"}
CAP_FOR = {"lender": "Queue", "lender_decided": "Decided"}
QCOLS = ("Vendor", "Request", "Score", "Risk", "Estimated limit", "Status")
SUMMARY_ONLY = "You see this summary only. The statement is never shared. Decisions are final."
NOTE_LABEL = "Note to the vendor (optional)"
INTENT = "lender_decision"                    # (application id, "approved" | "declined") set by the two buttons


def _in(status: str, f: str) -> bool:
    return f == "all" or status == f or (f == "decided" and status in ("approved", "declined"))


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


def _cells(a: dict) -> str:
    c = (f'<span class="c">{_vendor(a)}</span><span class="c">{escape(_request(a))}</span>'
         f'<span class="c">{a["score"]}</span><span class="c">{_risk(a)}</span>'
         f'<span class="c">{_limit_html(a["eligibility"])}</span><span class="c">{_status(a)}</span>')
    return f'<div class="tcells qgrid">{c}</div>'


def _open(page: str, app_id: int) -> None:
    ui.go("lender_review", review_id=app_id, review_from=page)


def _table(apps: list, page: str) -> None:
    """Laptop: header and one row per application; the reference (indigo, bold) is the button that opens the review."""
    with st.container(key="qtable"):
        head = "".join(f"<span>{escape(h)}</span>" for h in QCOLS)
        ui.html(f'<div class="trow thead"><span class="tref">Reference</span><div class="tcells qgrid">{head}</div></div>')
        for a in apps:
            with st.container(horizontal=True, key=f"qrow_{a['id']}"):
                st.button(a["ref"], key=f"open_{a['id']}", type="tertiary", on_click=_open, args=(page, a["id"]),
                          help=f"Review {a['ref']}")
                ui.html(_cells(a), width="stretch")


def _list(apps: list, page: str) -> None:
    """Phone: one small card per application (reference, status, vendor, the details) with a Review button."""
    with st.container(key="qlist"):
        for a in apps:
            with st.container(key=f"qcard_{a['id']}"):
                ui.html(f'<div class="qc-head"><span class="qc-ref">{escape(a["ref"])}</span>{_status(a)}</div>'
                        f'<div class="qc-who">{_vendor(a)}</div>'
                        + ui.row("Request", escape(_request(a))) + ui.row("Score", f"{a['score']} / 850")
                        + ui.row("Risk", _risk(a)) + ui.row("Estimated limit", _limit_html(a["eligibility"]))
                        + ui.row("Submitted", escape(ui.short_date(a["created_at"]))))
                st.button("Review application", key=f"popen_{a['id']}", on_click=_open, args=(page, a["id"]),
                          width="stretch")


def render_queue(conn, user, page: str = "lender") -> None:
    apps = SS.lender_applications(conn, user)                       # the one query of the page
    org = user.get("org_name") or user.get("name") or ""
    ui.page_header(user, "Applications", f"{org} · {CAP_FOR[page]}")
    filters = FILTERS_FOR[page]
    groups = {f: [a for a in apps if _in(a["status"], f)] for f in filters}
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
