"""
sources/dice_scraper.py
------------------------
Logs into Dice.com and scrapes the "Applied Jobs" section of the user's
dashboard using Playwright.

IMPORTANT — Dice's site markup changes periodically and it runs bot
detection (rate limiting, CAPTCHAs, login challenges). This module is
built defensively:

  1. It reuses a saved browser session (storage_state) so you only have
     to do a real interactive login occasionally, not on every run.
  2. It runs headful (visible browser) by default — headless automation
     is far more likely to be flagged.
  3. If automated login fails or a CAPTCHA/2FA challenge is detected, it
     pauses and asks YOU to complete the login/challenge manually in the
     open browser window, then continues automatically once you press Enter.
  4. Selectors are centralized in `SELECTORS` below. If Dice changes its
     HTML, you should only need to update this one dict.

If Dice actively blocks automated access (persistent CAPTCHAs, account
flags, legal/ToS concerns), see the "Dice blocks scraping" section of the
README for the recommended fallback: rely on the Gmail source instead,
since Dice/company ATS systems almost always send an email confirmation
when you apply.
"""

import re
import time
from typing import List

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import config
import logger_setup
from models import JobApplication

logger = logger_setup.get_logger(__name__)

LOGIN_URL = "https://www.dice.com/dashboard/login"

# Centralized selectors — update here if Dice changes its markup.
SELECTORS = {
    "email_input": "input[type='email'], input[name='email'], #email",
    "password_input": "input[type='password'], input[name='password'], #password",
    "submit_button": "button[type='submit']",
    # Applied jobs list — Dice renders each application as a card/row.
    "applied_job_card": "[data-testid='applied-job-card'], .applied-job-card, .card.search-card",
    "job_title": "[data-testid='job-title'], .card-title-link, h5 a",
    "company_name": "[data-testid='company-name'], .card-company, .company-name",
    "job_location": "[data-testid='job-location'], .location, .card-location",
    "date_applied": "[data-testid='date-applied'], .applied-date, time",
    "application_status": "[data-testid='application-status'], .status-badge, .application-status",
    "employment_type": "[data-testid='employment-type'], .employment-type",
    "salary": "[data-testid='salary'], .salary",
    "job_link": "a[href*='/job-detail/'], a.card-title-link",
    "next_page_button": "button[aria-label='Next'], a[aria-label='Next'], .pagination-next:not(.disabled)",
    # Signals that a CAPTCHA / bot challenge appeared.
    "captcha_indicator": "iframe[src*='captcha'], #challenge-running, .cf-challenge",
}


class DiceLoginError(Exception):
    pass


def _looks_like_challenge(page) -> bool:
    try:
        return page.locator(SELECTORS["captcha_indicator"]).count() > 0
    except Exception:
        return False


def _extract_job_id_from_url(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/job-detail/([a-zA-Z0-9\-]+)", url)
    return match.group(1) if match else ""


def _safe_text(locator) -> str:
    try:
        if locator.count() == 0:
            return ""
        return locator.first.inner_text(timeout=2000).strip()
    except Exception:
        return ""


def _login(page, context) -> None:
    logger.info("Navigating to Dice login page...")
    page.goto(LOGIN_URL, timeout=config.DICE_NAV_TIMEOUT_MS)

    if not config.DICE_EMAIL or not config.DICE_PASSWORD:
        logger.warning(
            "DICE_EMAIL / DICE_PASSWORD not set in environment. "
            "Please log in manually in the browser window."
        )
        input("Press Enter here once you have logged into Dice manually...")
        return

    try:
        page.wait_for_selector(SELECTORS["email_input"], timeout=10000)
        page.fill(SELECTORS["email_input"], config.DICE_EMAIL)
        page.click(SELECTORS["submit_button"])

        page.wait_for_selector(SELECTORS["password_input"], timeout=10000)
        page.fill(SELECTORS["password_input"], config.DICE_PASSWORD)
        page.click(SELECTORS["submit_button"])

        page.wait_for_timeout(3000)

        if _looks_like_challenge(page):
            logger.warning(
                "A CAPTCHA / bot-challenge appears to have been triggered."
            )
            input(
                "Please solve the challenge / complete 2FA manually in the "
                "open browser window, then press Enter here to continue..."
            )
    except PlaywrightTimeoutError:
        logger.warning(
            "Automated login selectors did not match (Dice may have changed "
            "its login form). Falling back to manual login."
        )
        input("Please log in manually in the browser window, then press Enter here...")

    # Persist the session so future runs can skip login entirely.
    context.storage_state(path=config.DICE_STORAGE_STATE_PATH)
    logger.info("Saved Dice session to %s for future reuse.", config.DICE_STORAGE_STATE_PATH)


def _parse_job_card(card) -> JobApplication:
    title_el = card.locator(SELECTORS["job_title"])
    link_el = card.locator(SELECTORS["job_link"])

    job_url = ""
    try:
        if link_el.count() > 0:
            href = link_el.first.get_attribute("href") or ""
            if href.startswith("http"):
                job_url = href
            elif href:
                job_url = f"https://www.dice.com{href}"
    except Exception:
        pass

    return JobApplication(
        company_name=_safe_text(card.locator(SELECTORS["company_name"])),
        job_title=_safe_text(title_el),
        job_id=_extract_job_id_from_url(job_url),
        date_applied=_safe_text(card.locator(SELECTORS["date_applied"])),
        application_status=_safe_text(card.locator(SELECTORS["application_status"])),
        job_location=_safe_text(card.locator(SELECTORS["job_location"])),
        employment_type=_safe_text(card.locator(SELECTORS["employment_type"])),
        salary=_safe_text(card.locator(SELECTORS["salary"])),
        recruiter_name="",
        recruiter_email="",
        dice_job_url=job_url,
        source="Dice",
        notes="",
    )


def fetch_dice_applications() -> List[JobApplication]:
    """
    Log into Dice, navigate to Applied Jobs, and scrape every page.
    Returns a list of JobApplication records. Returns an empty list (and
    logs the error) rather than raising, so a Dice failure doesn't prevent
    the Gmail source from still producing a CSV.
    """
    applications: List[JobApplication] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=config.DICE_HEADLESS)

            storage_state = None
            import os
            if os.path.exists(config.DICE_STORAGE_STATE_PATH):
                storage_state = config.DICE_STORAGE_STATE_PATH
                logger.info("Reusing saved Dice session.")

            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()

            try:
                page.goto(config.DICE_APPLIED_JOBS_URL, timeout=config.DICE_NAV_TIMEOUT_MS)
                # If we got redirected to login, storage_state was missing/expired.
                if "login" in page.url:
                    _login(page, context)
                    page.goto(config.DICE_APPLIED_JOBS_URL, timeout=config.DICE_NAV_TIMEOUT_MS)
            except PlaywrightTimeoutError:
                logger.error("Timed out loading the Dice Applied Jobs page.")
                browser.close()
                return applications

            page_num = 1
            while True:
                logger.info("Scraping Dice applied jobs — page %d", page_num)
                try:
                    page.wait_for_selector(SELECTORS["applied_job_card"], timeout=15000)
                except PlaywrightTimeoutError:
                    if _looks_like_challenge(page):
                        logger.error(
                            "Dice presented a bot challenge and no applied-job "
                            "cards were found. Aborting Dice scrape for this run."
                        )
                    else:
                        logger.info("No more applied-job cards found; stopping.")
                    break

                cards = page.locator(SELECTORS["applied_job_card"])
                count = cards.count()
                logger.info("Found %d job cards on page %d.", count, page_num)

                for i in range(count):
                    try:
                        app = _parse_job_card(cards.nth(i))
                        if app.job_title or app.company_name:
                            applications.append(app)
                    except Exception as e:
                        logger.warning("Failed to parse a job card: %s", e)

                # Pagination
                next_btn = page.locator(SELECTORS["next_page_button"])
                if next_btn.count() == 0:
                    logger.info("No 'Next' pagination control found; assuming last page.")
                    break

                try:
                    next_btn.first.click(timeout=5000)
                    page.wait_for_timeout(2500)
                    page_num += 1
                except Exception:
                    logger.info("Could not click 'Next' (likely disabled); stopping pagination.")
                    break

            browser.close()

    except Exception as e:
        logger.error("Dice scraping failed entirely: %s", e, exc_info=True)

    logger.info("Dice scrape complete: %d applications extracted.", len(applications))
    return applications
