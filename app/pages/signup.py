"""Sign up (vendors only; lender and admin accounts come from scripts/create_demo_users.py). A form, so Enter submits.

A validation message is shown under the field it is about (FIELD_FOR, matched on the message text from app/auth.py);
any other message is shown under the button.
"""
import streamlit as st

from app import auth, components as ui, service

FIELD_FOR = {
    "Enter your full name.": "name",
    "Enter a valid email address.": "email",
    auth.EMAIL_TAKEN: "email",
    f"Use at least {auth.MIN_PASSWORD_LENGTH} characters for the password.": "password",
    "The passwords do not match.": "confirm",
}


def render(conn, user=None) -> None:
    ui.auth_band()
    with st.container(key="auth_card"):
        ui.auth_title("Create your account", "Takes less than a minute")
        with st.form("signup_form", border=False):
            slot = {}
            name = st.text_input("Full name", key="signup_name", autocomplete="name")
            slot["name"] = st.empty()
            email = st.text_input("Email", key="signup_email", autocomplete="email", placeholder="you@example.com")
            slot["email"] = st.empty()
            password = st.text_input("Password", type="password", key="signup_password", autocomplete="new-password",
                                     help=f"At least {auth.MIN_PASSWORD_LENGTH} characters")
            slot["password"] = st.empty()
            confirm = st.text_input("Confirm password", type="password", key="signup_confirm", autocomplete="new-password")
            slot["confirm"] = st.empty()
            submitted = st.form_submit_button("Create account", type="primary", key="signup_submit", width="stretch")
            if submitted:
                try:
                    u = service.register_vendor(conn, name, email, password, confirm)
                except auth.AuthError as e:
                    msg = str(e)
                    field = FIELD_FOR.get(msg)
                    ui.auth_error(msg, where=slot[field] if field else st)
                else:
                    for k in ("signup_password", "signup_confirm"):
                        st.session_state.pop(k, None)
                    ui.go("home", user_id=u["id"])
                    st.rerun()
        st.button("Already have an account? **Sign in**", key="to_signin", type="tertiary", on_click=ui.go,
                  args=("signin",), width="stretch")
    ui.auth_footer()
