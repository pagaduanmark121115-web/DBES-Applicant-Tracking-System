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
                role TEXT NOT NULL CHECK (role IN ('admin', 'school')),
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

            CREATE TABLE IF NOT EXISTS stage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                applicant_id INTEGER NOT NULL,
                stage TEXT NOT NULL,
                date_entered TEXT NOT NULL,
                remarks TEXT,
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
        cur = conn.execute(
            """
            INSERT INTO applicants (
                school_id, first_name, middle_name, last_name, contact_number, email,
                position_applied_for, position_category, source, date_applied,
                current_stage, notes, date_created, last_updated,
                date_screened, date_interviewed, date_psych_assessment,
                date_competency_teaching, date_competency_nonteaching,
                date_final_interview, date_hired
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["school_id"],
                data["first_name"],
                data.get("middle_name"),
                data["last_name"],
                data.get("contact_number"),
                data.get("email"),
                data["position_applied_for"],
                data["position_category"],
                data.get("source"),
                data["date_applied"],
                data.get("current_stage", "Applied"),
                data.get("notes"),
                now,
                now,
                data.get("date_screened"),
                data.get("date_interviewed"),
                data.get("date_psych_assessment"),
                data.get("date_competency_teaching"),
                data.get("date_competency_nonteaching"),
                data.get("date_final_interview"),
                data.get("date_hired"),
            ),
        )
        applicant_id = cur.lastrowid
        conn.execute(
            "INSERT INTO stage_history (applicant_id, stage, date_entered, remarks) VALUES (?, ?, ?, ?)",
            (applicant_id, data.get("current_stage", "Applied"), data["date_applied"], "Initial application"),
        )
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

        conn.execute(
            """
            UPDATE applicants SET
                school_id = ?, first_name = ?, middle_name = ?, last_name = ?,
                contact_number = ?, email = ?, position_applied_for = ?,
                position_category = ?, source = ?, date_applied = ?,
                current_stage = ?, notes = ?, last_updated = ?,
                date_screened = ?, date_interviewed = ?, date_psych_assessment = ?,
                date_competency_teaching = ?, date_competency_nonteaching = ?,
                date_final_interview = ?, date_hired = ?
            WHERE id = ?
            """,
            (
                data["school_id"],
                data["first_name"],
                data.get("middle_name"),
                data["last_name"],
                data.get("contact_number"),
                data.get("email"),
                data["position_applied_for"],
                data["position_category"],
                data.get("source"),
                data["date_applied"],
                data.get("current_stage", "Applied"),
                data.get("notes"),
                now,
                data.get("date_screened"),
                data.get("date_interviewed"),
                data.get("date_psych_assessment"),
                data.get("date_competency_teaching"),
                data.get("date_competency_nonteaching"),
                data.get("date_final_interview"),
                data.get("date_hired"),
                applicant_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    log_action(updated_by, None, "UPDATE_APPLICANT", "applicant", applicant_id,
               f"Updated applicant {data['first_name']} {data['last_name']}")


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
