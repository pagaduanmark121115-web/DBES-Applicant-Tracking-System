import streamlit as st
import pandas as pd
import plotly.express as px

import dbes_ats_db as db
import auth
import utils

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")
import pwa
pwa.inject_pwa()

auth.require_login()
auth.logout_button()

st.title("📊 Applicant Pipeline Dashboard")

school_id, vicariate_id = auth.current_scope()

if school_id:
    school = db.get_school(school_id)
    st.markdown(f"Showing data for **{school['name']}** ({school['vicariate_name']} Vicariate)")
    applicants = db.list_applicants(school_id=school_id)
else:
    st.markdown("Showing data for **all schools** (Northern, Southern, Quirino)")
    applicants = db.list_applicants()

if not applicants:
    st.info("No applicant records yet. Add some from the Applicants page.")
    st.stop()

df = pd.DataFrame([dict(a) for a in applicants])
df["days_in_process"] = df["date_applied"].apply(utils.days_since)
df["full_name"] = df["last_name"] + ", " + df["first_name"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Applicants", len(df))
col2.metric("Hired", int((df["current_stage"] == "Hired").sum()))
col3.metric("Rejected", int((df["current_stage"] == "Rejected").sum()))
in_process = df[~df["current_stage"].isin(db.TERMINAL_STAGES)]
col4.metric("Still in Process", len(in_process))

st.download_button(
    "⬇️ Export this view to CSV",
    data=utils.to_csv_bytes(df.drop(columns=["full_name"])),
    file_name="dbes_applicants_export.csv",
    mime="text/csv",
)

st.divider()

c1, c2 = st.columns(2)
with c1:
    st.subheader("Applicants by Stage")
    stage_counts = df["current_stage"].value_counts().reindex(db.APPLICATION_STAGES).fillna(0).reset_index()
    stage_counts.columns = ["Stage", "Count"]
    fig = px.bar(stage_counts, x="Count", y="Stage", orientation="h")
    fig.update_layout(yaxis=dict(categoryorder="array", categoryarray=list(reversed(db.APPLICATION_STAGES))))
    st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("Teaching vs Non-Teaching Applicants")
    cat_counts = df["position_category"].value_counts().reset_index()
    cat_counts.columns = ["Category", "Count"]
    fig2 = px.pie(cat_counts, names="Category", values="Count", hole=0.4)
    st.plotly_chart(fig2, use_container_width=True)

if not school_id:
    st.subheader("Applicants per School")
    per_school = df["school_name"].value_counts().reset_index()
    per_school.columns = ["School", "Applicants"]
    fig3 = px.bar(per_school, x="School", y="Applicants")
    st.plotly_chart(fig3, use_container_width=True)

    st.subheader("Applicants per Vicariate")
    per_vic = df["vicariate_name"].value_counts().reset_index()
    per_vic.columns = ["Vicariate", "Applicants"]
    fig4 = px.bar(per_vic, x="Vicariate", y="Applicants")
    st.plotly_chart(fig4, use_container_width=True)

st.divider()
st.subheader("⏳ Longest-waiting applicants still in process")
if len(in_process):
    longest = in_process.sort_values("days_in_process", ascending=False).head(10)
    show_cols = ["full_name", "school_name", "position_applied_for", "current_stage", "days_in_process"]
    st.dataframe(
        longest[show_cols].rename(columns={
            "full_name": "Name", "school_name": "School", "position_applied_for": "Position",
            "current_stage": "Stage", "days_in_process": "Days Since Applied",
        }),
        use_container_width=True, hide_index=True,
    )
else:
    st.caption("Everyone has reached Hired or Rejected.")
