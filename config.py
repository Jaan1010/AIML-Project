"""
config.py
---------
Centralizes all configuration. Everything sensitive (credentials, paths)
is loaded from environment variables (optionally via a local .env file)
so no secrets ever live in source code.

Copy `.env.example` to `.env` and fill in your real values before running.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a .env file in the project root, if present.
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Dice credentials / behavior
# ---------------------------------------------------------------------------
DICE_EMAIL = os.getenv("DICE_EMAIL", "")
DICE_PASSWORD = os.getenv("DICE_PASSWORD", "")
DICE_APPLIED_JOBS_URL = os.getenv(
    "DICE_APPLIED_JOBS_URL", "https://www.dice.com/dashboard/profile/applications"
)
# Run browser headful (visible) by default. Dice's bot detection is much
# more likely to flag a fully headless session.
DICE_HEADLESS = _get_bool("DICE_HEADLESS", default=False)
# Persist the logged-in browser session so we don't have to log in (and
# potentially trip 2FA / bot checks) on every run.
DICE_STORAGE_STATE_PATH = str(BASE_DIR / "credentials" / "dice_session.json")
DICE_NAV_TIMEOUT_MS = int(os.getenv("DICE_NAV_TIMEOUT_MS", "45000"))

# ---------------------------------------------------------------------------
# Gmail API
# ---------------------------------------------------------------------------
GMAIL_CREDENTIALS_PATH = os.getenv(
    "GMAIL_CREDENTIALS_PATH", str(BASE_DIR / "credentials" / "gmail_credentials.json")
)
GMAIL_TOKEN_PATH = os.getenv(
    "GMAIL_TOKEN_PATH", str(BASE_DIR / "credentials" / "gmail_token.json")
)
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
# How many days back to search for application-confirmation emails.
GMAIL_SEARCH_DAYS_BACK = int(os.getenv("GMAIL_SEARCH_DAYS_BACK", "365"))
GMAIL_MAX_RESULTS = int(os.getenv("GMAIL_MAX_RESULTS", "500"))

# ---------------------------------------------------------------------------
# Output / logging
# ---------------------------------------------------------------------------
CSV_OUTPUT_PATH = os.getenv("CSV_OUTPUT_PATH", str(BASE_DIR / "applied_jobs.csv"))
LOG_DIR = Path(os.getenv("LOG_DIR", str(BASE_DIR / "logs")))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
