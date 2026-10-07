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


def _specialization_field(position_category, current_value, key):
    """Major dropdown for Teaching, free-text role for Non-Teaching.
    Both are stored in the same `specialization` column."""
    if position_category == "Teaching":
        options = db.TEACHING_MAJORS
        index = options.index(current_value) if current_value in options else 0
        return st.selectbox("Major*", options, index=index, key=key)
    return st.text_input(
        "Specialization / Role (Non-Teaching)*",
        value=current_value or "",
        key=key,
        placeholder="e.g. Bookkeeper, Utility, Security Guard",
    )


def _stage_detail_fields(applicant_or_none, key_prefix):
    """Renders Date / Person-in-charge / Notes for every stage in
    db.STAGE_EXTRA_FIELDS (Applied only gets PIC + Notes, since its date
    is a required top-level field rendered separately). Returns a dict
    of column_name -> raw widget value, ready to be normalized by the
    caller before saving."""
    values = {}
    for date_col, pic_col, notes_col, label in db.STAGE_EXTRA_FIELDS:
        st.markdown(f"**{label}**")
        existing_date = applicant_or_none[date_col] if applicant_or_none is not None else None
        existing_pic = applicant_or_none[pic_col] if applicant_or_none is not None else None
        existing_notes = applicant_or_none[notes_col] if applicant_or_none is not None else None

        if date_col == "date_applied":
            col_pic, col_notes = st.columns([1, 2])
            with col_pic:
                values[pic_col] = st.text_input(
                    "Person in charge", value=existing_pic or "", key=f"{key_prefix}_{pic_col}"
                )
            with col_notes:
                values[notes_col] = st.text_area(
                    "Notes", value=existing_notes or "", key=f"{key_prefix}_{notes_col}", height=68
                )
        else:
            col_date, col_pic, col_notes = st.columns([1, 1, 2])
            with col_date:
                values[date_col] = st.date_input(
                    "Date", value=utils.parse_date(existing_date), key=f"{key_prefix}_{date_col}"
                )
            with col_pic:
                values[pic_col] = st.text_input(
                    "Person in charge", value=existing_pic or "", key=f"{key_prefix}_{pic_col}"
                )
            with col_notes:
                values[notes_col] = st.text_area(
                    "Notes", value=existing_notes or "", key=f"{key_prefix}_{notes_col}", height=68
                )
        st.markdown("---")
    return values


def _normalize_stage_values(raw_values):
    """Turns widget output into DB-ready values: dates -> isoformat or
    None, text -> stripped string or None."""
    normalized = {}
    for column, value in raw_values.items():
        if column.startswith("date_"):
            normalized[column] = value.isoformat() if value else None
        else:
            value = (value or "").strip()
            normalized[column] = value or None
    return normalized


def _requirements_fields(current_statuses, key_prefix):
    """One row per requirement. Items marked 'if applicable' also offer a
    'Not applicable' choice. Returns {requirement_key: status}."""
    values = {}
    for key, label, can_be_na in db.REQUIREMENTS:
        options = [db.REQ_SUBMITTED, db.REQ_NOT_SUBMITTED]
        if can_be_na:
            options.append(db.REQ_NOT_APPLICABLE)
        current = (current_statuses or {}).get(key, db.REQ_NOT_SUBMITTED)
        index = options.index(current) if current in options else 1
        values[key] = st.radio(
            label, options, index=index, horizontal=True, key=f"{key_prefix}_req_{key}"
        )
    return values


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
        progress_map = db.requirements_progress_map()
        df["requirements_submitted"] = df["id"].map(progress_map)

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
            "specialization", "current_stage", "date_applied", "days_in_process",
            "requirements_submitted",
        ]
        st.dataframe(
            df[display_cols].rename(columns={
                "full_name": "Name", "school_name": "School", "position_applied_for": "Position",
                "position_category": "Category", "specialization": "Major / Specialization",
                "current_stage": "Stage", "date_applied": "Date Applied",
                "days_in_process": "Days Since Applied",
                "requirements_submitted": "Requirements Submitted",
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

                # Outside the form so switching Teaching <-> Non-Teaching
                # immediately swaps the Major dropdown for the free-text
                # specialization field below (widgets inside a form only
                # update on submit).
                position_category = st.selectbox(
                    "Position category", db.POSITION_CATEGORIES,
                    index=db.POSITION_CATEGORIES.index(applicant["position_category"]),
                    key=f"edit_category_{app_id}",
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
                        specialization = _specialization_field(
                            position_category, applicant["specialization"], key=f"edit_spec_{app_id}"
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

                    st.markdown(
                        "**Stage details** _(date, person in charge, and notes for each stage — "
                        "leave blank if not yet reached)_"
                    )
                    raw_stage_values = _stage_detail_fields(applicant, key_prefix=f"edit_{app_id}")

                    notes = st.text_area("General notes", value=applicant["notes"] or "")
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
                        "specialization": specialization,
                        "source": source,
                        "date_applied": date_applied.isoformat(),
                        "current_stage": current_stage,
                        "notes": notes,
                    }
                    update_data.update(_normalize_stage_values(raw_stage_values))
                    db.update_applicant(app_id, update_data, updated_by=current_user)
                    st.success("Record updated.")
                    st.rerun()

            with st.expander("📎 Requirements / Documents", expanded=False):
                st.caption(
                    "Soft copies of requirements submitted by the applicant — PDF, Word (.docx), "
                    f"or scanned image (.png). Max {db.MAX_DOCUMENT_SIZE_MB} MB per file."
                )
                documents = db.list_applicant_documents(app_id)
                if not documents:
                    st.caption("No documents uploaded yet.")
                else:
                    for doc in documents:
                        with st.container(border=True):
                            c1, c2, c3 = st.columns([3, 2, 1])
                            with c1:
                                st.write(f"**{doc['document_type']}**")
                                st.caption(doc["file_name"])
                                st.caption(
                                    f"{doc['file_size'] / 1024:.0f} KB · uploaded by "
                                    f"{doc['uploaded_by']} on {doc['uploaded_at']}"
                                )
                            with c2:
                                full_doc = db.get_applicant_document(doc["id"])
                                st.download_button(
                                    "⬇️ Download",
                                    data=full_doc["file_data"],
                                    file_name=full_doc["file_name"],
                                    mime=db.DOCUMENT_MIME_TYPES.get(
                                        full_doc["file_ext"], "application/octet-stream"
                                    ),
                                    key=f"dl_{doc['id']}",
                                )
                                if full_doc["file_ext"] == "png":
                                    with st.popover("👁️ Preview"):
                                        st.image(full_doc["file_data"])
                            with c3:
                                st.write("")
                                if st.button("🗑️ Delete", key=f"del_doc_{doc['id']}"):
                                    db.delete_applicant_document(doc["id"], deleted_by=current_user)
                                    st.success("Document deleted.")
                                    st.rerun()

                st.markdown("---")
                st.markdown("**Upload a new document**")
                doc_type_choice = st.selectbox(
                    "Document type", db.DOCUMENT_TYPES, key=f"doc_type_{app_id}"
                )
                custom_doc_type = ""
                if doc_type_choice == "Other":
                    custom_doc_type = st.text_input(
                        "Specify document type", key=f"doc_type_other_{app_id}"
                    )
                uploaded_doc_file = st.file_uploader(
                    "Choose a file (PDF, DOCX, or PNG)",
                    type=db.ALLOWED_DOCUMENT_EXTENSIONS,
                    key=f"doc_upload_{app_id}",
                )
                if st.button("⬆️ Upload document", key=f"doc_upload_btn_{app_id}"):
                    if uploaded_doc_file is None:
                        st.error("Please choose a file first.")
                    elif doc_type_choice == "Other" and not custom_doc_type.strip():
                        st.error("Please specify the document type.")
                    elif uploaded_doc_file.size > db.MAX_DOCUMENT_SIZE_MB * 1024 * 1024:
                        st.error(f"File is too large. Maximum size is {db.MAX_DOCUMENT_SIZE_MB} MB.")
                    else:
                        final_doc_type = (
                            custom_doc_type.strip() if doc_type_choice == "Other" else doc_type_choice
                        )
                        db.add_applicant_document(
                            app_id, final_doc_type, uploaded_doc_file.name,
                            uploaded_doc_file.getvalue(), uploaded_by=current_user,
                        )
                        st.success(f"Uploaded '{uploaded_doc_file.name}'.")
                        st.rerun()

            with st.expander("✅ Requirements Checklist", expanded=False):
                saved_statuses = db.get_requirement_statuses(app_id)
                done, total = db.requirements_progress(saved_statuses)
                st.progress(done / total if total else 0.0, text=f"{done} of {total} applicable requirements submitted")

                with st.form(f"req_form_{app_id}"):
                    new_statuses = _requirements_fields(saved_statuses, key_prefix=f"edit_{app_id}")
                    save_reqs = st.form_submit_button("💾 Save checklist")
                if save_reqs:
                    db.set_requirement_statuses(app_id, new_statuses, changed_by=current_user)
                    st.success("Checklist saved.")
                    st.rerun()

            with st.expander("🎓 Trainings & Seminars Attended", expanded=False):
                st.caption(
                    "Encode each training or seminar the applicant attended (the checklist asks for "
                    "certificates from the past three years)."
                )
                trainings = db.list_applicant_trainings(app_id)
                if not trainings:
                    st.caption("No trainings encoded yet.")
                else:
                    st.markdown(f"**{len(trainings)} training(s) encoded**")
                    for t in trainings:
                        with st.container(border=True):
                            tc1, tc2 = st.columns([5, 1])
                            with tc1:
                                st.write(f"**{t['title']}**")
                                details = []
                                if t["organizer"]:
                                    details.append(f"Organizer: {t['organizer']}")
                                if t["date_from"] and t["date_to"] and t["date_to"] != t["date_from"]:
                                    details.append(f"{t['date_from']} to {t['date_to']}")
                                elif t["date_from"]:
                                    details.append(t["date_from"])
                                if t["hours"]:
                                    details.append(f"{t['hours']:g} hour(s)")
                                details.append(
                                    "Certificate on file ✅" if t["certificate_on_file"]
                                    else "Certificate not yet submitted"
                                )
                                st.caption(" · ".join(details))
                                if t["remarks"]:
                                    st.caption(f"Remarks: {t['remarks']}")
                            with tc2:
                                if st.button("🗑️ Delete", key=f"del_training_{t['id']}"):
                                    db.delete_applicant_training(t["id"], deleted_by=current_user)
                                    st.rerun()

                st.markdown("---")
                st.markdown("**Add a training / seminar**")
                with st.form(f"training_form_{app_id}", clear_on_submit=True):
                    t_title = st.text_input("Title of training / seminar*")
                    t_organizer = st.text_input("Organizer / provider")
                    td1, td2, td3 = st.columns(3)
                    with td1:
                        t_from = st.date_input("Date (from)", value=None, key=f"tr_from_{app_id}")
                    with td2:
                        t_to = st.date_input("Date (to, if multi-day)", value=None, key=f"tr_to_{app_id}")
                    with td3:
                        t_hours = st.number_input("Number of hours", min_value=0.0, step=1.0, value=0.0)
                    t_cert = st.checkbox("Certificate submitted / on file")
                    t_remarks = st.text_input("Remarks")
                    add_training = st.form_submit_button("➕ Add training")
                if add_training:
                    if not t_title.strip():
                        st.error("Please enter the title of the training or seminar.")
                    elif t_from and t_to and t_to < t_from:
                        st.error("The end date can't be earlier than the start date.")
                    else:
                        db.add_applicant_training(
                            app_id, t_title.strip(), t_organizer.strip() or None,
                            t_from.isoformat() if t_from else None,
                            t_to.isoformat() if t_to else None,
                            t_hours or None, t_cert, t_remarks.strip() or None,
                            added_by=current_user,
                        )
                        st.success("Training added.")
                        st.rerun()

            with st.expander("📅 Stage Dates, Person-in-Charge & Notes", expanded=False):
                for date_col, pic_col, notes_col, label in db.STAGE_EXTRA_FIELDS:
                    date_val = applicant[date_col] if date_col in applicant.keys() else None
                    pic_val = applicant[pic_col] if pic_col in applicant.keys() else None
                    notes_val = applicant[notes_col] if notes_col in applicant.keys() else None
                    st.markdown(f"**{label}:** {date_val or '— not yet reached'}")
                    st.caption(f"Person in charge: {pic_val or '—'}")
                    if notes_val:
                        st.caption(f"Notes: {notes_val}")
                    st.markdown("")

            assessment_label = "Teaching" if applicant["position_category"] == "Teaching" else "Non-Teaching"
            with st.expander(f"🧑‍🤝‍🧑 Competency Assessment Assessors ({assessment_label})", expanded=False):
                st.caption(
                    "Add every assessor who took part in this applicant's competency assessment "
                    "— there can be more than two."
                )
                state_key = f"assessors_{app_id}"
                if state_key not in st.session_state:
                    existing_names = db.get_competency_assessors(app_id)
                    st.session_state[state_key] = existing_names if existing_names else [""]

                remove_idx = None
                for i in range(len(st.session_state[state_key])):
                    col_name, col_remove = st.columns([5, 1])
                    with col_name:
                        st.session_state[state_key][i] = st.text_input(
                            f"Assessor {i + 1} name",
                            value=st.session_state[state_key][i],
                            key=f"{state_key}_input_{i}",
                        )
                    with col_remove:
                        st.write("")
                        if st.button("✖ Remove", key=f"{state_key}_remove_{i}") and len(st.session_state[state_key]) > 1:
                            remove_idx = i
                if remove_idx is not None:
                    st.session_state[state_key].pop(remove_idx)
                    st.rerun()

                col_add, col_save = st.columns(2)
                with col_add:
                    if st.button("➕ Add another assessor", key=f"{state_key}_add"):
                        st.session_state[state_key].append("")
                        st.rerun()
                with col_save:
                    if st.button("💾 Save assessors", key=f"{state_key}_save", type="primary"):
                        db.set_competency_assessors(app_id, st.session_state[state_key], changed_by=current_user)
                        st.success("Assessors saved.")
                        st.rerun()

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

        # Outside the form for the same reason as the edit form above —
        # the Major/Specialization field needs to react immediately.
        position_category = st.selectbox("Position category*", db.POSITION_CATEGORIES, key="add_position_category")

        with st.form("add_applicant_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                first_name = st.text_input("First name*")
                last_name = st.text_input("Last name*")
                middle_name = st.text_input("Middle name")
            with c2:
                position_applied_for = st.text_input("Position applied for*")
                specialization = _specialization_field(position_category, None, key="add_specialization")
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

            st.markdown(
                "**Stage details** _(optional — fill in date, person in charge, and notes for any "
                "stage already reached, leave the rest blank)_"
            )
            raw_stage_values = _stage_detail_fields(None, key_prefix="add")

            st.markdown("**Requirements checklist** _(mark what has been submitted so far)_")
            new_req_statuses = _requirements_fields(None, key_prefix="add")

            notes = st.text_area("General notes")
            submitted = st.form_submit_button("➕ Add applicant")

        if submitted:
            if not (first_name and last_name and position_applied_for):
                st.error("First name, last name, and position applied for are required.")
            elif not specialization:
                st.error("Please provide a Major (Teaching) or Specialization/Role (Non-Teaching).")
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
                    "specialization": specialization,
                    "source": source or None,
                    "date_applied": date_applied.isoformat(),
                    "current_stage": current_stage,
                    "notes": notes or None,
                }
                new_applicant_data.update(_normalize_stage_values(raw_stage_values))
                new_id = db.add_applicant(new_applicant_data, created_by=current_user)
                db.set_requirement_statuses(new_id, new_req_statuses, changed_by=current_user)
                st.success(
                    f"Added {first_name} {last_name}. Encode their trainings and seminars from "
                    "View / Edit Applicants → Trainings & Seminars Attended."
                )