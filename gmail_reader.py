"""
sources/gmail_reader.py
-------------------------
Uses the official Gmail API (OAuth2, read-only scope) to find job
application confirmation emails and extract structured data from them.

Setup required (see README for full walkthrough):
  1. Create a Google Cloud project, enable the Gmail API.
  2. Create OAuth 2.0 Desktop credentials, download as JSON.
  3. Save that file to the path in config.GMAIL_CREDENTIALS_PATH
     (default: credentials/gmail_credentials.json).
  4. First run opens a browser for you to authorize; a token is then
     cached at config.GMAIL_TOKEN_PATH so you don't re-auth every time.

This module never sends or modifies email — it uses the
`gmail.readonly` scope only.
"""

import base64
import re
from email.utils import parseaddr
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
import logger_setup
from models import JobApplication

logger = logger_setup.get_logger(__name__)

# Search query targeting common job-application confirmation phrasing.
# Adjust/extend this to match the ATS systems you actually apply through.
SEARCH_QUERY = (
    f"newer_than:{config.GMAIL_SEARCH_DAYS_BACK}d "
    '(subject:("application received" OR "thank you for applying" OR '
    '"your application" OR "application confirmation" OR "we received your application") '
    "OR from:(dice.com OR linkedin.com OR indeed.com OR greenhouse.io OR "
    "lever.co OR workday.com OR myworkdayjobs.com OR icims.com OR smartrecruiters.com))"
)

# Heuristic patterns used to pull structured fields out of free-text email bodies.
JOB_TITLE_PATTERNS = [
    r"application for the (?:position of )?([A-Za-z0-9 ,/&\-]{3,80}?) (?:position|role|at|has been received)",
    r"applied to (?:the )?([A-Za-z0-9 ,/&\-]{3,80}?) (?:position|role) at",
    r"your application for ([A-Za-z0-9 ,/&\-]{3,80}?)(?:\.|,|\n)",
]
COMPANY_PATTERNS = [
    r"(?:at|with) ([A-Z][A-Za-z0-9&.,\- ]{1,60}?)(?:\.|,|\n| has| have| team)",
]
JOB_ID_PATTERNS = [
    r"(?:Job ID|Requisition(?: ID)?|Req(?:uisition)? #|Job Number)[:\s#]*([A-Za-z0-9\-]{3,20})",
]


def _get_credentials() -> Credentials:
    creds: Optional[Credentials] = None
    token_path = config.GMAIL_TOKEN_PATH

    import os
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, config.GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Refreshing expired Gmail token...")
            creds.refresh(Request())
        else:
            if not os.path.exists(config.GMAIL_CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Gmail OAuth client secrets not found at "
                    f"{config.GMAIL_CREDENTIALS_PATH}. See README setup instructions."
                )
            logger.info("Launching OAuth consent flow for Gmail access...")
            flow = InstalledAppFlow.from_client_secrets_file(
                config.GMAIL_CREDENTIALS_PATH, config.GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(token_path), exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info("Saved Gmail token to %s.", token_path)

    return creds


def _decode_body(payload: dict) -> str:
    """Recursively extract and decode the plain-text (or HTML) body from a Gmail payload."""
    if not payload:
        return ""

    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        data = payload["body"]["data"]
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    if "parts" in payload:
        texts = []
        for part in payload["parts"]:
            texts.append(_decode_body(part))
        joined = "\n".join(t for t in texts if t)
        if joined:
            return joined

    # Fall back to HTML body, stripped of tags, if no plain text was found.
    if payload.get("mimeType") == "text/html" and "data" in payload.get("body", {}):
        data = payload["body"]["data"]
        html = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        return re.sub("<[^<]+?>", " ", html)

    return ""


def _first_match(patterns: List[str], text: str) -> str:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _parse_message(service, msg_id: str) -> Optional[JobApplication]:
    try:
        msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    except HttpError as e:
        logger.warning("Failed to fetch Gmail message %s: %s", msg_id, e)
        return None

    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    subject = headers.get("subject", "")
    from_header = headers.get("from", "")
    date_header = headers.get("date", "")

    sender_name, sender_email = parseaddr(from_header)

    body = _decode_body(msg["payload"])
    combined_text = f"{subject}\n{body}"

    job_title = _first_match(JOB_TITLE_PATTERNS, combined_text)
    company = _first_match(COMPANY_PATTERNS, combined_text)
    job_id = _first_match(JOB_ID_PATTERNS, combined_text)

    # If we couldn't confidently extract a company name from the body,
    # fall back to the sender's domain/display name as a best-effort guess.
    if not company and sender_name:
        company = sender_name

    return JobApplication(
        company_name=company,
        job_title=job_title,
        job_id=job_id,
        date_applied=date_header,
        application_status="Applied",
        job_location="",
        employment_type="",
        salary="",
        recruiter_name=sender_name if "recruiter" in combined_text.lower() else "",
        recruiter_email=sender_email,
        dice_job_url="",
        source="Gmail",
        notes=f"Subject: {subject}"[:250],
    )


def fetch_gmail_applications() -> List[JobApplication]:
    """
    Search Gmail for job-application confirmation emails and parse them
    into JobApplication records. Returns [] (and logs) on failure rather
    than raising, so a Gmail outage doesn't block the Dice source.
    """
    applications: List[JobApplication] = []

    try:
        creds = _get_credentials()
        service = build("gmail", "v1", credentials=creds)

        logger.info("Searching Gmail with query: %s", SEARCH_QUERY)
        results = (
            service.users()
            .messages()
            .list(userId="me", q=SEARCH_QUERY, maxResults=config.GMAIL_MAX_RESULTS)
            .execute()
        )
        messages = results.get("messages", [])

        # Handle pagination through Gmail's API (nextPageToken).
        while "nextPageToken" in results and len(messages) < config.GMAIL_MAX_RESULTS:
            results = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=SEARCH_QUERY,
                    maxResults=config.GMAIL_MAX_RESULTS,
                    pageToken=results["nextPageToken"],
                )
                .execute()
            )
            messages.extend(results.get("messages", []))

        logger.info("Found %d candidate emails in Gmail.", len(messages))

        for m in messages:
            app = _parse_message(service, m["id"])
            if app and (app.job_title or app.company_name):
                applications.append(app)

    except FileNotFoundError as e:
        logger.error(str(e))
    except HttpError as e:
        logger.error("Gmail API error: %s", e)
    except Exception as e:
        logger.error("Gmail reading failed entirely: %s", e, exc_info=True)

    logger.info("Gmail parse complete: %d applications extracted.", len(applications))
    return applications
