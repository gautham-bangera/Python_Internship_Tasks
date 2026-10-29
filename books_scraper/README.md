# Books to Scrape — Book Data Scraper

## Purpose and business flow
A data analyst needs a consistent catalogue snapshot to compare prices, ratings and stock status. This project reads the Books to Scrape practice website, validates each book and exports a CSV suitable for Excel, pandas or a data warehouse.

Business flow: analyst starts the program → download homepage → extract and validate each book → log and skip invalid books → follow Next links → remove duplicate product URLs → write books_data.csv → analyst reviews logs and analyzes the CSV.

The website is a demonstration catalogue. Its ratings and prices are practice data, not evidence of real market demand. A single run is a snapshot; measuring changes over time requires keeping dated exports from repeated runs.

## Files
- `scraper.py`: HTTP retrieval, parsing, validation, pagination, CSV export and CLI.
- `test_scraper.py`: offline acceptance and failure tests.
- `requirements.txt`: runtime dependencies. Tests use Python's built-in unittest.
- `books_data.csv`: generated output; includes a verified 1,000-book sample snapshot.
- `scraper.log`: execution and rejected-book details (excluded from Git).

## Setup (Python 3.10 or later)
From the repository root, run:

```powershell
cd books_scraper
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

On Linux/macOS, activate with `source .venv/bin/activate`.

## Run
```sh
# All pages; writes books_data.csv in the current directory
python scraper.py

# Homepage only (normally 20 books)
python scraper.py --max-pages 1 --output homepage_books.csv

# Tests, run from books_scraper
python -m unittest -v
```

A full catalogue normally contains about 1,000 books over 50 pages. The program follows actual pagination instead of hard-coding those counts. Counts can be lower when records are rejected or the website changes. Exit code 0 means the selected page range completed and the CSV was saved; exit code 1 means failure. Inspect logs for rejected records even after a successful run.

## Output contract
CSV columns are exactly `Title,Price,Rating,Availability,URL` in that order.

| Column | Meaning and validation |
| --- | --- |
| Title | Nonempty full title from the link's title attribute |
| Price | GBP amount with two decimal places, e.g. 51.77; currency symbol removed for analysis |
| Rating | Integer 1–5, mapped from One–Five CSS classes |
| Availability | In stock or Out of stock; normalized whitespace/case |
| URL | Absolute HTTP(S) product link on books.toscrape.com |

UTF-8 encoding preserves non-ASCII titles. Python's CSV writer quotes commas and quotation marks correctly. The source serves HTML, not a downloadable CSV: the application creates the CSV after extracting HTML data. No stock quantity or book-detail page fields are claimed.

## Design and error handling
1. Use one requests Session, a 20-second request timeout and an educational User-Agent.
2. Parse each `article.product_pod` with BeautifulSoup. Read the untruncated title attribute, price, star-rating classes, availability and link.
3. Reject the entire book if any required field is missing or invalid. Log page URL, card number and reason; continue with other cards.
4. Resolve relative Next and product links against the current page. Reject external links, detect pagination loops and deduplicate by product URL.
5. Wait 0.25 seconds between successful pages. Retry connection errors, timeouts, HTTP 429 and server errors up to three total attempts with 1- and 2-second backoff. Permanent errors such as 404 are not retried.
6. Stop with a clear error if a page remains unavailable or has no book cards. Since the next page cannot reliably be inferred after failure, no partial catalogue CSV is published.
7. Write to a temporary CSV and then replace the target. Existing output is preserved on retrieval/validation failures. Missing output directories or write-permission failures are reported. The output path must end in .csv.

Records are collected in memory before export, which is appropriate for this approximately 1,000-book exercise. Run one instance per output path. Site markup changes may require selector updates. Treat imported titles as text in spreadsheet software.

## Test plan
The tests use controlled HTML and mocked HTTP, so they do not depend on internet access or live catalogue changes.

| Required case | Verification |
| --- | --- |
| 1. CSV file download | Mock homepage fetch with 20 books, export and count 20 CSV records |
| 2. CSV extraction | Read exported CSV back; verify values, comma quoting and Unicode |
| 3. File type/format | Reject non-CSV extension; verify exact header and CSV line endings |
| 4. Data structure | Verify all five fields, all five rating mappings and out-of-stock status |
| 5. Missing/invalid data | Invalid title, price, rating, stock, URL and missing node are logged and skipped; valid book survives |

Additional tests cover pagination, duplicate URLs, 503 recovery, 404 without retry, timeout retry limits, empty pages and pagination loops.

For a live acceptance check, run the homepage command and full command, then open both CSVs and confirm the logged counts match their data rows. A live run needs network access to books.toscrape.com. Offline test success alone does not prove the current website is accessible.

## Review workflow
This task is isolated in `books_scraper/` on branch `books-data-scraper`. Its pull request targets `main`. The mentor can review the code, documentation and test results, request changes, then merge when approved.
