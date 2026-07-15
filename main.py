"""
main.py
-------
Entry point. Orchestrates fetching job applications from Dice and/or
Gmail, merges them with the existing CSV (deduplicated), and writes the
result back to applied_jobs.csv.

Usage:
    python main.py                  # run both sources (Dice preferred, Gmail fallback/supplement)
    python main.py --source dice    # Dice only
    python main.py --source gmail   # Gmail only
    python main.py --output custom.csv
"""

import argparse
import sys

import config
import logger_setup
from csv_writer import read_existing_csv, write_csv_atomic
from dedup import merge_records

logger = logger_setup.get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync job applications into a CSV file.")
    parser.add_argument(
        "--source",
        choices=["dice", "gmail", "both"],
        default="both",
        help="Which data source(s) to pull from (default: both).",
    )
    parser.add_argument(
        "--output",
        default=config.CSV_OUTPUT_PATH,
        help="Path to the output CSV file (default: applied_jobs.csv).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger.info("=== Job Application Tracker run starting (source=%s) ===", args.source)

    new_applications = []

    if args.source in ("dice", "both"):
        try:
            from sources.dice_scraper import fetch_dice_applications
            dice_apps = fetch_dice_applications()
            new_applications.extend(dice_apps)
        except Exception as e:
            logger.error(
                "Dice source failed unexpectedly (%s). Continuing with other "
                "sources if configured.", e, exc_info=True
            )

    if args.source in ("gmail", "both"):
        try:
            from sources.gmail_reader import fetch_gmail_applications
            gmail_apps = fetch_gmail_applications()
            new_applications.extend(gmail_apps)
        except Exception as e:
            logger.error("Gmail source failed unexpectedly: %s", e, exc_info=True)

    if not new_applications:
        logger.warning(
            "No applications were retrieved from any source this run. "
            "The existing CSV (if any) will be left unchanged."
        )

    existing_rows = read_existing_csv(args.output)
    merged_rows, num_added, num_enriched = merge_records(existing_rows, new_applications)

    try:
        write_csv_atomic(args.output, merged_rows)
    except Exception:
        logger.error("Failed to save CSV — aborting.")
        return 1

    logger.info(
        "=== Run complete: %d new application(s) added, %d existing row(s) "
        "enriched, %d total row(s) in %s ===",
        num_added, num_enriched, len(merged_rows), args.output,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
