## Demo contact columns (added)

Run `python main.py --dummy-contacts` to fill missing email and phone columns.
Emails use `demo.employee1@example.com`, etc. Phone values are `0000000000`.
These are synthetic placeholders, not real contacts. Existing contact columns
are preserved and validated normally. Source-missing columns remain recorded in
the report. Demo completion returns exit code 0 when all other required columns
exist and valid rows were exported; production ingestion readiness remains false.
Without the flag, the original strict behavior remains.

# Employee Data Scraper from ZIP File

This program downloads an employee ZIP file, checks that the download is a real ZIP, extracts it, chooses the employee Excel file, and writes a CSV of valid rows. The CSV is prepared for a later data warehouse load. This program does not load data into a warehouse.

Default ZIP URL:

`https://www.thespreadsheetguru.com/wp-content/uploads/2022/12/EmployeeSampleData.zip`

## Requirements

- Python 3.10 or newer
- Internet access when you run the live download

## Installation

Open a terminal in this project folder (`userstory3`). On this computer, `py -3` points at a Python install that is not there, so create the virtual environment with Python 3.13:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `py -3` works on your machine, this is the same setup:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks the activate script, run this once in the same terminal and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## Run the program

From the project folder, with the virtual environment active:

```powershell
python main.py
```

Without activating the environment:

```powershell
.\.venv\Scripts\python.exe main.py
```

Useful options:

```powershell
python main.py --help
python main.py --work-dir .
python main.py --timeout 30 --retry-delay 2
```

The program tries the download at most 3 times. Each try waits up to 30 seconds. After a failed try it waits 2 seconds, logs the error, and tries again.

Exit code `0` means every required column was found and at least one valid row was written. Exit code `1` means the download failed, a required column is missing, or no valid row was exported. A partial CSV may still be written. Read the report before using it.

## Output files

| Path | Contents |
| --- | --- |
| `downloads/EmployeeSampleData.zip` | The downloaded archive |
| `extracted/` | Files taken out of the ZIP |
| `output/employees.csv` | Valid employee rows only |
| `output/validation_report.txt` | Columns, missing fields, and invalid rows |
| `logs/employee_scraper.log` | Successes, warnings, and failures |

`employees.csv` columns, when the workbook has them:

`employee_id`, `first_name`, `last_name`, `email`, `job_title`, `phone_number`, `hire_date`

Hire dates are saved as `YYYY-MM-DD`. Employee IDs and phone numbers are written as text. A blank is not invented when a required column is absent.

## Project structure

```text
main.py                          Command-line program
requirements.txt                 Python packages
employee_scraper/download.py     Download the ZIP (max 3 attempts)
employee_scraper/zip_archive.py  Check the ZIP and extract it safely
employee_scraper/discovery.py    Find .xlsx and .xls files and choose one
employee_scraper/excel_reader.py Open workbooks and reject damaged files
employee_scraper/columns.py      Match column-name variations
employee_scraper/validation.py   Check required fields and row values
employee_scraper/export.py       Write the CSV and validation report
employee_scraper/pipeline.py     Run the steps in order
tests/                           Automated tests (no live download)
```

## How the workbook is chosen

The ZIP can contain more than one file. The program:

- ignores folders as workbooks, but still reads Excel files inside folders
- ignores temporary Excel lock files whose names start with `~$`
- ignores hidden files and `__MACOSX` junk
- accepts only `.xlsx` and `.xls`
- skips files that do not open
- chooses the readable sheet whose headers match the most employee fields

It does not assume the first file or the first sheet is the employee data.

If the URL returns an `.xlsx` workbook directly (an Excel file is also a ZIP), extraction will not contain another spreadsheet. The program then uses that downloaded workbook and logs a warning.

## Column names

Required fields are employee ID, first name, last name, email, job title, phone number, and hire date.

Examples of accepted headers:

- Employee ID, Emp ID, EEID, ID
- First Name, Last Name
- Full Name or Employee Name (split into first and last name when those columns are missing)
- Email, E-mail, Email Address
- Job Title, Position, Role
- Phone Number, Phone, Mobile, Telephone
- Hire Date, Start Date, Date Hired

The first word of a full name becomes the first name. The rest becomes the last name. A one-word name has no last name, so that row is invalid.

Missing required columns are listed in the log and in `output/validation_report.txt`.

## Row checks

A row is left out of the CSV when:

- a required value that exists in the workbook is blank or `N/A`
- the email does not look like `name@example.com`
- the phone number contains letters or has fewer than 7 digits
- the hire date cannot be parsed
- the same employee ID already appeared on an earlier valid row

The original text is kept for IDs and phone numbers when Excel stored them as text. Numeric cells are saved without a trailing `.0`. Leading zeros that Excel already removed cannot be restored.

Slash dates such as `01/02/2020` are read as month/day/year. Year-first dates such as `2020-01-02` are accepted as written. Hire dates must fall from year 1900 through 2100.

## Tests

The tests use local files and fakes. They do not contact the ZIP URL and they do not need the internet.

```powershell
python -m pytest -q
```

Or, without activating the environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

| Test | What it checks |
| --- | --- |
| Test Case 1 | `tests/test_zip_download.py` verifies a ZIP download, timeouts, 3 attempts, and retry delays |
| Test Case 2 | `tests/test_zip_extraction.py` extracts a ZIP and chooses the employee workbook |
| Test Case 3 | `tests/test_workbook_integrity.py` rejects bad file types and damaged workbooks |
| Test Case 4 | `tests/test_employee_columns.py` maps column names and reports missing columns |
| Test Case 5 | `tests/test_invalid_employee_data.py` keeps valid rows and reports invalid ones |

## What the live ZIP contained

A run on 11 October 2026 received HTTP 200 and saved a 125,295-byte ZIP. An earlier run with a non-browser user agent received HTTP 403, so the downloader sends a browser user agent.

The archive contained `Employee Sample Data.xlsx` and `Employee Sample Data.csv`. The program ignored the CSV and used the workbook. The workbook has one sheet, `Data`, with these columns:

`EEID`, `Full Name`, `Job Title`, `Department`, `Business Unit`, `Gender`, `Ethnicity`, `Age`, `Hire Date`, `Annual Salary`, `Bonus %`, `Country`, `City`, `Exit Date`

There is no email column and no phone column. The program reports both as missing and does not invent values. `EEID` is the employee ID. `Full Name` is split into first and last name. That run read 1,000 data rows, wrote 911 rows to the CSV, and left out 89 rows because the employee ID was already used. The process exits with code 1 when required columns are missing, even though the partial CSV and the validation report are written. Nothing was loaded into a data warehouse.

## Assumptions

- The header row is one of the first 10 rows.
- The sample dates use US month/day/year when the order is ambiguous.
- `.xlsm` and `.xlsb` files are not read.
- Password-protected workbooks are reported as unreadable.
- The published ZIP may not contain every required column. The program reports the real headers instead of filling in email addresses, phone numbers, or names.
- Re-running the program replaces the `extracted` folder so old files are not selected by mistake.
