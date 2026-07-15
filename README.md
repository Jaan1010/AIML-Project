# Job Application Tracker

Automatically builds and maintains `applied_jobs.csv` — a running record of
every job you've applied to — pulled from **Dice** (via browser automation)
and/or **Gmail** (via the official Gmail API, reading application
confirmation emails).

---

## 1. Folder Structure

```
job_applications_tracker/
├── main.py                  # Entry point — run this
├── config.py                 # Loads all settings from environment variables
├── models.py                  # JobApplication data model + CSV schema
├── dedup.py                    # Merge/dedup logic
├── csv_writer.py                # Reads/writes applied_jobs.csv safely
├── logger_setup.py               # Logging configuration
├── sources/
│   ├── __init__.py
│   ├── dice_scraper.py           # Playwright automation for Dice
│   └── gmail_reader.py             # Gmail API reader/parser
├── credentials/                    # <-- YOU put secret files here (gitignored)
│   ├── gmail_credentials.json        # Google OAuth client secret (you download this)
│   ├── gmail_token.json                # Auto-created after first Gmail login
│   └── dice_session.json                 # Auto-created after first Dice login
├── logs/                             # Rotating log files (auto-created)
├── applied_jobs.csv                    # THE OUTPUT — created/updated automatically
├── .env.example                          # Template — copy to .env and fill in
├── .env                                    # <-- YOU create this (gitignored, never commit it)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 2. Requirements

- Python 3.10+
- Google Chrome/Chromium (installed automatically by Playwright, see below)
- A Dice.com account (for Option 1)
- A Gmail/Google account (for Option 2)

---

## 3. Installation

```bash
# 1. Clone/copy this project, then from inside the project folder:
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright's browser binaries (one-time)
playwright install chromium
```

---

## 4. Where to insert your credentials

**Nothing sensitive is ever hard-coded.** All secrets are read from
environment variables, loaded from a local `.env` file (via `python-dotenv`).

### Step A — Create your `.env` file

```bash
cp .env.example .env
```

Then open `.env` and fill in:

```ini
DICE_EMAIL=your_dice_login_email@example.com
DICE_PASSWORD=your_dice_password
```

`.env` is listed in `.gitignore` — it will never be committed to version control.

### Step B — Gmail API credentials (only needed if using the Gmail source)

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project (or reuse one).
3. Enable the **Gmail API** (APIs & Services → Library → search "Gmail API" → Enable).
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
   - Application type: **Desktop app**.
5. Download the resulting JSON file.
6. Save it as:
   ```
   credentials/gmail_credentials.json
   ```
7. The **first time** you run the Gmail source, a browser window will open
   asking you to log in and grant read-only Gmail access. After that, a
   token is cached at `credentials/gmail_token.json` and you won't need to
   log in again unless the token expires or is revoked.

The app only ever requests the `gmail.readonly` scope — it cannot send,
delete, or modify any email.

### Step C — Dice session (automatic after first run)

You do **not** need to manually export cookies. The first time you run the
Dice source:

- A visible Chromium window opens.
- The script attempts to log in automatically using `DICE_EMAIL` /
  `DICE_PASSWORD` from `.env`.
- If Dice shows a CAPTCHA, 2FA prompt, or any other challenge, the script
  will pause and print a message asking **you** to complete it manually in
  the open window — then press **Enter** in the terminal to continue.
- Once logged in, the session is saved to `credentials/dice_session.json`
  so future runs can skip the login step entirely.

---

## 5. Running the tool

```bash
# Run both sources (Dice preferred, Gmail supplements/fills gaps)
python main.py

# Only Dice
python main.py --source dice

# Only Gmail
python main.py --source gmail

# Custom output path
python main.py --output ~/Documents/applied_jobs.csv
```

Each run:

1. Fetches new data from the selected source(s).
2. Loads the existing `applied_jobs.csv` (if present).
3. Merges new records in, skipping exact duplicates and enriching existing
   rows with any newly-found fields (e.g. a recruiter email found later via
   Gmail gets added to a row originally created from Dice).
4. Writes the result back out atomically (a crash mid-write can't corrupt
   your existing CSV).

You can safely re-run this on a schedule (see "Automation" below) — it is
idempotent and will not create duplicate rows.

---

## 6. CSV Schema

| Column | Notes |
|---|---|
| Company Name | |
| Job Title | |
| Job ID | Extracted from the Dice URL, or from email body when a requisition/job number is present |
| Date Applied | From Dice's applied-date, or the email's Date header |
| Application Status | Dice status badge if available, else "Applied" for Gmail-sourced rows |
| Job Location | Dice only (rarely present in confirmation emails) |
| Employment Type | Dice only |
| Salary | Dice only, when listed |
| Recruiter Name | Best-effort, from email sender name when the email body mentions "recruiter" |
| Recruiter Email | From the confirmation email's sender address |
| Dice Job URL | Direct link to the job posting |
| Source | `Dice` or `Gmail` |
| Notes | Freeform — e.g. the email subject line, for traceability |

---

## 7. Deduplication logic

Each record is de-duplicated using, in priority order:

1. **Dice Job URL** (most reliable — unique per posting)
2. **Job ID** (if a URL isn't available but an ID was extracted)
3. **Company + Job Title + Date Applied** (fallback, normalized/lowercased)

**Known limitation:** if Dice provides a URL-keyed record and Gmail later
provides a same-job record with no URL, they are keyed differently and may
appear as two rows (clearly distinguishable by the `Source` column). In
practice this is rare and easy to spot/merge manually; a future
enhancement could add fuzzy company/title matching to unify these, at the
cost of a higher false-merge risk — this project intentionally favors
"occasionally duplicate" over "occasionally silently merges two different jobs."

---

## 8. Automating it (optional)

Once working manually, schedule periodic runs:

**Linux/macOS (cron)** — run daily at 8am:
```
0 8 * * * cd /path/to/job_applications_tracker && .venv/bin/python main.py --source gmail >> logs/cron.log 2>&1
```
(Cron runs headless with no interactive terminal, so it's strongly
recommended to schedule **only the Gmail source** this way — Dice
automation needs a visible browser available for manual challenge-solving
and is better run interactively when you can watch it.)

**Windows (Task Scheduler)** — point it at `python.exe main.py --source gmail`
inside your project's `.venv`.

---

## 9. If Dice blocks scraping

Dice, like most job boards, runs bot detection (rate limiting, CAPTCHAs,
device fingerprinting, and outright IP/account flags for repeated automated
logins). This project is built to be respectful and defensive about that
(headful browser, session reuse, manual-challenge fallback), but **there is
no guarantee Dice won't eventually block or restrict automated access**, and
aggressive scraping can risk your account standing under Dice's Terms of
Service.

**Recommended alternative if Dice scraping becomes unreliable:**

Rely primarily on the **Gmail source**. Every application you submit through
Dice, LinkedIn Easy Apply, or a company's own ATS (Greenhouse, Lever,
Workday, iCIMS, SmartRecruiters, etc.) almost always triggers an automatic
confirmation email. Since this project already reads and parses those
emails via the official Gmail API — a fully sanctioned, ToS-compliant
integration — you get the same end result (a populated CSV) without ever
touching Dice's front end. This is what `--source gmail` is for.

Secondary options if you want richer Dice-specific data as well:
- Ask Dice support whether they offer a personal data export (some job
  boards provide a "download my activity/applications" feature under
  account settings — check `Dice → Account Settings → Privacy/Data`).
- Manually export/copy the Applied Jobs page occasionally and let the
  Gmail-based automation handle the day-to-day updates in between.

---

## 10. Logging & error handling

- All runs log to both the console and a rotating file at `logs/job_tracker.log`.
- Each source (Dice, Gmail) is wrapped in its own try/except — a failure in
  one never prevents the other from running or from updating the CSV.
- CSV writes are atomic (write-to-temp-then-replace), so an interrupted run
  never corrupts your existing data.

---

## 11. Extending this project

- Add more ATS domains to `SEARCH_QUERY` in `sources/gmail_reader.py` if you
  apply through platforms not already listed.
- Adjust the regex patterns in `gmail_reader.py` if your confirmation
  emails use different phrasing.
- Update `SELECTORS` in `dice_scraper.py` if Dice changes its page markup —
  everything scraping-related is centralized there.
