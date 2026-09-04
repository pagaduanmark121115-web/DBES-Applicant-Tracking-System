# Deploying the DBES Applicant Tracking Dashboard to the Web

This turns the app into a real website with its own URL, reachable from
any phone, tablet, or computer browser — no need for your PC to be on.

## Why Streamlit Community Cloud

It's free, made by the same people who make Streamlit, and deploys
straight from a GitHub repository with no server setup.

## One-time setup

1. **Create a GitHub account** at github.com if you don't have one.
2. **Create a new repository** (e.g. `dbes-applicant-tracker`) — it can be
   private.
3. **Upload this whole folder's contents** to that repository. Easiest
   way without using git commands:
   - On the repo page, click **Add file → Upload files**.
   - Drag in every file and folder from this project (`app.py`,
     `auth.py`, `dbes_ats_db.py`, `utils.py`, `pwa.py`, `requirements.txt`,
     the `pages/` folder, the `static/` folder, and the `.streamlit/`
     folder — including the hidden-looking `.streamlit` folder, which
     you may need to upload file-by-file since some browsers hide
     folders starting with a dot when drag-dropping).
   - Do **not** upload the `venv/` folder or `data/dbes_applicants.db`
     — you don't want your local test data or virtual environment in
     the repo.
4. **Create a Streamlit Community Cloud account** at
   share.streamlit.io, signing in with your GitHub account.
5. Click **New app**, pick your repository and branch, and set the
   main file path to `app.py`.
6. Click **Deploy**. After a minute or two you'll get a URL like
   `https://your-app-name.streamlit.app`.

## Using it on a phone or tablet

1. Open that URL in the phone/tablet's browser (Chrome, Safari, etc.).
2. Log in with the default admin account (`admin` / `changeme123`) and
   change the password immediately from **My Account** — the app is
   now reachable by anyone with the link, so a real password matters.
3. To install it like an app:
   - **Android/Chrome**: tap the menu (⋮) → **Install app** or **Add
     to Home screen**.
   - **iPhone/iPad/Safari**: tap the Share icon → **Add to Home
     Screen**.
4. It now sits on the home screen with its own icon and opens in a
   full window without browser address bars — installed like a normal
   app, launched by tapping the icon.

## ⚠️ Important: back up your data regularly

Streamlit Community Cloud's free tier does **not guarantee** that
files your app writes at runtime (like the SQLite database) survive:
- The app "sleeping" after a period of no visitors and waking back up
  usually preserves the file, but isn't guaranteed long-term.
- Any time you push a code update to GitHub, the app redeploys from
  the repository — and the repository doesn't contain your database,
  so **a redeploy can wipe all data entered since the last backup**.

To protect against this, use the **Backup & Restore** page (admin
only) added to this dashboard:
- **Before making any code changes or pushing updates**, go to
  Backup & Restore and download a backup.
- Do this on a regular schedule too (e.g. weekly) and keep the
  downloaded `.db` files somewhere safe (Google Drive, email to
  yourself, etc.).
- If data ever does get wiped by a redeploy, upload your most recent
  backup from that same page to restore everything.

If you need guaranteed persistence without manual backups (for
example, once you have real production data for all applicants
and can't risk any loss), the next step up is migrating from the
local SQLite file to a hosted database (e.g. a free-tier Postgres on
Supabase or Neon). That's a larger change to `dbes_ats_db.py` — let me
know if you want help with that migration once you're ready.
