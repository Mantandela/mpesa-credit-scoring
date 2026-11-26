"""Sign in (all roles). A form, so Enter in either field submits."""
import streamlit as st

from app import auth, components as ui, service

HOME_FOR = {"vendor": "home", "lender": "lender", "admin": "admin"}


def render(conn, user=None) -> None:
    ui.auth_band()
    with st.container(key="auth_card"):
        ui.auth_title("Welcome back", "Sign in to check your score")
        with st.form("signin_form", border=False):
            email = st.text_input("Email", key="signin_email", autocomplete="email", placeholder="you@example.com")
            password = st.text_input("Password", type="password", key="signin_password", autocomplete="current-password")
            submitted = st.form_submit_button("Sign in", type="primary", key="signin_submit", width="stretch")
            if submitted:
                try:
                    u = service.authenticate(conn, email, password)
                except auth.AuthError as e:
                    ui.auth_error(str(e))              # under the button: wrong password, unknown email, locked
                else:
                    st.session_state.pop("signin_password", None)
                    ui.go(HOME_FOR[u["role"]], user_id=u["id"])
                    st.rerun()
        ui.auth_note(ui.SIGNIN_ROLES)
        st.button("New to Nuru? **Create an account**", key="to_signup", type="tertiary", on_click=ui.go,
                  args=("signup",), width="stretch")
    ui.auth_footer()
