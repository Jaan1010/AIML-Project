"""
models.py
---------
Defines the canonical data structure for a single job application record.
Both the Dice scraper and the Gmail reader normalize their output into
this shape so the CSV writer and dedup logic only ever deal with one
consistent schema.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional

# Canonical column order used everywhere (CSV header, dict keys, etc.)
FIELDNAMES = [
    "Company Name",
    "Job Title",
    "Job ID",
    "Date Applied",
    "Application Status",
    "Job Location",
    "Employment Type",
    "Salary",
    "Recruiter Name",
    "Recruiter Email",
    "Dice Job URL",
    "Source",
    "Notes",
]


@dataclass
class JobApplication:
    company_name: str = ""
    job_title: str = ""
    job_id: str = ""
    date_applied: str = ""
    application_status: str = ""
    job_location: str = ""
    employment_type: str = ""
    salary: str = ""
    recruiter_name: str = ""
    recruiter_email: str = ""
    dice_job_url: str = ""
    source: str = ""
    notes: str = ""

    def to_csv_row(self) -> dict:
        """Return a dict keyed by the canonical FIELDNAMES, for csv.DictWriter."""
        return {
            "Company Name": self.company_name.strip(),
            "Job Title": self.job_title.strip(),
            "Job ID": self.job_id.strip(),
            "Date Applied": self.date_applied.strip(),
            "Application Status": self.application_status.strip(),
            "Job Location": self.job_location.strip(),
            "Employment Type": self.employment_type.strip(),
            "Salary": self.salary.strip(),
            "Recruiter Name": self.recruiter_name.strip(),
            "Recruiter Email": self.recruiter_email.strip(),
            "Dice Job URL": self.dice_job_url.strip(),
            "Source": self.source.strip(),
            "Notes": self.notes.strip(),
        }

    def dedup_key(self) -> tuple:
        """
        Key used to identify "the same application" across runs and sources.

        Priority:
          1. Dice Job URL / Job ID (most reliable, when present)
          2. Fallback: normalized (company, title, date) triple
        """
        if self.dice_job_url:
            return ("url", self.dice_job_url.strip().lower())
        if self.job_id:
            return ("job_id", self.job_id.strip().lower())
        return (
            "ct",
            self.company_name.strip().lower(),
            self.job_title.strip().lower(),
            self.date_applied.strip().lower(),
        )
