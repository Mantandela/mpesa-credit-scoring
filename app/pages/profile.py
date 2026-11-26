"""Profile: who is signed in, Security (change password), Preferences (each toggle is stored as soon as it is
switched; delete saved results), the privacy line and a danger "Sign out" pill.

render_account() is the same page for lenders and admins: the identity card, Security and Sign out."""
from html import escape

import streamlit as st

from app import auth, components as ui, db, service, theme

FLAGS = (("email_notifications", "Application updates"), ("share_with_lenders", "Share score with lenders"),
         ("save_results", "Save my score results"))
PRIVACY = "Your statement is read once and never stored. Lenders only see the score summary you choose to share."


def _save_flag(user_id, flag):
    """Toggle callback. Callbacks run at the start of the next run, so they open their own connection."""
    conn = db.connect()
    try:
        service.update_profile_flags(conn, user_id, **{flag: st.session_state[f"flag_{flag}"]})
    finally:
        conn.close()


def _confirm(value: bool):
    st.session_state["confirm_delete_step"] = value


def identity_card(user: dict, name: str | None = None) -> None:
    with st.container(key="card_identity"):
        ui.html(f'<div class="profile-id"><div class="avatar-lg" aria-hidden="true">{escape(ui.initials(user["name"]))}'
                f'</div><div><div class="section">{escape(name or user["name"])}</div>'
                f'<div class="muted">{escape(user["email"])}</div><div class="cap" style="margin-top:6px">'
                f'{escape(ui.account_label(user))}</div></div></div>')


def security_card(conn, user: dict) -> None:
    """Change password (every role)."""
    with st.container(key="card_security"):
        ui.html(ui.cap("Security"))
        with st.expander("Change password", key="change_password"):
            cur = st.text_input("Current password", type="password", key="pw_current", autocomplete="current-password")
            new = st.text_input("New password", type="password", key="pw_new", autocomplete="new-password")
            conf = st.text_input("Confirm new password", type="password", key="pw_confirm", autocomplete="new-password")
            if st.button("Save password", key="pw_save", width="stretch"):
                try:
                    service.change_password(conn, user, cur, new, conf)
                except auth.AuthError as e:
                    ui.alert(str(e))
                else:
                    ui.muted("Password changed.")


def sign_out_button() -> None:
    with st.container(key="card_signout"):
        st.button("Sign out", key="sign_out", on_click=ui.sign_out, width="stretch")


def render(conn, user) -> None:
    ui.page_header(user, "Profile", "Your account")
    identity_card(user)
    security_card(conn, user)
    with st.container(key="card_account"):
        ui.html(ui.cap("Preferences"))
        for flag, label in FLAGS:
            st.toggle(label, value=bool(user[flag]), key=f"flag_{flag}", on_change=_save_flag, args=(user["id"], flag))
        if not st.session_state.get("confirm_delete_step"):
            st.button("Delete saved results", key="delete_results", on_click=_confirm, args=(True,), width="stretch")
        else:
            ui.muted("Delete all saved score results? Applications already sent are kept.")
            with st.container(horizontal=True, key="confirm_row"):
                if st.button("Delete", key="confirm_delete", width="stretch"):
                    n = service.delete_saved_results(conn, user)
                    st.session_state.pop("result", None)
                    _confirm(False)
                    st.session_state["deleted_n"] = n
                    st.rerun()
                st.button("Cancel", key="cancel_delete", on_click=_confirm, args=(False,), width="stretch")
        if "deleted_n" in st.session_state:
            ui.muted(f"Deleted {st.session_state.pop('deleted_n')} saved results.")
    ui.html(f'<div class="lock-line">{ui.icon("lock", theme.MUTED, 16)}<span>{escape(PRIVACY)}</span></div>')
    sign_out_button()


def render_account(conn, user) -> None:
    """Lender and admin profile: the identity (a lender's organisation), Security and Sign out."""
    ui.page_header(user, "Profile", "Your account")
    identity_card(user, user.get("org_name") if user.get("role") == "lender" else None)
    security_card(conn, user)
    sign_out_button()
