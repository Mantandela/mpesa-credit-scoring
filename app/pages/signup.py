"""Sign up (vendors only; lender and admin accounts come from scripts/create_demo_users.py)."""
import streamlit as st

from app import auth, components as ui, service


def render(conn, user=None) -> None:
    ui.auth_header("Create account", "For vendors")
    with st.container(key="card_signup"):
        name = st.text_input("Full name", key="signup_name", autocomplete="name")
        email = st.text_input("Email", key="signup_email", autocomplete="email")
        password = st.text_input("Password", type="password", key="signup_password", autocomplete="new-password",
                                 help=f"At least {auth.MIN_PASSWORD_LENGTH} characters")
        confirm = st.text_input("Confirm password", type="password", key="signup_confirm", autocomplete="new-password")
        if st.button("Create account", type="primary", key="signup_submit", width="stretch"):
            try:
                u = service.register_vendor(conn, name, email, password, confirm)
            except auth.AuthError as e:
                ui.alert(str(e))
            else:
                for k in ("signup_password", "signup_confirm"):
                    st.session_state.pop(k, None)
                ui.go("home", user_id=u["id"])
                st.rerun()
    st.button("Already have an account? Sign in", key="to_signin", type="tertiary", on_click=ui.go, args=("signin",),
              width="stretch")
