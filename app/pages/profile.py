"""Profile: who is signed in, the account settings (stored only) with "Save changes", change password, delete saved
results, the privacy line and sign out."""
from html import escape

import streamlit as st

from app import auth, components as ui, service, theme

FLAGS = (("share_with_lenders", "Share score with lenders"), ("save_results", "Save my score results"),
         ("email_notifications", "Email notifications"))
PRIVACY = "Your statement is read once and never stored. Lenders only see the score summary you choose to share."


def _confirm(value: bool):
    st.session_state["confirm_delete_step"] = value


def render(conn, user) -> None:
    ui.page_header(user, "Profile", "Your account")
    with st.container(key="card_identity"):
        ui.html(f'<div class="profile-id"><div class="avatar-lg" aria-hidden="true">{escape(ui.initials(user["name"]))}'
                f'</div><div><div class="section">{escape(user["name"])}</div>'
                f'<div class="muted">{escape(user["email"])}</div></div></div>')

    with st.container(key="card_account"):
        ui.section("Account details")
        with st.form("profile_form", border=False):
            values = {flag: st.toggle(label, value=bool(user[flag]), key=f"flag_{flag}") for flag, label in FLAGS}
            saved = st.form_submit_button("Save changes", type="primary", key="profile_save", width="stretch")
        if saved:
            service.update_profile_flags(conn, user["id"], **values)
            ui.muted("Changes saved.")
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
    with st.container(key="card_signout"):
        st.button("Sign out", key="sign_out", type="tertiary", on_click=ui.sign_out, width="stretch")
