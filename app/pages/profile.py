"""Profile: settings (stored only), change password, delete saved results, sign out."""
from html import escape

import streamlit as st

from app import auth, components as ui, db, service


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def _save_flag(user_id, flag):
    """Toggle callback. Callbacks run at the start of the next run, so they open their own connection."""
    conn = db.connect()
    try:
        service.update_profile_flags(conn, user_id, **{flag: st.session_state[f"flag_{flag}"]})
    finally:
        conn.close()


def _confirm(value: bool):
    st.session_state["confirm_delete_step"] = value


def render(conn, user) -> None:
    ui.html(f'<div class="avatar" aria-hidden="true">{escape(_initials(user["name"]))}</div>'
            f'<div class="center"><div class="title">{escape(user["name"])}</div>'
            f'<div class="muted">{escape(user["email"])}</div></div>')

    with st.container(key="card_settings"):
        for flag, label in (("share_with_lenders", "Share score with lenders"), ("save_results", "Save my score results"),
                            ("email_notifications", "Email notifications")):
            st.toggle(label, value=bool(user[flag]), key=f"flag_{flag}", on_change=_save_flag, args=(user["id"], flag))

    with st.container(key="card_account"):
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
            st.button("Delete saved results", key="delete_results", type="tertiary", on_click=_confirm, args=(True,),
                      width="stretch")
        else:
            ui.muted("Delete all saved score results? Applications already sent are kept.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Delete", key="confirm_delete", width="stretch"):
                    n = service.delete_saved_results(conn, user)
                    st.session_state.pop("result", None)
                    _confirm(False)
                    st.session_state["deleted_n"] = n
                    st.rerun()
            with c2:
                st.button("Cancel", key="cancel_delete", on_click=_confirm, args=(False,), width="stretch")
        if "deleted_n" in st.session_state:
            ui.muted(f"Deleted {st.session_state.pop('deleted_n')} saved results.")
        st.button("Sign out", key="sign_out", type="tertiary", on_click=ui.sign_out, width="stretch")
