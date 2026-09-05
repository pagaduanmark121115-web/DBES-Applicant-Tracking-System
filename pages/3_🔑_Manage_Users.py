import streamlit as st

import dbes_ats_db as db
import auth

st.set_page_config(page_title="Manage Users", page_icon="🔑", layout="wide")
import pwa
pwa.inject_pwa()

auth.require_admin()
auth.logout_button()

st.title("🔑 Manage Users")
st.caption("Create and manage login accounts for admins and school-level users.")

current_admin = st.session_state["username"]

schools = db.list_schools()
school_names = [s["name"] for s in schools]

tab_list, tab_add = st.tabs(["Existing Users", "➕ Add New User"])

with tab_list:
    users = db.list_users()
    if not users:
        st.info("No users yet.")
    else:
        for u in users:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2, 2, 2, 1])
                c1.markdown(f"**{u['full_name']}**  \n@{u['username']}")
                c2.write(f"Role: {db.role_label(u['role'])}")
                c3.write(f"School: {u['school_name'] or '— (all schools)'}")
                status = "🟢 Active" if u["is_active"] else "🔴 Disabled"
                c4.write(status)

                with st.expander("Manage this user"):
                    new_pw = st.text_input(
                        "Set new password", type="password", key=f"pw_{u['id']}"
                    )
                    colx, coly = st.columns(2)
                    with colx:
                        if st.button("Update password", key=f"upd_{u['id']}") and new_pw:
                            db.reset_user_password(u["id"], new_pw, changed_by=current_admin)
                            st.success("Password updated.")
                    with coly:
                        toggle_label = "Disable user" if u["is_active"] else "Enable user"
                        if st.button(toggle_label, key=f"tgl_{u['id']}"):
                            db.set_user_active(u["id"], not u["is_active"], changed_by=current_admin)
                            st.rerun()

with tab_add:
    if not school_names:
        st.warning("Add schools from the main Dashboard page before creating school-level logins.")

    # Outside the form so switching roles immediately shows/hides the
    # school-assignment field below (widgets inside a form only update on
    # submit) — same pattern used for Position category on the Applicants page.
    role_choice = st.selectbox(
        "Role*", db.ROLES, format_func=db.role_label, key="add_user_role"
    )
    role_needs_school = role_choice in ("school", "school_delegate")

    with st.form("add_user_form", clear_on_submit=True):
        full_name = st.text_input("Full name*")
        username = st.text_input("Username*")
        password = st.text_input("Temporary password*", type="password")
        st.text_input("Role", value=db.role_label(role_choice), disabled=True)
        school_choice = None
        if role_needs_school:
            school_choice = st.selectbox("Assign to school*", school_names) if school_names else None
        submitted = st.form_submit_button("➕ Create user")

    if submitted:
        if not (full_name and username and password):
            st.error("Full name, username, and password are required.")
        elif len(password) < 6:
            st.error("Password must be at least 6 characters.")
        elif role_needs_school and not school_choice:
            st.error("Please assign a school for school-level accounts.")
        elif db.get_user_by_username(username.strip()):
            st.error("That username already exists.")
        else:
            school_id = None
            if role_needs_school:
                match = next(s for s in schools if s["name"] == school_choice)
                school_id = match["id"]
            try:
                db.create_user(username.strip(), password, full_name, role_choice, school_id, created_by=current_admin)
                st.success(f"Created {db.role_label(role_choice)} account for {full_name}.")
            except db.DuplicateUsernameError as e:
                st.error(str(e))
