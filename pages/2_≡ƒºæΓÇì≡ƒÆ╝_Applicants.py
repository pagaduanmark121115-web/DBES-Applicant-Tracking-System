import streamlit as st
import pandas as pd

import dbes_ats_db as db
import auth
import utils

st.set_page_config(page_title="Applicants", page_icon="🧑‍💼", layout="wide")
import pwa
pwa.inject_pwa()

auth.require_login()
auth.logout_button()

st.title("🧑‍💼 Applicants")

school_id, vicariate_id = auth.current_scope()
is_admin = st.session_state["role"] == "admin"
current_user = st.session_state["username"]

tab_list, tab_add = st.tabs(["View / Edit Applicants", "➕ Add New Applicant"])

# ============================================================
# TAB 1 — VIEW / EDIT
# ============================================================
with tab_list:
    if school_id:
        applicants = db.list_applicants(school_id=school_id)
    else:
        schools = db.list_schools()
        school_names = ["All Schools"] + [s["name"] for s in schools]
        chosen = st.selectbox("Filter by school", school_names)
        if chosen == "All Schools":
            applicants = db.list_applicants()
        else:
            match = next(s for s in schools if s["name"] == chosen)
            applicants = db.list_applicants(school_id=match["id"])

    if not applicants:
        st.info("No applicants found for this filter.")
    else:
        df = pd.DataFrame([dict(a) for a in applicants])
        df["full_name"] = df["last_name"] + ", " + df["first_name"]
        df["days_in_process"] = df["date_applied"].apply(utils.days_since)

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            search = st.text_input("🔎 Search by name or position")
        with col_f2:
            stage_filter = st.multiselect("Filter by stage", db.APPLICATION_STAGES)

        if search:
            mask = (
                df["full_name"].str.contains(search, case=False, na=False)
                | df["position_applied_for"].str.contains(search, case=False, na=False)
            )
            df = df[mask]
        if stage_filter:
            df = df[df["current_stage"].isin(stage_filter)]

        display_cols = [
            "full_name", "school_name", "position_applied_for", "position_category",
            "current_stage", "date_applied", "days_in_process",
        ]
        st.dataframe(
            df[display_cols].rename(columns={
                "full_name": "Name", "school_name": "School", "position_applied_for": "Position",
                "position_category": "Category", "current_stage": "Stage",
                "date_applied": "Date Applied", "days_in_process": "Days Since Applied",
            }),
            use_container_width=True, hide_index=True,
        )

        st.download_button(
            "⬇️ Export this list to CSV",
            data=utils.to_csv_bytes(df.drop(columns=["full_name"])),
            file_name="dbes_applicants.csv",
            mime="text/csv",
        )

        st.divider()
        st.subheader("Applicant Detail / Edit")
        options = {f"{row['full_name']} — {row['school_name']} ({row['position_applied_for']})": row["id"]
                   for _, row in df.iterrows()}
        if options:
            selected_label = st.selectbox("Select an applicant to view or edit", list(options.keys()))
            app_id = options[selected_label]
            applicant = db.get_applicant(app_id)

            colA, colB = st.columns(2)
            with colA:
                st.metric("Current Stage", applicant["current_stage"])
            with colB:
                st.metric("Days Since Applied", utils.days_since(applicant["date_applied"]))

            with st.expander("✏️ Edit this applicant's record", expanded=False):
                schools_all = db.list_schools()
                school_names_all = [s["name"] for s in schools_all]
                current_school_idx = (
                    school_names_all.index(applicant["school_name"])
                    if applicant["school_name"] in school_names_all else 0
                )

                with st.form(f"edit_form_{app_id}"):
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        first_name = st.text_input("First name", value=applicant["first_name"])
                        last_name = st.text_input("Last name", value=applicant["last_name"])
                        middle_name = st.text_input("Middle name", value=applicant["middle_name"] or "")
                    with c2:
                        position_applied_for = st.text_input(
                            "Position applied for", value=applicant["position_applied_for"]
                        )
                        position_category = st.selectbox(
                            "Position category", db.POSITION_CATEGORIES,
                            index=db.POSITION_CATEGORIES.index(applicant["position_category"]),
                        )
                        if is_admin:
                            school_choice = st.selectbox("School", school_names_all, index=current_school_idx)
                        else:
                            st.text_input("School", value=applicant["school_name"], disabled=True)
                            school_choice = applicant["school_name"]
                    with c3:
                        contact_number = st.text_input("Contact number", value=applicant["contact_number"] or "")
                        email = st.text_input("Email", value=applicant["email"] or "")
                        source = st.text_input("Source (e.g. Referral, Walk-in, Online)", value=applicant["source"] or "")

                    c4, c5 = st.columns(2)
                    with c4:
                        date_applied = st.date_input("Date applied", value=utils.parse_date(applicant["date_applied"]))
                    with c5:
                        current_stage = st.selectbox(
                            "Current stage", db.APPLICATION_STAGES,
                            index=db.APPLICATION_STAGES.index(applicant["current_stage"]),
                        )

                    st.markdown("**Stage dates** _(leave a date blank if the applicant hasn't reached it yet)_")
                    stage_date_values = {}
                    sd_cols = st.columns(3)
                    for i, (column, label) in enumerate(db.STAGE_DATE_FIELDS):
                        if column == "date_applied":
                            continue
                        with sd_cols[i % 3]:
                            stage_date_values[column] = st.date_input(
                                label, value=utils.parse_date(applicant[column]), key=f"edit_{column}_{app_id}"
                            )

                    notes = st.text_area("Notes", value=applicant["notes"] or "")
                    save = st.form_submit_button("💾 Save changes")

                if save:
                    school_match = next(s for s in schools_all if s["name"] == school_choice)
                    update_data = {
                        "school_id": school_match["id"],
                        "first_name": first_name,
                        "middle_name": middle_name,
                        "last_name": last_name,
                        "contact_number": contact_number,
                        "email": email,
                        "position_applied_for": position_applied_for,
                        "position_category": position_category,
                        "source": source,
                        "date_applied": date_applied.isoformat(),
                        "current_stage": current_stage,
                        "notes": notes,
                    }
                    for column, value in stage_date_values.items():
                        update_data[column] = value.isoformat() if value else None
                    db.update_applicant(app_id, update_data, updated_by=current_user)
                    st.success("Record updated.")
                    st.rerun()

            with st.expander("📅 Stage Dates", expanded=False):
                sd_view_cols = st.columns(2)
                for i, (column, label) in enumerate(db.STAGE_DATE_FIELDS):
                    value = applicant[column] if column in applicant.keys() else None
                    with sd_view_cols[i % 2]:
                        st.write(f"**{label}:** {value or '— not yet reached'}")

            with st.expander("📈 Stage History"):
                stage_hist = db.get_stage_history(app_id)
                for s in stage_hist:
                    st.write(f"- **{s['stage']}** — {s['date_entered']}" + (f" _({s['remarks']})_" if s["remarks"] else ""))

            if is_admin:
                with st.expander("🗑️ Delete this record"):
                    st.warning("This permanently deletes the applicant and their stage history.")
                    if st.button("Confirm delete", key=f"del_{app_id}"):
                        db.delete_applicant(app_id, deleted_by=current_user)
                        st.success("Applicant deleted.")
                        st.rerun()

# ============================================================
# TAB 2 — ADD NEW
# ============================================================
with tab_add:
    schools_all = db.list_schools()
    if not schools_all:
        st.warning("Add at least one school from the main Dashboard page first.")
    else:
        school_names_all = [s["name"] for s in schools_all]

        with st.form("add_applicant_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                first_name = st.text_input("First name*")
                last_name = st.text_input("Last name*")
                middle_name = st.text_input("Middle name")
            with c2:
                position_applied_for = st.text_input("Position applied for*")
                position_category = st.selectbox("Position category*", db.POSITION_CATEGORIES)
                if is_admin:
                    school_choice = st.selectbox("School*", school_names_all)
                else:
                    school = db.get_school(school_id)
                    st.text_input("School", value=school["name"], disabled=True)
                    school_choice = school["name"]
            with c3:
                contact_number = st.text_input("Contact number")
                email = st.text_input("Email")
                source = st.text_input("Source (e.g. Referral, Walk-in, Online)")

            c4, c5 = st.columns(2)
            with c4:
                date_applied = st.date_input("Date applied*")
            with c5:
                current_stage = st.selectbox("Starting stage*", db.APPLICATION_STAGES, index=0)

            st.markdown("**Stage dates** _(optional — fill in any that already happened, leave the rest blank)_")
            new_stage_date_values = {}
            sd_cols = st.columns(3)
            for i, (column, label) in enumerate(db.STAGE_DATE_FIELDS):
                if column == "date_applied":
                    continue
                with sd_cols[i % 3]:
                    new_stage_date_values[column] = st.date_input(label, value=None, key=f"add_{column}")

            notes = st.text_area("Notes")
            submitted = st.form_submit_button("➕ Add applicant")

        if submitted:
            if not (first_name and last_name and position_applied_for):
                st.error("First name, last name, and position applied for are required.")
            else:
                school_match = next(s for s in schools_all if s["name"] == school_choice)
                new_applicant_data = {
                    "school_id": school_match["id"],
                    "first_name": first_name,
                    "middle_name": middle_name or None,
                    "last_name": last_name,
                    "contact_number": contact_number or None,
                    "email": email or None,
                    "position_applied_for": position_applied_for,
                    "position_category": position_category,
                    "source": source or None,
                    "date_applied": date_applied.isoformat(),
                    "current_stage": current_stage,
                    "notes": notes or None,
                }
                for column, value in new_stage_date_values.items():
                    new_applicant_data[column] = value.isoformat() if value else None
                db.add_applicant(new_applicant_data, created_by=current_user)
                st.success(f"Added {first_name} {last_name}.")
