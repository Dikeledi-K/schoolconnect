"""Staff login for the Streamlit pages.

Every staff page starts with:

    staff = auth.require_login()                       # any logged-in staff member
    staff = auth.require_login(roles=SENIOR_ROLES)     # e.g. principal + deputy only

If nobody is logged in, the page shows a login form and stops. The token from the API is kept
in st.session_state (this browser tab only; it disappears when the session ends) and
api_client sends it with every request. The API checks the role again on every call, so
hiding a page here is a convenience, not the security.
"""

from __future__ import annotations

import streamlit as st

import api_client as api

SENIOR_ROLES = ("deputy_principal", "principal")
ROLE_NAMES = {"admin_clerk": "Admin Clerk", "finance_clerk": "Finance Clerk", "class_teacher": "Class Teacher",
              "deputy_principal": "Deputy Principal", "it_support": "IT Support", "principal": "Principal"}


def current_staff() -> dict | None:
    return st.session_state.get("staff") if api.current_token() else None


def _login_form() -> None:
    st.subheader("🔐 Staff login")
    st.caption("Parents do not need to log in: use **Send a message** in the menu.")
    with st.form("login"):
        email = st.text_input("Work email", autocomplete="username")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Log in", type="primary")
    if submitted:
        if not email or not password:
            st.error("Please enter your email and password.")
            return
        try:
            result = api.login(email.strip(), password)
        except api.ApiError as err:
            st.error(str(err))
            return
        st.session_state[api.TOKEN_KEY] = result["token"]
        st.session_state["staff"] = result["staff"]
        st.rerun()


def sidebar() -> None:
    """Who is logged in, and a logout button (shown on every page once logged in)."""
    staff = current_staff()
    if not staff:
        return
    with st.sidebar:
        st.markdown(f"**👋 {staff['name']}**  \n{ROLE_NAMES.get(staff['role'], staff['role'])}")
        if st.button("Log out", key="logout", width="stretch"):
            api.logout()
            st.rerun()


def require_login(roles: tuple[str, ...] | None = None) -> dict:
    """Return the logged-in staff member, or show the login form and stop the page."""
    staff = current_staff()
    if not staff:
        _login_form()
        st.stop()
    sidebar()
    if roles and staff["role"] not in roles:
        allowed = " or ".join(ROLE_NAMES[r] for r in roles)
        st.warning(f"🔒 This page is for the {allowed} only. Use **My work** or the **Staff inbox** instead.")
        st.stop()
    return staff
