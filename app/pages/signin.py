"""Sign in (all roles)."""
import streamlit as st

from app import auth, components as ui, service

HOME_FOR = {"vendor": "home", "lender": "lender", "admin": "admin"}


def render(conn, user=None) -> None:
    ui.auth_header("Welcome back", "Sign in to your account")
    with st.container(key="card_signin"):
        email = st.text_input("Email", key="signin_email", autocomplete="email")
        password = st.text_input("Password", type="password", key="signin_password", autocomplete="current-password")
        ui.html('<div class="muted" style="text-align:right"><a href="#" style="color:#5B3FC4">Forgot password?</a></div>')
        if st.button("Sign in", type="primary", key="signin_submit", width="stretch"):
            try:
                u = service.authenticate(conn, email, password)
            except auth.AuthError as e:
                ui.alert(str(e))
            else:
                st.session_state.pop("signin_password", None)
                ui.go(HOME_FOR[u["role"]], user_id=u["id"])
                st.rerun()
    st.button("New vendor? Create an account", key="to_signup", type="tertiary", on_click=ui.go, args=("signup",),
              width="stretch")
