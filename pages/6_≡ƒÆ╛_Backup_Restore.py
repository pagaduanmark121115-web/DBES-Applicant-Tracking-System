import streamlit as st
import os
from datetime import datetime

import dbes_ats_db as db
import auth

st.set_page_config(page_title="Backup & Restore", page_icon="💾", layout="wide")
import pwa
pwa.inject_pwa()

auth.require_admin()
auth.logout_button()

st.title("💾 Backup & Restore")
st.caption(
    "If this app is hosted on a free service like Streamlit Community Cloud, "
    "the database file is NOT guaranteed to survive every redeploy or a long "
    "period of inactivity. Download a backup regularly (e.g. weekly) and keep "
    "it somewhere safe, such as Google Drive."
)

st.divider()
st.subheader("Download a backup")

if os.path.exists(db.DB_PATH):
    size_kb = os.path.getsize(db.DB_PATH) / 1024
    modified = datetime.fromtimestamp(os.path.getmtime(db.DB_PATH)).strftime("%Y-%m-%d %H:%M")
    st.write(f"Current database: **{size_kb:.1f} KB**, last modified **{modified}**.")

    with open(db.DB_PATH, "rb") as f:
        st.download_button(
            "⬇️ Download database backup (.db)",
            data=f.read(),
            file_name=f"dbes_applicants_backup_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
            mime="application/octet-stream",
        )
    db.log_action(st.session_state["username"], "admin", "BACKUP_DOWNLOADED", "database", None,
                  "Admin downloaded a database backup")
else:
    st.warning("No database file found yet.")

st.divider()
st.subheader("Restore from a backup")
st.warning(
    "⚠️ Restoring will completely REPLACE all current data — every employee "
    "record, disciplinary action, and user login — with the contents of the "
    "uploaded file. This cannot be undone. Only do this if you're sure."
)

uploaded = st.file_uploader("Upload a .db backup file", type=["db"])
if uploaded is not None:
    confirm_text = st.text_input('Type RESTORE (in capitals) to confirm you understand this will overwrite all current data')
    if st.button("Restore this backup", type="primary", disabled=(confirm_text != "RESTORE")):
        with open(db.DB_PATH, "wb") as f:
            f.write(uploaded.getbuffer())
        db.log_action(st.session_state["username"], "admin", "RESTORE_PERFORMED", "database", None,
                      f"Admin restored database from uploaded file '{uploaded.name}'")
        st.success("Database restored. Please log out and log back in to make sure everything reloads correctly.")
