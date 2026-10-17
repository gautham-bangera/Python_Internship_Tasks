"""Download and normalize sample employees using only Python's standard library."""
import argparse
import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

URL = "https://api.slingacademy.com/v1/sample-data/files/employees.json"
LOG = logging.getLogger(__name__)
TEXT_FIELDS = ("first_name", "last_name", "email", "gender", "job_title", "department")
INT_FIELDS = ("id", "age", "years_of_experience", "salary")


def parse_json(body):
    try:
        records = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        LOG.error("Response is not valid JSON")
        raise ValueError("Response is not valid JSON") from exc
    if not isinstance(records, list):
        LOG.error("JSON root must be a list of employees")
        raise ValueError("JSON root must be a list of employees")
    return records


def fetch_employees(url=URL, attempts=3, timeout=20, delay=1, opener=None):
    """Retry connection errors, HTTP 429 and 5xx; fail fast for other HTTP errors."""
    if attempts < 1 or timeout <= 0 or delay < 0:
        raise ValueError("Invalid retry or timeout settings")
    opener = opener or urlopen
    for attempt in range(1, attempts + 1):
        try:
            with opener(url, timeout=timeout) as response:
                if response.status != 200:
                    raise HTTPError(url, response.status, "Expected HTTP 200", None, None)
                body = response.read()
            return parse_json(body)
        except HTTPError as exc:
            LOG.error("HTTP %s: %s (attempt %s/%s)", exc.code, exc.reason, attempt, attempts)
            if exc.code != 429 and not 500 <= exc.code <= 599:
                break
        except (TimeoutError, URLError, ConnectionError, OSError) as exc:
            LOG.error("Connection failed: %s (attempt %s/%s)", exc, attempt, attempts)
        if attempt < attempts:
            time.sleep(delay * 2 ** (attempt - 1))
    LOG.error("Download failed after %s attempt(s)", attempt)
    raise RuntimeError(f"Download failed after {attempt} attempt(s)")


def integer(value, field):
    # Do not silently truncate fractions or convert True to 1.
    if type(value) is int:
        result = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        result = int(value.strip())
    else:
        raise ValueError(f"{field} must be an integer")
    if result < 0 or (field == "id" and result == 0):
        raise ValueError(f"{field} is out of range")
    return result


def normalize_date(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError("Date must be a string")
    value = value.strip()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    for pattern in ("%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError("Unsupported or invalid date")


def normalize_employee(record):
    if not isinstance(record, dict):
        raise ValueError("Employee must be an object")
    result = {}
    for field in TEXT_FIELDS:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a nonempty string")
        result[field] = value.strip()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", result["email"]):
        raise ValueError("Invalid email")
    for field in INT_FIELDS:
        result[field] = integer(record.get(field), field)
    result["Full name"] = f'{result["first_name"]} {result["last_name"]}'
    years = result["years_of_experience"]
    result["designation"] = ("system engineer" if years < 3 else
                             "data engineer" if years <= 5 else
                             "senior data engineer" if years <= 10 else "lead")
    raw = record.get("phone")
    result["phone_raw"] = raw if isinstance(raw, str) or type(raw) is int else None
    phone = str(raw).strip() if isinstance(raw, str) or type(raw) is int else ""
    digits = re.sub(r"[^0-9]", "", phone)
    valid = bool(digits) and not phone.startswith("-") and re.fullmatch(r"\+?[0-9().\s-]+", phone) is not None
    result["phone"] = int(digits) if valid else None
    result["phone_status"] = "Valid Number" if valid else "Invalid Number"
    # Keep date fields separate; never infer a hire date from a birth date.
    for field, value in record.items():
        key = re.sub(r"[\s-]+", "_", field.strip().lower())
        if "date" in key.split("_"):
            if key in result:
                raise ValueError("Conflicting date fields")
            result[key] = normalize_date(value)
    result.setdefault("hire_date", None)
    return result


def normalize_records(records):
    accepted, rejected, seen = [], [], set()
    for index, record in enumerate(records, start=1):
        try:
            employee = normalize_employee(record)
            if employee["id"] in seen:
                raise ValueError("Duplicate employee ID")
            seen.add(employee["id"])
            accepted.append(employee)
        except ValueError as exc:
            LOG.warning("Rejected record %s: %s", index, exc)
            rejected.append({"record_number": index, "reason": str(exc)})
    if accepted and all(row["hire_date"] is None for row in accepted):
        LOG.warning("No hire dates available; hire_date remains null")
    return accepted, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(args.output_dir / "scraper.log", encoding="utf-8")])
    try:
        records = fetch_employees()
        accepted, rejected = normalize_records(records)
        for name, data in (("employees_raw.json", records), ("employees_cleaned.json", accepted), ("rejected_records.json", rejected)):
            (args.output_dir / name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        LOG.info("Downloaded %s employees. Accepted %s. Rejected %s.", len(records), len(accepted), len(rejected))
        return 0 if accepted and not rejected else 2
    except (RuntimeError, ValueError, OSError) as exc:
        LOG.error("Scraper failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
