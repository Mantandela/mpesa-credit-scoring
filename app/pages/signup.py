"""Sign up as a vendor or a lender. A form, so Enter submits.

The account type comes ONLY from the "Sign up as" selector (two buttons, Vendor by default), and the value is checked
against SIGNUP_TYPES before anything is created: a vendor goes through service.register_vendor, a lender through
service.register_lender (with the organisation name). Neither takes a role parameter, nothing here reads a role from
the URL or from other session keys, and an admin account can never be created from this page (admins are added by an
admin, or by scripts/create_demo_users.py).

A validation message is shown under the field it is about (FIELD_FOR, matched on the message text from app/auth.py
and app/service.py); any other message is shown under the button.
"""
import streamlit as st

from app import auth, components as ui, service
from app.pages.signin import HOME_FOR

TYPE_KEY = "signup_type"
SIGNUP_TYPES = {"vendor": "Vendor", "lender": "Lender"}           # the only account types sign-up can create
CHOOSE_TYPE = "Choose Vendor or Lender."

FIELD_FOR = {
    "Enter your full name.": "name",
    "Enter a valid email address.": "email",
    auth.EMAIL_TAKEN: "email",
    service.ORG_MISSING: "org",
    service.ORG_LENGTH: "org",
    service.ORG_TAKEN: "org",
    f"Use at least {auth.MIN_PASSWORD_LENGTH} characters for the password.": "password",
    "The passwords do not match.": "confirm",
}


def render(conn, user=None) -> None:
    if st.session_state.get(TYPE_KEY, "vendor") not in SIGNUP_TYPES:      # a value not from the selector: drop it
        st.session_state.pop(TYPE_KEY, None)
    ui.auth_band()
    with st.container(key="auth_card"):
        ui.auth_title("Create your account", "Takes less than a minute")
        kind = st.segmented_control("Sign up as", tuple(SIGNUP_TYPES), format_func=SIGNUP_TYPES.get, default="vendor",
                                    required=True, key=TYPE_KEY, width="stretch")
        with st.form("signup_form", border=False):
            slot = {}
            name = st.text_input("Full name", key="signup_name", autocomplete="name")
            slot["name"] = st.empty()
            email = st.text_input("Email", key="signup_email", autocomplete="email", placeholder="you@example.com")
            slot["email"] = st.empty()
            if kind == "lender":
                org = st.text_input("Organisation name", key="signup_org", autocomplete="organization",
                                    max_chars=service.ORG_MAX)
                slot["org"] = st.empty()
            password = st.text_input("Password", type="password", key="signup_password", autocomplete="new-password",
                                     help=f"At least {auth.MIN_PASSWORD_LENGTH} characters")
            slot["password"] = st.empty()
            confirm = st.text_input("Confirm password", type="password", key="signup_confirm", autocomplete="new-password")
            slot["confirm"] = st.empty()
            submitted = st.form_submit_button("Create account", type="primary", key="signup_submit", width="stretch")
            if submitted:
                try:
                    if kind == "vendor":
                        u = service.register_vendor(conn, name, email, password, confirm)
                    elif kind == "lender":
                        u = service.register_lender(conn, name, email, org, password, confirm)
                    else:
                        raise auth.AuthError(CHOOSE_TYPE)
                except auth.AuthError as e:
                    msg = str(e)
                    field = FIELD_FOR.get(msg)
                    ui.auth_error(msg, where=slot[field] if field in slot else st)
                else:
                    for k in ("signup_password", "signup_confirm"):
                        st.session_state.pop(k, None)
                    ui.go(HOME_FOR[u["role"]], user_id=u["id"])
                    st.rerun()
        st.button("Already have an account? **Sign in**", key="to_signin", type="tertiary", on_click=ui.go,
                  args=("signin",), width="stretch")
    ui.auth_footer()
