import streamlit as st
import pandas as pd

import dbes_ats_db as db
import auth
import utils

st.set_page_config(page_title="Audit Log", page_icon="🧾", layout="wide")
import pwa
pwa.inject_pwa()

auth.require_admin()
auth.logout_button()

st.title("🧾 Audit Log")
st.caption("Who changed what, and when — most recent 500 entries.")

records = db.list_audit_log(limit=500)

if not records:
    st.info("No activity recorded yet.")
    st.stop()

df = pd.DataFrame([dict(r) for r in records])

col1, col2 = st.columns(2)
with col1:
    action_filter = st.multiselect("Filter by action", sorted(df["action"].unique()))
with col2:
    user_filter = st.multiselect("Filter by username", sorted(df["username"].dropna().unique()))

filtered = df.copy()
if action_filter:
    filtered = filtered[filtered["action"].isin(action_filter)]
if user_filter:
    filtered = filtered[filtered["username"].isin(user_filter)]

show_cols = ["timestamp", "username", "role", "action", "entity_type", "entity_id", "details"]
st.dataframe(
    filtered[show_cols].rename(columns={
        "timestamp": "Timestamp", "username": "User", "role": "Role",
        "action": "Action", "entity_type": "Entity", "entity_id": "Entity ID", "details": "Details",
    }),
    use_container_width=True, hide_index=True,
)

st.download_button(
    "⬇️ Export audit log to CSV",
    data=utils.to_csv_bytes(filtered[show_cols]),
    file_name="dbes_ats_audit_log.csv",
    mime="text/csv",
)
