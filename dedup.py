"""
dedup.py
--------
Merges newly-scraped/parsed JobApplication records with whatever already
exists in the CSV, without creating duplicate rows.

Strategy:
- Build a dict keyed by JobApplication.dedup_key() from the existing rows.
- For each new record, if its key already exists, we optionally enrich the
  existing row with any new non-empty fields (e.g. Gmail found a recruiter
  email that Dice didn't have) rather than dropping the information.
- If the key is new, it's appended.
"""

from typing import Dict, List

from models import JobApplication, FIELDNAMES


def _row_to_application(row: Dict[str, str]) -> JobApplication:
    return JobApplication(
        company_name=row.get("Company Name", ""),
        job_title=row.get("Job Title", ""),
        job_id=row.get("Job ID", ""),
        date_applied=row.get("Date Applied", ""),
        application_status=row.get("Application Status", ""),
        job_location=row.get("Job Location", ""),
        employment_type=row.get("Employment Type", ""),
        salary=row.get("Salary", ""),
        recruiter_name=row.get("Recruiter Name", ""),
        recruiter_email=row.get("Recruiter Email", ""),
        dice_job_url=row.get("Dice Job URL", ""),
        source=row.get("Source", ""),
        notes=row.get("Notes", ""),
    )


def merge_records(
    existing_rows: List[Dict[str, str]],
    new_applications: List[JobApplication],
) -> tuple[List[Dict[str, str]], int, int]:
    """
    Merge new_applications into existing_rows.

    Returns:
        (merged_rows, num_added, num_enriched)
    """
    existing_apps = [_row_to_application(r) for r in existing_rows]
    index_by_key = {app.dedup_key(): i for i, app in enumerate(existing_apps)}

    num_added = 0
    num_enriched = 0

    for new_app in new_applications:
        key = new_app.dedup_key()
        if key in index_by_key:
            idx = index_by_key[key]
            existing_app = existing_apps[idx]
            enriched = False
            # Fill in any blanks the existing record is missing, using the
            # new record's data, without overwriting existing populated values.
            for field_name in vars(existing_app):
                existing_val = getattr(existing_app, field_name)
                new_val = getattr(new_app, field_name)
                if not existing_val and new_val:
                    setattr(existing_app, field_name, new_val)
                    enriched = True
            if enriched:
                num_enriched += 1
                existing_apps[idx] = existing_app
        else:
            existing_apps.append(new_app)
            index_by_key[key] = len(existing_apps) - 1
            num_added += 1

    merged_rows = [app.to_csv_row() for app in existing_apps]
    return merged_rows, num_added, num_enriched
