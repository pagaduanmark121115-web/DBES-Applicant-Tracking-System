"""
auth.py
Login form and session-state helpers for role-based access
(HR Officer vs. school-scoped users — School Principal and Delegated by
School Principal). Login attempts are recorded to the audit log.
"""

import streamlit as st
import dbes_ats_db as db


def login_form():
    if st.session_state.get("authenticated"):
        return True

    st.title("🔐 DBES Applicant Tracking Dashboard")
    st.caption("Diocese of Bayombong Education System")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        clean_username = username.strip()
        user = db.get_user_by_username(clean_username)
        if user and db.verify_password(password, user["password_hash"]):
            st.session_state["authenticated"] = True
            st.session_state["user_id"] = user["id"]
            st.session_state["username"] = user["username"]
            st.session_state["full_name"] = user["full_name"]
            st.session_state["role"] = user["role"]
            st.session_state["school_id"] = user["school_id"]
            db.log_action(user["username"], user["role"], "LOGIN_SUCCESS")
            st.rerun()
        else:
            db.log_action(clean_username or "(blank)", None, "LOGIN_FAILED")
            st.error("Invalid username or password.")

    return False


def require_login():
    # Make sure every table (including newly added ones) exists even if this
    # page is opened directly instead of through the main page.
    db.init_db()
    if not st.session_state.get("authenticated"):
        st.warning("Please log in from the main page first.")
        st.stop()


def require_admin():
    require_login()
    if st.session_state.get("role") != "admin":
        st.error("This page is restricted to administrators.")
        st.stop()


def logout_button():
    with st.sidebar:
        st.markdown(f"**Logged in as:** {st.session_state.get('full_name')}")
        st.caption(f"Role: {db.role_label(st.session_state.get('role'))}")
        if st.button("Log out"):
            db.log_action(st.session_state.get("username"), st.session_state.get("role"), "LOGOUT")
            for key in ["authenticated", "user_id", "username", "full_name", "role", "school_id"]:
                st.session_state.pop(key, None)
            st.rerun()


def current_scope():
    """HR Officer (role 'admin') -> (None, None), no restriction.
    Any school-scoped role (School Principal or Delegated by School
    Principal) -> (school_id, None)."""
    if st.session_state.get("role") == "admin":
        return None, None
    return st.session_state.get("school_id"), None