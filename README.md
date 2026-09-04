# DBES Applicant Tracking Dashboard

A login-protected Streamlit dashboard for tracking job applicants across
the schools of the Diocese of Bayombong Education System, grouped into
three vicariates: Northern, Southern, and Quirino.

## Features

- Login system with two roles:
  - Admin - sees and manages all schools and all applicants; can
    create/disable user logins and view the audit log.
  - School-level (principal/HR) - sees and manages only their own
    school's applicants. The school field is locked/read-only for them
    everywhere.
- School setup form - add or verify your schools at any time from
  the main page (not a one-time setup screen), grouped by vicariate.
- Applicant pipeline: Applied, Screening, Interview,
  Psychological Assessment, Competency Assessment (Teaching),
  Competency Assessment (Non-Teaching), Ranking of Applicants, Final
  Interview, Job Offer, Hired/Rejected. Every stage change is
  logged to a per-applicant history so you can see their full timeline.
- Dashboard - pipeline funnel by stage, teaching vs. non-teaching
  split, per-school/vicariate breakdowns, hired/rejected counts, and a
  "longest waiting" list to flag applicants stuck in process. CSV
  export.
- Applicants page - search, filter by stage, add, edit, and view
  full stage history per applicant. CSV export.
- My Account - any logged-in user can change their own password.
- Manage Users (admin only) - create school-level logins tied to a
  specific school, reset passwords, enable/disable accounts.
- Audit Log (admin only) - every login, logout, failed login, and
  create/update/delete of applicants, schools, and users is
  timestamped and attributed to a username. Filterable, exportable.
- Installable on phones/tablets as a home-screen app (PWA), and ready
  to host online so it's reachable from any device without your PC
  running - see Mobile & Hosting below.
- A Backup & Restore page to protect your data if hosted for free.

## Setup (Windows / VS Code)

1. Open this folder in VS Code.
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Run the app:
   ```
   streamlit run app.py
   ```
   Or, after the first setup, just double-click run_dashboard.bat to
   launch it without opening VS Code at all.
5. Log in with the default admin account:
   - Username: admin
   - Password: changeme123
   - Change this immediately from the My Account page.

## First-time setup

1. Log in as admin.
2. On the main page, expand "Add / verify a school" and fill out
   each DBES school under its correct vicariate. You can come back and
   add more at any time.
3. Go to Manage Users to create a school-level login for each
   school (each one will only see their own school's applicants).
4. Go to Applicants to start entering applicant records.

## Project structure

```
dbes_applicant_tracker/
    app.py                    Entry point + login + school setup
    auth.py                   Login/session/role helpers + login audit
    dbes_ats_db.py            SQLite schema + all CRUD + audit logging
    utils.py                  Date helpers, CSV export
    pwa.py                    Installs the app on phones/tablets (PWA)
    requirements.txt
    run_dashboard.bat         Double-click launcher (no VS Code needed)
    DEPLOYMENT.md             How to host this online for phone/tablet access
    .streamlit/
        config.toml           Enables static file serving + theme color
    static/
        manifest.json          PWA manifest (name, icons, colors)
        service-worker.js      Minimal service worker (installability only)
        icon-192.png / icon-512.png   Home-screen icons
    data/
        dbes_applicants.db    Created automatically on first run
    pages/
        1_Dashboard.py             Pipeline stats, charts, CSV export
        2_Applicants.py            Add/edit/view applicants, CSV export
        3_Manage_Users.py          Admin-only: manage logins
        4_My_Account.py            Any user: change own password
        5_Audit_Log.py             Admin-only: view/filter/export audit trail
        6_Backup_Restore.py        Admin-only: download/restore a full backup
```

## Mobile & Hosting

This app can be used on phones and tablets two ways:

1. Locally over Wi-Fi (works today, no extra setup): run
   `streamlit run app.py --server.address 0.0.0.0` on your PC, then on
   a phone/tablet connected to the same Wi-Fi network, open
   `http://<your-pc's-local-IP>:8501` in a browser. Find your PC's
   local IP with `ipconfig` (look for "IPv4 Address").
2. Hosted online (works from anywhere, PC doesn't need to be on):
   deploy it to Streamlit Community Cloud (free). See DEPLOYMENT.md in
   this folder for the full walkthrough.

Either way, once opened on a phone/tablet browser, you can "Add to
Home Screen" (or "Install app" on Android/Chrome) to get a proper app
icon that launches in its own window - that's what pwa.py and the
static/ folder set up.

If you host it for free, read the backup warning in DEPLOYMENT.md -
free hosting doesn't guarantee your database survives every redeploy,
so use the Backup & Restore page regularly.

## Notes

- This is a separate project from the DBES HR/Employee Records
  Dashboard - it has its own folder, its own database file
  (dbes_applicants.db), and its own set of logins. Schools have to be
  added here too even if you already added them in the HR dashboard.
- The database module is named dbes_ats_db.py (not database.py) on
  purpose, to avoid any chance of colliding with another package of
  that name in your Python environment.
- Backups: back up data/dbes_applicants.db regularly - it holds
  every applicant record and the audit trail.
