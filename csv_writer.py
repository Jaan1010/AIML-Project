"""
csv_writer.py
-------------
Handles reading the existing applied_jobs.csv (if any) and writing the
merged, de-duplicated result back out. Uses an atomic write (write to temp
file, then replace) so a crash mid-write never corrupts the existing CSV.
"""

import csv
import os
import tempfile
from pathlib import Path
from typing import Dict, List

from models import FIELDNAMES

import logger_setup

logger = logger_setup.get_logger(__name__)


def read_existing_csv(path: str) -> List[Dict[str, str]]:
    """Read the existing CSV into a list of dict rows. Returns [] if absent."""
    p = Path(path)
    if not p.exists():
        logger.info("No existing CSV found at %s; starting fresh.", path)
        return []

    try:
        with p.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = [dict(row) for row in reader]
        logger.info("Loaded %d existing rows from %s.", len(rows), path)
        return rows
    except (OSError, csv.Error) as e:
        logger.error("Failed to read existing CSV at %s: %s", path, e)
        # Better to start empty than to crash the whole pipeline; the old
        # file remains untouched on disk since we never opened it for writing.
        return []


def write_csv_atomic(path: str, rows: List[Dict[str, str]]) -> None:
    """Write rows to `path` atomically, sorted by Date Applied (desc) then Company."""
    out_dir = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(out_dir, exist_ok=True)

    def sort_key(row):
        # Newest first; unparseable/empty dates sink to the bottom.
        return (row.get("Date Applied", "") == "", row.get("Date Applied", ""))

    rows_sorted = sorted(rows, key=sort_key, reverse=False)

    fd, tmp_path = tempfile.mkstemp(dir=out_dir, prefix=".applied_jobs_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in rows_sorted:
                writer.writerow({k: row.get(k, "") for k in FIELDNAMES})
        os.replace(tmp_path, path)
        logger.info("Wrote %d rows to %s.", len(rows_sorted), path)
    except OSError as e:
        logger.error("Failed to write CSV to %s: %s", path, e)
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
