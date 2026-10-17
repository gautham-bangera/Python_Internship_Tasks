"""Command-line entry point for the employee ZIP scraper."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from employee_scraper.download import (
    DEFAULT_RETRY_DELAY_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_ZIP_URL,
)
from employee_scraper.exceptions import EmployeeScraperError
from employee_scraper.pipeline import run_pipeline

logger = logging.getLogger("employee_scraper.main")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download an employee ZIP file, validate the Excel data, "
            "and save a CSV for downstream data warehouse ingestion."
        )
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_ZIP_URL,
        help="ZIP file URL. Defaults to the Employee Sample Data link.",
    )
    parser.add_argument(
        "--work-dir",
        default=".",
        help="Folder for downloads, extracted files, the CSV, and the log.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Seconds to wait for each download attempt.",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=DEFAULT_RETRY_DELAY_SECONDS,
        help="Seconds to wait between download attempts.",
    )
    parser.add_argument("--dummy-contacts", action="store_true",
                        help="DEMO ONLY: fill absent email/phone columns with dummy values.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_pipeline(
            url=args.url,
            work_dir=Path(args.work_dir),
            timeout=args.timeout,
            retry_delay=args.retry_delay,
            dummy_contacts=args.dummy_contacts,
        )
    except EmployeeScraperError as exc:
        # Logging may already be configured. Fall back to the console if it is not.
        if logger.handlers or logging.getLogger("employee_scraper").handlers:
            logger.error("%s", exc)
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if result.preparation_complete:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
