"""
dbes_ats_db.py
All SQLite database setup and CRUD operations for the
Diocese of Bayombong Education System (DBES) Applicant Tracking Dashboard.

Named distinctively (not "database.py") to avoid colliding with any
similarly-named package that might already be importable in the
environment — see the DBES HR dashboard's own history with this exact
problem.

Every function that opens a connection closes it in a finally block,
even if an error is raised, so a failed insert (e.g. a UNIQUE
violation) can never leave the database file locked for later calls.
"""

import sqlite3
import os
import bcrypt
from datetime import date, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "dbes_applicants.db")

VICARIATES = ["Northern", "Southern", "Quirino"]

POSITION_CATEGORIES = ["Teaching", "Non-Teaching"]

# Internal role values stay short/stable (used in code, the DB, and
# audit-log filters); ROLE_LABELS is what's actually shown in the UI.
# "school_delegate" is scoped identically to "school" (same assigned
# school) — it exists purely so a delegate's actions are distinguishable
# from the Principal's own in the audit log.
ROLES = ["admin", "school", "school_delegate"]
ROLE_LABELS = {
    "admin": "HR Officer",
    "school": "School Principal",
    "school_delegate": "Delegated Personnel",
}


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


# Full pipeline, in the order applicants normally move through it.
# "Hired" and "Rejected" are terminal and can be reached from any stage.
APPLICATION_STAGES = [
    "Applied",
    "Screening",
    "Interview",
    "Psychological Assessment",
    "Competency Assessment (Teaching)",
    "Competency Assessment (Non-Teaching)",
    "Ranking of Applicants",
    "Final Interview",
    "Job Offer",
    "Hired",
    "Rejected",
]

TERMINAL_STAGES = ["Hired", "Rejected"]

# Teaching applicants pick a Major from this fixed list. Non-Teaching
# applicants instead get a free-text field for their specific role — both
# are stored in the single `specialization` column on the applicant record.
TEACHING_MAJORS = [
    "English", "Mathematics", "Filipino", "Science", "MAPEH",
    "TLE", "ICT", "Social Sciences", "Religion",
]

# Soft-copy requirements/documents that can be attached to an applicant
# record. Uploadable by HR Officer (admin), School Principal (school), and
# Delegated by School Principal (school_delegate) — anyone who can already
# see the applicant's record. Files are stored as BLOBs directly in the
# SQLite database (not on disk) so a single .db backup via the Backup &
# Restore page captures every attached document too.
DOCUMENT_TYPES = [
    "Application Letter",
    "Resume / CV",
    "Transcript of Records (TOR)",
    "Diploma",
    "PRC License / Certificate",
    "NBI Clearance",
    "Barangay Clearance",
    "Medical Certificate",
    "PSA Birth Certificate",
    "PSA Marriage Certificate",
    "2x2 ID Picture",
    "Certificate of Employment",
    "Other",
]

ALLOWED_DOCUMENT_EXTENSIONS = ["pdf", "docx", "png"]
MAX_DOCUMENT_SIZE_MB = 10
DOCUMENT_MIME_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "png": "image/png",
}

# Explicit per-stage date fields the person asked to be able to fill in
# directly on the applicant record (in addition to the automatic
# stage_history log). Each tuple is (column_name, label_for_forms).
STAGE_DATE_FIELDS = [
    ("date_applied", "Date Applied"),
    ("date_screened", "Date Screened"),
    ("date_interviewed", "Date Interviewed"),
    ("date_psych_assessment", "Date of Psychological Assessment"),
    ("date_competency_teaching", "Date of Competency Assessment (Teaching)"),
    ("date_competency_nonteaching", "Date of Competency Assessment (Non-Teaching)"),
    ("date_final_interview", "Date of Final Interview"),
    ("date_hired", "Date Hired"),
]
# date_applied already exists as a required column from the original schema;
# the rest are optional columns added by the migration below.
_NEW_STAGE_DATE_COLUMNS = [c for c, _ in STAGE_DATE_FIELDS if c != "date_applied"]

# Person-in-charge + notes fields, one pair per stage in STAGE_DATE_FIELDS
# (including the Applied stage). Each tuple is
# (date_column, pic_column, notes_column, label). Derived from
# STAGE_DATE_FIELDS so the naming stays consistent automatically, e.g.
# "date_screened" -> "pic_screened" / "notes_screened".
STAGE_EXTRA_FIELDS = [
    (date_col, f"pic_{date_col[len('date_'):]}", f"notes_{date_col[len('date_'):]}", label)
    for date_col, label in STAGE_DATE_FIELDS
]

# All applicant-table columns that forms are allowed to write to directly
# (excludes id, date_created, last_updated, which are handled separately).
APPLICANT_BASE_COLUMNS = [
    "school_id", "first_name", "middle_name", "last_name", "contact_number", "email",
    "position_applied_for", "position_category", "specialization", "source",
    "date_applied", "current_stage", "notes",
]
STAGE_PIC_COLUMNS = [pic for _, pic, _, _ in STAGE_EXTRA_FIELDS]
STAGE_NOTES_COLUMNS = [notes for _, _, notes, _ in STAGE_EXTRA_FIELDS]
ALL_EDITABLE_APPLICANT_COLUMNS = (
    APPLICANT_BASE_COLUMNS + _NEW_STAGE_DATE_COLUMNS + STAGE_PIC_COLUMNS + STAGE_NOTES_COLUMNS
)
# Columns added by migration on top of the original schema (everything new
# in this feature: specialization + every per-stage PIC/notes column).
_NEW_APPLICANT_COLUMNS = ["specialization"] + STAGE_PIC_COLUMNS + STAGE_NOTES_COLUMNS


# Checklist of requirements an applicant submits. Each tuple is
# (stable_key, label_shown_in_UI, can_be_not_applicable). Keys are stored in
# the database, so never rename a key — change only the label if needed.
REQUIREMENTS = [
    ("application_letter", "Application letter addressed to the College President", False),
    ("resume", "Comprehensive Resume / Curriculum Vitae", False),
    ("tor", "Photocopy of Transcript of Records (TOR)", False),
    ("diploma", "Photocopy of Diploma", False),
    ("prc", "Photocopy of PRC ID and Board Rating (if applicable)", True),
    ("tesda_nc2", "TESDA National Certificate II (NC II) for Senior High School TVL applicants (if applicable)", True),
    ("coe", "Certificate of Employment (for those with previous working experience)", True),
    ("trainings", "Certificates of Training and Seminar attended (for the past three years)", False),
    ("psa_birth_cert", "Photocopy of PSA-issued Birth Certificate", False),
    ("nbi", "NBI Clearance", False),
    ("id_pictures", "Two (2) copies of recent 2x2 ID picture", False),
]
REQ_NOT_SUBMITTED = "Not yet submitted"
REQ_SUBMITTED = "Submitted"
REQ_NOT_APPLICABLE = "Not applicable"


class DuplicateSchoolError(Exception):
    pass


class DuplicateUsernameError(Exception):
    pass


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS vicariates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );

            CREATE TABLE IF NOT EXISTS schools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                vicariate_id INTEGER NOT NULL,
                FOREIGN KEY (vicariate_id) REFERENCES vicariates(id),
                UNIQUE(name, vicariate_id)
            );

            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('admin', 'school', 'school_delegate')),
                school_id INTEGER,
                is_active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (school_id) REFERENCES schools(id)
            );

            CREATE TABLE IF NOT EXISTS applicants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER NOT NULL,
                first_name TEXT NOT NULL,
                middle_name TEXT,
                last_name TEXT NOT NULL,
                contact_number TEXT,
                email TEXT,
                position_applied_for TEXT NOT NULL,
                position_category TEXT NOT NULL,
                source TEXT,
                date_applied TEXT NOT NULL,
                current_stage TEXT NOT NULL DEFAULT 'Applied',
                notes TEXT,
                date_created TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                FOREIGN KEY (school_id) REFERENCES schools(id)
            );

            CREATE TABLE IF NOT EXISTS competency_assessors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER NOT NULL,
                assessor_name TEXT NOT NULL,
                FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS stage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER NOT NULL,
                stage TEXT NOT NULL,
                date_entered TEXT NOT NULL,
                remarks TEXT,
                FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS applicant_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER NOT NULL,
                document_type TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_ext TEXT NOT NULL,
                file_data BLOB NOT NULL,
                file_size INTEGER NOT NULL,
                uploaded_by TEXT,
                uploaded_at TEXT NOT NULL,
                FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS applicant_requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER NOT NULL,
                requirement_key TEXT NOT NULL,
                status TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(applicant_id, requirement_key),
                FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS applicant_trainings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                organizer TEXT,
                date_from TEXT,
                date_to TEXT,
                hours REAL,
                certificate_on_file INTEGER NOT NULL DEFAULT 0,
                remarks TEXT,
                added_by TEXT,
                added_at TEXT NOT NULL,
                FOREIGN KEY (applicant_id) REFERENCES applicants(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT,
                role TEXT,
                action TEXT NOT NULL,
                entity_type TEXT,
                entity_id INTEGER,
                details TEXT
            );
            """
        )
        conn.commit()

        _migrate_stage_date_columns(conn)
        _migrate_new_applicant_columns(conn)
        _migrate_user_role_check(conn)

        for v in VICARIATES:
            cur.execute("INSERT OR IGNORE INTO vicariates (name) VALUES (?)", (v,))
        conn.commit()

        cur.execute("SELECT COUNT(*) AS c FROM users")
        if cur.fetchone()["c"] == 0:
            default_hash = hash_password("changeme123")
            cur.execute(
                "INSERT INTO users (username, password_hash, full_name, role, school_id) "
                "VALUES (?, ?, ?, 'admin', NULL)",
                ("admin", default_hash, "System Administrator"),
            )
            conn.commit()
    finally:
        conn.close()


def _migrate_stage_date_columns(conn):
    """Add the per-stage date columns to an already-existing applicants
    table (older databases created before this feature won't have them).
    SQLite has no 'ADD COLUMN IF NOT EXISTS', so check first."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(applicants)").fetchall()}
    for column in _NEW_STAGE_DATE_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE applicants ADD COLUMN {column} TEXT")
    conn.commit()


def _migrate_new_applicant_columns(conn):
    """Add the specialization/major column and the per-stage
    person-in-charge + notes columns to an already-existing applicants
    table. Idempotent, same approach as _migrate_stage_date_columns."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(applicants)").fetchall()}
    for column in _NEW_APPLICANT_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE applicants ADD COLUMN {column} TEXT")
    conn.commit()


def _migrate_user_role_check(conn):
    """SQLite has no ALTER TABLE ... DROP/MODIFY CONSTRAINT, so widening
    the users.role CHECK to allow 'school_delegate' means rebuilding the
    table. Only runs if the existing table's CHECK doesn't already allow
    it — safe to call every startup. All existing rows (and their roles)
    are preserved."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()
    if row and "school_delegate" in (row["sql"] or ""):
        return  # already migrated
    if not row:
        return  # table doesn't exist yet; CREATE TABLE above already has it right
    conn.executescript(
        """
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'school', 'school_delegate')),
            school_id INTEGER,
            is_active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (school_id) REFERENCES schools(id)
        );
        INSERT INTO users_new (id, username, password_hash, full_name, role, school_id, is_active)
            SELECT id, username, password_hash, full_name, role, school_id, is_active FROM users;
        DROP TABLE users;
        ALTER TABLE users_new RENAME TO users;
        """
    )
    conn.commit()


# ---------- Audit log ----------

def log_action(username, role, action, entity_type=None, entity_id=None, details=None):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO audit_log (timestamp, username, role, action, entity_type, entity_id, details)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now().isoformat(timespec="seconds"), username, role, action, entity_type, entity_id, details),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit_log(limit=500):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()


# ---------- Auth helpers ----------

def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def get_user_by_username(username: str):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)
        ).fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id: int):
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()


def create_user(username, plain_password, full_name, role, school_id=None, created_by="admin"):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, full_name, role, school_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, hash_password(plain_password), full_name, role, school_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateUsernameError(f"Username '{username}' already exists.")
    finally:
        conn.close()
    log_action(created_by, "admin", "CREATE_USER", "user", None, f"Created {role} account '{username}'")


def list_users():
    conn = get_connection()
    try:
        return conn.execute(
            """
            SELECT u.id, u.username, u.full_name, u.role, u.is_active,
                   s.name AS school_name
            FROM users u
            LEFT JOIN schools s ON u.school_id = s.id
            ORDER BY u.role, u.username
            """
        ).fetchall()
    finally:
        conn.close()


def set_user_active(user_id: int, is_active: bool, changed_by="admin"):
    conn = get_connection()
    try:
        conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (int(is_active), user_id))
        conn.commit()
    finally:
        conn.close()
    log_action(changed_by, "admin", "TOGGLE_USER_ACTIVE", "user", user_id, f"Set active={is_active}")


def reset_user_password(user_id: int, new_password: str, changed_by="admin"):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        conn.commit()
    finally:
        conn.close()
    log_action(changed_by, "admin", "RESET_PASSWORD", "user", user_id, "Admin reset a user's password")


def change_own_password(user_id: int, current_password: str, new_password: str):
    user = get_user_by_id(user_id)
    if not user:
        return False, "User not found."
    if not verify_password(current_password, user["password_hash"]):
        return False, "Current password is incorrect."
    if len(new_password) < 6:
        return False, "New password must be at least 6 characters."

    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        conn.commit()
    finally:
        conn.close()
    log_action(user["username"], user["role"], "CHANGE_OWN_PASSWORD", "user", user_id,
               "User changed their own password")
    return True, "Password updated successfully."


# ---------- Vicariate / school helpers ----------

def list_vicariates():
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM vicariates ORDER BY name").fetchall()
    finally:
        conn.close()


def list_schools(vicariate_id=None):
    conn = get_connection()
    try:
        if vicariate_id:
            return conn.execute(
                """SELECT s.*, v.name AS vicariate_name FROM schools s
                   JOIN vicariates v ON s.vicariate_id = v.id
                   WHERE s.vicariate_id = ? ORDER BY s.name""",
                (vicariate_id,),
            ).fetchall()
        return conn.execute(
            """SELECT s.*, v.name AS vicariate_name FROM schools s
               JOIN vicariates v ON s.vicariate_id = v.id
               ORDER BY v.name, s.name"""
        ).fetchall()
    finally:
        conn.close()


def add_school(name: str, vicariate_id: int, created_by="admin"):
    conn = get_connection()
    try:
        cur = conn.execute(
            "INSERT INTO schools (name, vicariate_id) VALUES (?, ?)", (name, vicariate_id)
        )
        school_id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        raise DuplicateSchoolError(f"'{name}' already exists in this vicariate.")
    finally:
        conn.close()
    log_action(created_by, "admin", "ADD_SCHOOL", "school", school_id, f"Added school '{name}'")
    return school_id


def get_school(school_id: int):
    conn = get_connection()
    try:
        return conn.execute(
            """SELECT s.*, v.name AS vicariate_name FROM schools s
               JOIN vicariates v ON s.vicariate_id = v.id WHERE s.id = ?""",
            (school_id,),
        ).fetchone()
    finally:
        conn.close()


# ---------- Applicant CRUD ----------

def add_applicant(data: dict, created_by="admin"):
    conn = get_connection()
    now = date.today().isoformat()
    try:
        columns = ALL_EDITABLE_APPLICANT_COLUMNS + ["date_created", "last_updated"]
        values = [data.get(c) for c in ALL_EDITABLE_APPLICANT_COLUMNS] + [now, now]
        placeholders = ", ".join(["?"] * len(columns))
        cur = conn.execute(
            f"INSERT INTO applicants ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        applicant_id = cur.lastrowid
        conn.execute(
            "INSERT INTO stage_history (applicant_id, stage, date_entered, remarks) VALUES (?, ?, ?, ?)",
            (applicant_id, data.get("current_stage", "Applied"), data["date_applied"], "Initial application"),
        )
        if "competency_assessors" in data:
            _replace_competency_assessors(conn, applicant_id, data["competency_assessors"])
        conn.commit()
    finally:
        conn.close()
    log_action(created_by, None, "CREATE_APPLICANT", "applicant", applicant_id,
               f"Added applicant {data['first_name']} {data['last_name']}")
    return applicant_id


def update_applicant(applicant_id: int, data: dict, updated_by="admin", record_history=True):
    conn = get_connection()
    now = date.today().isoformat()
    try:
        if record_history:
            current = conn.execute(
                "SELECT current_stage FROM applicants WHERE id = ?", (applicant_id,)
            ).fetchone()
            if current and data.get("current_stage") and data["current_stage"] != current["current_stage"]:
                conn.execute(
                    "INSERT INTO stage_history (applicant_id, stage, date_entered, remarks) VALUES (?, ?, ?, ?)",
                    (applicant_id, data["current_stage"], now, "Stage update"),
                )

        set_clause = ", ".join([f"{c} = ?" for c in ALL_EDITABLE_APPLICANT_COLUMNS]) + ", last_updated = ?"
        values = [data.get(c) for c in ALL_EDITABLE_APPLICANT_COLUMNS] + [now, applicant_id]
        conn.execute(
            f"UPDATE applicants SET {set_clause} WHERE id = ?",
            values,
        )
        if "competency_assessors" in data:
            _replace_competency_assessors(conn, applicant_id, data["competency_assessors"])
        conn.commit()
    finally:
        conn.close()
    log_action(updated_by, None, "UPDATE_APPLICANT", "applicant", applicant_id,
               f"Updated applicant {data['first_name']} {data['last_name']}")


# ---------- Competency assessors (Competency Assessment stage can have
# more than one assessor, for both Teaching and Non-Teaching applicants) ----------

def _replace_competency_assessors(conn, applicant_id: int, names):
    """Replace the full assessor list for an applicant in one go — the
    form always submits the complete current list, so delete-then-insert
    is simpler and safer than diffing."""
    conn.execute("DELETE FROM competency_assessors WHERE applicant_id = ?", (applicant_id,))
    for name in names or []:
        name = (name or "").strip()
        if name:
            conn.execute(
                "INSERT INTO competency_assessors (applicant_id, assessor_name) VALUES (?, ?)",
                (applicant_id, name),
            )


def get_competency_assessors(applicant_id: int):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT assessor_name FROM competency_assessors WHERE applicant_id = ? ORDER BY id",
            (applicant_id,),
        ).fetchall()
        return [r["assessor_name"] for r in rows]
    finally:
        conn.close()


def set_competency_assessors(applicant_id: int, names, changed_by="admin"):
    """Standalone setter used by the UI's own 'Save assessors' action,
    separate from the main applicant edit form."""
    conn = get_connection()
    try:
        _replace_competency_assessors(conn, applicant_id, names)
        conn.commit()
    finally:
        conn.close()
    log_action(changed_by, None, "UPDATE_COMPETENCY_ASSESSORS", "applicant", applicant_id,
               "Assessor list updated")


def delete_applicant(applicant_id: int, deleted_by="admin"):
    app_row = get_applicant(applicant_id)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM applicants WHERE id = ?", (applicant_id,))
        conn.commit()
    finally:
        conn.close()
    name = f"{app_row['first_name']} {app_row['last_name']}" if app_row else str(applicant_id)
    log_action(deleted_by, None, "DELETE_APPLICANT", "applicant", applicant_id, f"Deleted applicant {name}")


def get_applicant(applicant_id: int):
    conn = get_connection()
    try:
        return conn.execute(
            """SELECT a.*, s.name AS school_name, v.name AS vicariate_name
               FROM applicants a
               JOIN schools s ON a.school_id = s.id
               JOIN vicariates v ON s.vicariate_id = v.id
               WHERE a.id = ?""",
            (applicant_id,),
        ).fetchone()
    finally:
        conn.close()


def list_applicants(school_id=None, vicariate_id=None):
    conn = get_connection()
    try:
        query = """
            SELECT a.*, s.name AS school_name, v.name AS vicariate_name
            FROM applicants a
            JOIN schools s ON a.school_id = s.id
            JOIN vicariates v ON s.vicariate_id = v.id
        """
        params = []
        if school_id:
            query += " WHERE a.school_id = ?"
            params.append(school_id)
        elif vicariate_id:
            query += " WHERE s.vicariate_id = ?"
            params.append(vicariate_id)
        query += " ORDER BY a.date_applied DESC"
        return conn.execute(query, params).fetchall()
    finally:
        conn.close()


def get_stage_history(applicant_id: int):
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM stage_history WHERE applicant_id = ? ORDER BY date_entered",
            (applicant_id,),
        ).fetchall()
    finally:
        conn.close()


# ---------- Applicant documents (soft copies of submitted requirements) ----------

def add_applicant_document(applicant_id: int, document_type: str, file_name: str,
                            file_bytes: bytes, uploaded_by="admin"):
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO applicant_documents
               (applicant_id, document_type, file_name, file_ext, file_data, file_size,
                uploaded_by, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (applicant_id, document_type, file_name, ext, file_bytes, len(file_bytes),
             uploaded_by, now),
        )
        doc_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    log_action(uploaded_by, None, "UPLOAD_DOCUMENT", "applicant_document", doc_id,
               f"Uploaded '{file_name}' ({document_type}) for applicant #{applicant_id}")
    return doc_id


def list_applicant_documents(applicant_id: int):
    """Metadata only (no file_data) — cheap to call for every row in a list."""
    conn = get_connection()
    try:
        return conn.execute(
            """SELECT id, applicant_id, document_type, file_name, file_ext, file_size,
                      uploaded_by, uploaded_at
               FROM applicant_documents
               WHERE applicant_id = ?
               ORDER BY uploaded_at DESC""",
            (applicant_id,),
        ).fetchall()
    finally:
        conn.close()


def get_applicant_document(document_id: int):
    """Full row including file_data — call only when actually serving a
    download or preview, not when just listing documents."""
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT * FROM applicant_documents WHERE id = ?", (document_id,)
        ).fetchone()
    finally:
        conn.close()


def delete_applicant_document(document_id: int, deleted_by="admin"):
    doc = get_applicant_document(document_id)
    conn = get_connection()
    try:
        conn.execute("DELETE FROM applicant_documents WHERE id = ?", (document_id,))
        conn.commit()
    finally:
        conn.close()
    if doc:
        log_action(deleted_by, None, "DELETE_DOCUMENT", "applicant_document", document_id,
                   f"Deleted '{doc['file_name']}' ({doc['document_type']}) for applicant #{doc['applicant_id']}")


# ---------- Requirements checklist ----------

def get_requirement_statuses(applicant_id: int) -> dict:
    """{requirement_key: status}. Requirements never saved default to 'Not yet submitted'."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT requirement_key, status FROM applicant_requirements WHERE applicant_id = ?",
            (applicant_id,),
        ).fetchall()
    finally:
        conn.close()
    saved = {r["requirement_key"]: r["status"] for r in rows}
    return {key: saved.get(key, REQ_NOT_SUBMITTED) for key, _, _ in REQUIREMENTS}


def _write_requirement_statuses(conn, applicant_id: int, statuses: dict):
    now = datetime.now().isoformat(timespec="seconds")
    for key, _, _ in REQUIREMENTS:
        conn.execute(
            """INSERT INTO applicant_requirements (applicant_id, requirement_key, status, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(applicant_id, requirement_key)
               DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at""",
            (applicant_id, key, statuses.get(key, REQ_NOT_SUBMITTED), now),
        )


def set_requirement_statuses(applicant_id: int, statuses: dict, changed_by="admin"):
    conn = get_connection()
    try:
        _write_requirement_statuses(conn, applicant_id, statuses)
        conn.commit()
    finally:
        conn.close()
    done = sum(1 for v in statuses.values() if v == REQ_SUBMITTED)
    log_action(changed_by, None, "UPDATE_REQUIREMENTS", "applicant", applicant_id,
               f"Requirements checklist updated ({done} submitted)")


def requirements_progress(statuses: dict):
    """(submitted, applicable_total) — 'Not applicable' items don't count toward the total."""
    applicable = [v for v in statuses.values() if v != REQ_NOT_APPLICABLE]
    submitted = [v for v in applicable if v == REQ_SUBMITTED]
    return len(submitted), len(applicable)


def requirements_progress_map() -> dict:
    """{applicant_id: 'submitted/applicable'} for every applicant, in one query."""
    conn = get_connection()
    try:
        ids = [r["id"] for r in conn.execute("SELECT id FROM applicants").fetchall()]
        rows = conn.execute(
            "SELECT applicant_id, requirement_key, status FROM applicant_requirements"
        ).fetchall()
    finally:
        conn.close()
    by_applicant = {}
    for r in rows:
        by_applicant.setdefault(r["applicant_id"], {})[r["requirement_key"]] = r["status"]
    result = {}
    for aid in ids:
        saved = by_applicant.get(aid, {})
        statuses = {key: saved.get(key, REQ_NOT_SUBMITTED) for key, _, _ in REQUIREMENTS}
        done, total = requirements_progress(statuses)
        result[aid] = f"{done}/{total}"
    return result


# ---------- Trainings and seminars attended ----------

def add_applicant_training(applicant_id: int, title: str, organizer=None, date_from=None,
                            date_to=None, hours=None, certificate_on_file=False,
                            remarks=None, added_by="admin"):
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO applicant_trainings
               (applicant_id, title, organizer, date_from, date_to, hours,
                certificate_on_file, remarks, added_by, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (applicant_id, title, organizer, date_from, date_to, hours,
             int(bool(certificate_on_file)), remarks, added_by, now),
        )
        training_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()
    log_action(added_by, None, "ADD_TRAINING", "applicant_training", training_id,
               f"Added training '{title}' for applicant #{applicant_id}")
    return training_id


def list_applicant_trainings(applicant_id: int):
    conn = get_connection()
    try:
        return conn.execute(
            """SELECT * FROM applicant_trainings WHERE applicant_id = ?
               ORDER BY COALESCE(date_from, '') DESC, id DESC""",
            (applicant_id,),
        ).fetchall()
    finally:
        conn.close()


def delete_applicant_training(training_id: int, deleted_by="admin"):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT title, applicant_id FROM applicant_trainings WHERE id = ?", (training_id,)
        ).fetchone()
        conn.execute("DELETE FROM applicant_trainings WHERE id = ?", (training_id,))
        conn.commit()
    finally:
        conn.close()
    if row:
        log_action(deleted_by, None, "DELETE_TRAINING", "applicant_training", training_id,
                   f"Deleted training '{row['title']}' for applicant #{row['applicant_id']}")


# ---------- Three-year rule for trainings and seminars ----------

TRAINING_LOOKBACK_YEARS = 3


def training_cutoff(today=None):
    """Earliest date a training can have and still count toward the
    'past three years' requirement."""
    today = today or date.today()
    try:
        return today.replace(year=today.year - TRAINING_LOOKBACK_YEARS)
    except ValueError:  # Feb 29 -> Feb 28
        return today.replace(year=today.year - TRAINING_LOOKBACK_YEARS, day=28)


def replace_applicant_trainings(applicant_id: int, rows, changed_by="admin"):
    """Replace the applicant's whole trainings list with `rows` (list of
    dicts: title, organizer, date_from, date_to, hours, certificate_on_file,
    remarks). The table editor on the page always submits the complete
    current list, so delete-then-insert is the simplest safe approach."""
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_connection()
    try:
        conn.execute("DELETE FROM applicant_trainings WHERE applicant_id = ?", (applicant_id,))
        for r in rows:
            conn.execute(
                """INSERT INTO applicant_trainings
                   (applicant_id, title, organizer, date_from, date_to, hours,
                    certificate_on_file, remarks, added_by, added_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (applicant_id, r["title"], r.get("organizer"), r.get("date_from"),
                 r.get("date_to"), r.get("hours"), int(bool(r.get("certificate_on_file"))),
                 r.get("remarks"), changed_by, now),
            )
        conn.commit()
    finally:
        conn.close()
    log_action(changed_by, None, "UPDATE_TRAININGS", "applicant", applicant_id,
               f"Trainings list saved ({len(rows)} entries)")