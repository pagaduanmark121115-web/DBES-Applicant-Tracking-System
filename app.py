"""
app.py
Entry point for the DBES Applicant Tracking Dashboard.
Run with:  streamlit run app.py
"""

import streamlit as st
import dbes_ats_db as db
import auth

st.set_page_config(
    page_title="DBES Applicant Tracking Dashboard",
    page_icon="🧑‍💼",
    layout="wide",
)

import pwa
pwa.inject_pwa()

db.init_db()

if not auth.login_form():
    st.stop()

auth.logout_button()

st.title("🧑‍💼 DBES Applicant Tracking Dashboard")
st.markdown("### Diocese of Bayombong Education System")
st.markdown(
    "Use the sidebar to navigate: **Dashboard** for pipeline stats, "
    "**Applicants** to add/edit/view applicant records, "
    "**My Account** to change your own password, and "
    "**Manage Users** / **Audit Log** (admin only)."
)

# ---- School setup: admins can add/verify schools at any time ----
schools = db.list_schools()

if st.session_state["role"] == "admin":
    if len(schools) == 0:
        st.info(
            "No schools have been set up yet. Fill out the form below to add each "
            "of the DBES schools, selecting the correct vicariate (Northern, "
            "Southern, or Quirino) for each one."
        )

    with st.expander("➕ Add / verify a school", expanded=(len(schools) == 0)):
        vicariates = db.list_vicariates()
        vic_options = {v["name"]: v["id"] for v in vicariates}

        with st.form("add_school_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                school_name = st.text_input("School name")
            with col2:
                vicariate_name = st.selectbox("Vicariate", list(vic_options.keys()))
            submitted = st.form_submit_button("Add school")

        if submitted:
            if not school_name.strip():
                st.error("Please enter a school name.")
            else:
                try:
                    db.add_school(school_name.strip(), vic_options[vicariate_name],
                                   created_by=st.session_state["username"])
                    st.success(f"Added {school_name} under {vicariate_name} vicariate.")
                    st.rerun()
                except db.DuplicateSchoolError as e:
                    st.error(str(e))

st.divider()
st.subheader("Schools on record")

vicariates = db.list_vicariates()
cols = st.columns(3)
for col, vic in zip(cols, vicariates):
    with col:
        st.markdown(f"**{vic['name']} Vicariate**")
        vic_schools = db.list_schools(vic["id"])
        if vic_schools:
            for s in vic_schools:
                st.write(f"- {s['name']}")
        else:
            st.caption("No schools added yet.")

st.divider()
st.caption(
    "Default admin login is username `admin` / password `changeme123` — "
    "change this immediately from the My Account page."
)
