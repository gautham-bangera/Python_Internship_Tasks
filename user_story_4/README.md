# User Story 4 — Book Data Scraper

Extract the catalogue from https://books.toscrape.com/ and generate `books_data.csv`
for analysis of prices, ratings and availability. This is a demonstration website;
its prices and ratings are synthetic, so they do not establish real market trends.

## Setup and run

Python 3.10 or later is recommended. From the repository root, open a terminal:

```text
cd user_story_4
python -m venv .venv
```

Windows Command Prompt:

```bat
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python scraper.py
python -m unittest -v test_scraper
```

Ubuntu:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python scraper.py
python -m unittest -v test_scraper
```

Use `python3 -m venv .venv` on Ubuntu if `python` is not available before activation.
Run the commands inside `user_story_4`, not the repository root.

Full catalogue (default, approximately 1,000 books across 50 pages):

```bash
python scraper.py
```

Homepage only (20 books when all source records are valid):

```bash
python scraper.py --max-pages 1 --output homepage_books.csv
```

Change destination or request interval:

```bash
python scraper.py --output output/books_data.csv --delay 0.5
```

The output path is relative to the current working directory. A successful run
returns exit code 0; a failed run returns 1 and logs an explanation. Logs go to the
terminal; append `2> scraper.log` to a command to retain them. CSVs produced by the
default command are ignored by Git because they are reproducible outputs.

## Business flow

1. The analyst starts a full-catalogue run or chooses a homepage preview.
2. The program downloads the HTML listing page using HTTPS and a 20-second timeout.
3. It identifies each book card and extracts the full title, GBP price, rating,
   stock status and product link. It does not need to visit individual book pages.
4. It validates the required fields. A malformed record is logged and skipped;
   no dummy values are inserted. Duplicate product URLs are excluded.
5. It follows the actual Next link until the final page (or the requested page limit).
6. After the requested traversal succeeds, it writes a temporary CSV and replaces
   `books_data.csv` atomically. A failed page does not overwrite a prior successful
   CSV with incomplete results.
7. The analyst opens the CSV in Excel, Python or another analysis tool. Review the
   logged skipped-record count before using the data; a completed traversal can
   legitimately contain fewer rows when the source has invalid records.

## CSV schema

| Column | Representation | Validation |
| --- | --- | --- |
| Title | Full title text | Nonempty HTML title attribute |
| Price | Decimal text, e.g. `51.77` | Nonnegative GBP amount with two decimal places |
| Rating | Integer 1–5 | HTML One/Two/Three/Four/Five class mapped to a number |
| Availability | `In stock` or `Out of stock` | Whitespace normalized, known values only |
| URL | Absolute product URL | HTTP(S) URL on books.toscrape.com |

Exact header order: `Title,Price,Rating,Availability,URL`. All prices are GBP; the
pound sign is removed to simplify numeric analysis. CSV uses UTF-8, comma delimiters
and standard quoting for titles containing commas or quotation marks. CSV itself
has no typed cells; ratings and prices become text on a basic CSV read and should
be converted to numeric types for analysis. Decimal is used for price formatting.

## Error handling and limits

- HTTP 408, 429, 500, 502, 503 and 504 are retried up to three total attempts,
  with waits of 1 and 2 seconds. Connection failures and timeouts use the same limit.
- Permanent HTTP errors such as 404 stop that run without retrying indefinitely.
- Non-HTML responses, decoding failures, empty listing pages, broken Next links
  and pagination cycles stop the run with a logged error.
- Missing or invalid individual book fields are logged without crashing the run.
- A file-write failure preserves the prior destination and removes the temporary file.
- The program does not bypass access restrictions, execute JavaScript, load a
  warehouse or send email. It depends on the website's current HTML structure.
- An older CSV may remain after a failed run: check the exit code and logs instead
  of assuming an existing file represents today's successful scrape.

## Tests and acceptance criteria

The supplied story calls its first two tests “CSV File Download” and “CSV File
Extraction.” The source serves HTML, not a downloadable CSV. Therefore the tests
verify HTML download followed by CSV generation, and then reading the generated CSV.

| Acceptance test | Automated check |
| --- | --- |
| 1. CSV file download | Mock HTML download produces a nonempty CSV through the CLI |
| 2. CSV file extraction | Generated CSV can be read with intact comma-containing title and values |
| 3. File type and format | Reject non-CSV destinations and non-HTML source responses |
| 4. Data structure | Exact columns, rating type, normalized status and absolute URL |
| 5. Missing or invalid data | Eight malformed records skipped and logged; valid book survives |

Additional offline tests cover 20-book homepage mode, pagination, URL resolution,
duplicates, all five ratings, out-of-stock status, retries, 404, timeouts, failed
second pages, atomic output, bad CLI arguments, invalid pages and pagination loops.
Fixtures are synthetic test data, not scraped results. No network is required for
the unit tests. A separate live run is needed to verify the current website.

## Code layout and review

- `scraper.py`: HTTP retrieval, extraction, validation, pagination, CSV writer and CLI.
- `test_scraper.py`: isolated unittest tests with mocked HTTP responses.
- `requirements.txt`: Beautiful Soup HTML parser dependency.

Create the PR from `user-story-4` to the mentor's target branch (`main` by default).
Include the test results and any live-run limitations in the PR description. Send
the resulting PR link to the original assignment email's CC recipients for review.
Do not merge until the team's review process is complete.
