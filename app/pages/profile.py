"""Profile: privacy and account settings (stored only), change password, delete saved results, sign out."""
from html import escape

import streamlit as st

from app import auth, components as ui, db, service


def _save_flag(user_id, flag):
    """Toggle callback. Callbacks run at the start of the next run, so they open their own connection."""
    conn = db.connect()
    try:
        service.update_profile_flags(conn, user_id, **{flag: st.session_state[f"flag_{flag}"]})
    finally:
        conn.close()


def _confirm(value: bool):
    st.session_state["confirm_delete_step"] = value


def _toggle(user, flag, label):
    st.toggle(label, value=bool(user[flag]), key=f"flag_{flag}", on_change=_save_flag, args=(user["id"], flag))


def render(conn, user) -> None:
    ui.top_bar(user, "Profile")
    ui.html(f'<div class="avatar-lg" aria-hidden="true">{escape(ui.initials(user["name"]))}</div>'
            f'<div class="center"><div class="section">{escape(user["name"])}</div>'
            f'<div class="caption">{escape(user["email"])}</div></div>')

    with st.container(key="card_privacy"):
        ui.section("Privacy")
        _toggle(user, "share_with_lenders", "Share score with lenders")
        _toggle(user, "save_results", "Save my score results")

    with st.container(key="card_account"):
        ui.section("Account")
        _toggle(user, "email_notifications", "Email notifications")
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

    if not st.session_state.get("confirm_delete_step"):
        st.button("Delete saved results", key="delete_results", on_click=_confirm, args=(True,), width="stretch")
    else:
        with st.container(key="card_confirm"):
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
    st.button("Sign out", key="sign_out", type="tertiary", on_click=ui.sign_out, width="stretch")
