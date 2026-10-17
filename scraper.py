"""Download employee CSV and fill missing Hire Dates with labeled dummy dates."""

import csv
import io
import json
import logging
import random
import re
import time

from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


URL = (
    "https://drive.google.com/uc"
    "?id=1AWPf-pJodJKeHsARQK_RHiNsE8fjPCVK"
    "&export=download"
)

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
MAX_FILE_SIZE = 20 * 1024 * 1024

DUMMY_DATE_START = date(2020, 1, 1)
DUMMY_DATE_END = date(2025, 12, 31)
DUMMY_DATE_SPAN = (DUMMY_DATE_END - DUMMY_DATE_START).days

logger = logging.getLogger("employee_scraper")

FIELD_MAPPING = {
    "User Id": "employee_id",
    "First Name": "first_name",
    "Last Name": "last_name",
    "Email": "email",
    "Job Title": "job_title",
    "Phone": "phone",
}

EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")
DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_csv(content):
    """Validate and parse a UTF-8 CSV file."""
    if not content:
        raise ValueError("The downloaded file is empty.")

    if content.startswith((b"PK\x03\x04", b"\xd0\xcf\x11\xe0")):
        raise ValueError(
            "Excel/archive file detected. This program supports CSV only."
        )

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("Expected a UTF-8 CSV file.") from error

    if text.lstrip().startswith("<"):
        raise ValueError(
            "Received HTML/XML instead of CSV. Check Google Drive permissions."
        )

    if "\x00" in text:
        raise ValueError("Unexpected binary content.")

    try:
        reader = csv.DictReader(
            io.StringIO(text, newline=""),
            strict=True,
        )

        if not reader.fieldnames:
            raise ValueError("CSV header is missing.")

        headers = [name.strip() for name in reader.fieldnames]

        if any(not name for name in headers):
            raise ValueError("CSV contains an empty column name.")

        if len(headers) != len(set(headers)):
            raise ValueError("CSV contains duplicate column names.")

        missing = set(FIELD_MAPPING) - set(headers)

        if missing:
            raise ValueError(
                "Missing required CSV columns: "
                + ", ".join(sorted(missing))
            )

        reader.fieldnames = headers
        rows = list(reader)

    except csv.Error as error:
        raise ValueError("Malformed CSV file.") from error

    if not rows:
        raise ValueError("CSV contains no employee records.")

    return headers, rows


def download_file(url, destination, attempts=3, delay=1, opener=None):
    """Download CSV with limited retries, then validate before saving."""
    if attempts < 1 or delay < 0:
        raise ValueError("Invalid retry configuration.")

    opener = urlopen if opener is None else opener
    content = None

    for attempt in range(1, attempts + 1):
        try:
            with opener(url, timeout=20) as response:
                if response.status != 200:
                    raise HTTPError(
                        url,
                        response.status,
                        "Expected HTTP 200",
                        None,
                        None,
                    )

                downloaded = response.read(MAX_FILE_SIZE + 1)

            content = downloaded
            break

        except HTTPError as error:
            logger.warning(
                "Download attempt %d/%d: HTTP %d.",
                attempt,
                attempts,
                error.code,
            )

        except (URLError, TimeoutError, ConnectionError) as error:
            logger.warning(
                "Download attempt %d/%d failed: %s.",
                attempt,
                attempts,
                type(error).__name__,
            )

        if attempt < attempts:
            time.sleep(delay * attempt)

    if content is None:
        logger.error("Download failed after %d attempts.", attempts)
        raise RuntimeError(
            f"Download failed after {attempts} attempts. "
            "Check your connection and Google Drive access."
        )

    if len(content) > MAX_FILE_SIZE:
        raise ValueError("Downloaded file exceeds the 20 MB limit.")

    headers, rows = parse_csv(content)

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")

    try:
        temporary.write_bytes(content)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)

    logger.info("Downloaded CSV containing %d records.", len(rows))
    return headers, rows


def normalize_date(value, field):
    """Validate a date or return None for an absent or blank value."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field} must be text in YYYY-MM-DD format.")

    text = value.strip()

    if not text:
        return None

    if not DATE_PATTERN.fullmatch(text):
        raise ValueError(f"{field} must use YYYY-MM-DD.")

    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} contains an invalid date.") from error


def generate_dummy_hire_date():
    """Generate a synthetic date within the configured inclusive range."""
    offset = random.randint(0, DUMMY_DATE_SPAN)
    return (DUMMY_DATE_START + timedelta(days=offset)).isoformat()


def map_employee(row):
    """Preserve source values and fill only missing or blank Hire Dates."""
    if None in row or any(value is None for value in row.values()):
        raise ValueError("Record has an incorrect number of columns.")

    employee = {}

    for source, target in FIELD_MAPPING.items():
        value = row.get(source)

        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{source} is missing or empty.")

        employee[target] = value.strip()

    if not EMAIL_PATTERN.fullmatch(employee["email"]):
        raise ValueError("Email format is invalid.")

    hire_date = normalize_date(row.get("Hire Date"), "Hire Date")

    employee["hire_date_is_dummy"] = hire_date is None
    employee["hire_date"] = (
        generate_dummy_hire_date()
        if hire_date is None
        else hire_date
    )

    employee["date_of_birth"] = normalize_date(
        row.get("Date of birth"),
        "Date of birth",
    )

    employee["sex"] = row.get("Sex", "").strip() or None

    return employee


def process_employees(rows):
    """Separate accepted and rejected records, rejecting duplicate IDs."""
    accepted = []
    rejected = []
    seen_ids = set()

    for record_number, row in enumerate(rows, start=1):
        try:
            employee = map_employee(row)
            employee_id = employee["employee_id"]

            if employee_id in seen_ids:
                raise ValueError("Duplicate employee ID.")

            seen_ids.add(employee_id)
            accepted.append(employee)

        except ValueError as error:
            rejected.append({
                "record_number": record_number,
                "reason": str(error),
            })

    return accepted, rejected


def save_json(path, data):
    """Write JSON through a temporary file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")

    try:
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )

        temporary.replace(path)

    finally:
        temporary.unlink(missing_ok=True)


def main():
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s: %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(
                    OUTPUT_DIR / "scraper.log",
                    encoding="utf-8",
                ),
            ],
        )

        headers, rows = download_file(
            URL,
            OUTPUT_DIR / "employees_raw.csv",
        )

        accepted, rejected = process_employees(rows)

        dummy_count = sum(
            employee["hire_date_is_dummy"]
            for employee in accepted
        )

        summary = {
            "file_type": "CSV",
            "downloaded": len(rows),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "missing_hire_dates": sum(
                employee["hire_date"] is None
                for employee in accepted
            ),
            "dummy_hire_dates": dummy_count,
            "dummy_hire_date_range": (
                f"{DUMMY_DATE_START.isoformat()} to "
                f"{DUMMY_DATE_END.isoformat()}"
            ),
            "source_hire_date_column_missing": "Hire Date" not in headers,
            "notice": (
                "Dummy Hire Dates are random synthetic demo data. "
                "No warehouse loading is performed."
            ),
        }

        save_json(OUTPUT_DIR / "employees_cleaned.json", accepted)
        save_json(OUTPUT_DIR / "rejected_records.json", rejected)
        save_json(OUTPUT_DIR / "summary.json", summary)

        if not accepted:
            raise ValueError(
                "No valid employees. Check rejected_records.json."
            )

        if dummy_count:
            logger.info(
                "DEMO: assigned random dummy Hire Dates to %d records.",
                dummy_count,
            )

        logger.info(
            "Finished: %d accepted, %d rejected.",
            len(accepted),
            len(rejected),
        )

        print("\nRESULT")
        print(json.dumps(summary, indent=2))
        print("\nFiles saved in:", OUTPUT_DIR)
        return 0

    except (RuntimeError, ValueError, OSError) as error:
        logger.error("Task failed: %s", error)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())