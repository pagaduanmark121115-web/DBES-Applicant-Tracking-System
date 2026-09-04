import streamlit as st

import dbes_ats_db as db
import auth

st.set_page_config(page_title="My Account", page_icon="🔒", layout="wide")
import pwa
pwa.inject_pwa()

auth.require_login()
auth.logout_button()

st.title("🔒 My Account")

st.markdown(f"**Username:** {st.session_state['username']}")
st.markdown(f"**Full name:** {st.session_state['full_name']}")
st.markdown(f"**Role:** {st.session_state['role']}")
if st.session_state.get("school_id"):
    school = db.get_school(st.session_state["school_id"])
    st.markdown(f"**Assigned school:** {school['name']} ({school['vicariate_name']} Vicariate)")

st.divider()
st.subheader("Change my password")

with st.form("change_password_form", clear_on_submit=True):
    current_password = st.text_input("Current password", type="password")
    new_password = st.text_input("New password", type="password")
    confirm_password = st.text_input("Confirm new password", type="password")
    submitted = st.form_submit_button("Update password")

if submitted:
    if not (current_password and new_password and confirm_password):
        st.error("Please fill in all fields.")
    elif new_password != confirm_password:
        st.error("New password and confirmation don't match.")
    else:
        ok, message = db.change_own_password(
            st.session_state["user_id"], current_password, new_password
        )
        if ok:
            st.success(message)
        else:
            st.error(message)
