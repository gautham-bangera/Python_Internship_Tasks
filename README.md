# Employee API Scraper

Python internship task: retrieve, validate and normalize employee JSON for later warehouse ingestion. Uses Python 3.10+ and only the standard library; no pip packages required.

Source: https://api.slingacademy.com/v1/sample-data/files/employees.json

## Run in VS Code on Windows

1. Extract this ZIP. Open the extracted `employee-api-scraper` folder in VS Code (File > Open Folder). The Explorer must show `scraper.py` and `tests` directly.
2. Install the Microsoft Python extension if it is not already available.
3. Open Terminal > New Terminal. Run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scraper.py
```

If Python 3.12 is unavailable, use `py -m venv .venv` with installed Python 3.10 or newer. No environment activation is needed, avoiding PowerShell activation restrictions.

4. Press Ctrl+Shift+P > Python: Select Interpreter > choose `.venv\Scripts\python.exe`.
5. Inspect `output/employees_cleaned.json`, `output/rejected_records.json` and `output/scraper.log`. Raw downloaded data is in `output/employees_raw.json`.

Tests use mocked HTTP responses and work offline. Running `scraper.py` requires internet access. Exit code 0 means nonempty data with no rejected rows; 1 means a download/parsing/output failure; 2 means empty data or rejected records that need review. Check the latest terminal result and log before using outputs, since a failed download does not remove files from an earlier run.

## Mapping and assumptions

| Output field | Type | Rule |
|---|---|---|
| id | integer | Positive employee ID; duplicate IDs rejected |
| first_name, last_name | string | Required, trimmed |
| Full name | string | First name + space + last name; exact requested key |
| email | string | Required, basic email syntax validation |
| phone | integer or null | Formatting stripped; x/X or invalid/missing phone gives null |
| phone_raw | string, integer or null | Original phone retained, including leading zeroes |
| phone_status | string | Valid Number or Invalid Number |
| gender, job_title, department | string | Required, nonempty |
| age, years_of_experience, salary | integer | Nonnegative; integer strings accepted; fractions and booleans rejected |
| designation | string | Under 3: system engineer; 3–5: data engineer; 6–10: senior data engineer; above 10: lead |
| hire_date | string or null | YYYY-MM-DD if supplied; otherwise null |

The brief overlaps at five years; this implementation assigns five to data engineer. Confirm this boundary with the mentor if a different policy is intended.

The phone requirement conflicts with storing the text "Invalid Number" in an integer column. This implementation keeps `phone` nullable and puts that text in `phone_status`. Phone validation checks permitted formatting, not real-world reachability. Conversion to integer loses leading zeroes, so `phone_raw` preserves the source representation.

All source keys containing a separate word `date` (e.g. `Hire Date`, `hire_date`, `date_of_birth`) are normalized to lowercase underscore keys and ISO dates. Accepted inputs: YYYY-MM-DD, ISO datetime, DD/MM/YYYY and YYYY/MM/DD. Slash day/month dates use day-first interpretation. Invalid dates reject the record. Birth dates never substitute for hire dates. Unmapped, non-date extra fields are omitted.

Missing/invalid required fields reject only that record. Missing or invalid phones remain accepted with null and status. Rejection output identifies source row numbers and reasons; raw input is saved separately. An invalid JSON root fails the entire run. JSON validity is checked by parsing the body, not by trusting a filename or Content-Type header.

HTTP errors are logged with status and reason. Connection failures, timeouts, HTTP 429 and 5xx get at most three attempts with 1- and 2-second waits, and a 20-second request timeout. Other non-200 statuses fail immediately. Invalid JSON is not retried.

Optional external currency conversion is not implemented: source and target currencies were not specified. Salaries are preserved as provided; no currency is inferred. Actual warehouse loading is outside this project because no connection or target schema was supplied.

## Unit tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The first five tests cover the requested download, extraction, format, structure and invalid-data cases. Additional tests cover designation boundaries, phone formats, date parsing, invalid types, HTTP errors, retry limits, backoff, duplicate IDs and invalid JSON without retry.

## Upload to GitHub and get a commit link

Use an approved repository. For confidential internship work, use a private repository and give the mentor access before sharing. Do not upload credentials, `.venv`, logs or generated employee data; `.gitignore` excludes them.

1. On GitHub, create an empty repository called `employee-api-scraper`. Leave README, license and .gitignore initialization unchecked because this folder already has files.
2. In the VS Code terminal inside this project, run:

```powershell
git init
git add .
git status
git commit -m "Add employee API scraper and unit tests"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/employee-api-scraper.git
git push -u origin main
```

Replace YOUR_USERNAME with your actual GitHub username. These instructions assume a NEW repository; do not replace the remote of an existing unrelated project. If Git asks for your identity, set `git config user.name "Your Name"` and `git config user.email "YOUR_GITHUB_EMAIL"`, then retry the commit. Authenticate through Git's normal sign-in prompt; never put an access token in source code or send it in email.

3. Run `git rev-parse HEAD` to get the full commit SHA.
4. Your commit link is `https://github.com/YOUR_USERNAME/employee-api-scraper/commit/FULL_COMMIT_SHA`. You can also open the latest commit on the repository website and copy its address.
5. Check that the mentor has access to the private repository. A link alone does not grant access.

## Gmail submission

Use the mentor's address in To. Put any additional recipient who should receive a copy in Cc. Check the actual addresses before sending.

Subject: Employee API Scraper – Task Submission

Dear [Mentor Name],

I have completed the employee API scraper with data validation, normalization, error handling and unit tests.

Commit link: [paste the actual GitHub commit link]

The README includes the steps to run the project in VS Code and explains the assumptions used. Please review and share your feedback.

Regards,
Gautham

Send this only after the tests pass on your laptop and the commit has been pushed successfully.
