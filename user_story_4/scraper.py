"""Scrape Books to Scrape into a validated CSV. Run `python scraper.py --help`."""

import argparse
import csv
import logging
import os
import re
import tempfile
import time
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
COLUMNS = ["Title", "Price", "Rating", "Availability", "URL"]
RATINGS = {word: number for number, word in enumerate(
    ["One", "Two", "Three", "Four", "Five"], start=1)}
LOG = logging.getLogger(__name__)


class ScrapeError(Exception):
    """A page could not be fetched or its structure was invalid."""


def site_url(base, href):
    """Resolve relative links, rejecting blank or off-site URLs."""
    if not href or not href.strip():
        raise ValueError("Missing URL")
    result = urljoin(base, href.strip())
    parsed = urlparse(result)
    if (parsed.scheme not in {"http", "https"}
            or parsed.netloc != "books.toscrape.com"):
        raise ValueError("Invalid or off-site URL")
    return result


def fetch_page(url, attempts=3, timeout=20):
    """Retry temporary HTTP/network failures; fail immediately on permanent 4xx."""
    if attempts < 1:
        raise ValueError("attempts must be positive")
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "BookStory4Scraper/1.0"})
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise ScrapeError(f"Unexpected HTTP status {response.status}: {url}")
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "application/xhtml+xml"}:
                    raise ScrapeError(f"Expected HTML, received {content_type}: {url}")
                # Decode explicitly so the pound sign is not misread as 'Â£'.
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset)
        except HTTPError as exc:
            retryable = exc.code in {408, 429, 500, 502, 503, 504}
            LOG.warning("HTTP %s on attempt %s/%s: %s", exc.code, attempt, attempts, url)
            exc.close()
            if not retryable or attempt == attempts:
                raise ScrapeError(f"HTTP {exc.code}: {url}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            LOG.warning("Network failure on attempt %s/%s: %s (%s)",
                        attempt, attempts, url, exc)
            if attempt == attempts:
                raise ScrapeError(f"Download failed after {attempts} attempts: {url}") from exc
        except (UnicodeError, LookupError) as exc:
            raise ScrapeError(f"Invalid page encoding: {url}") from exc
        # Exponential delay is bounded by the small retry limit.
        time.sleep(2 ** (attempt - 1))


def parse_book(card, page_url):
    """Validate every required field; never invent data for an invalid book."""
    link = card.select_one("h3 a")
    price_node = card.select_one(".price_color")
    rating_node = card.select_one(".star-rating")
    availability_node = card.select_one(".availability")
    if any(node is None for node in (link, price_node, rating_node, availability_node)):
        raise ValueError("Missing title, price, rating, or availability element")
    # The title attribute contains the full title, unlike truncated display text.
    title = link.get("title", "").strip()
    if not title:
        raise ValueError("Missing full title")
    price_text = price_node.get_text(strip=True)
    if not re.fullmatch(r"£\d+\.\d{2}", price_text):
        raise ValueError(f"Invalid GBP price: {price_text!r}")
    price = format(Decimal(price_text[1:]), ".2f")
    ratings = [RATINGS[c] for c in rating_node.get("class", []) if c in RATINGS]
    if len(ratings) != 1:
        raise ValueError("Missing or invalid rating")
    availability_text = " ".join(availability_node.stripped_strings).lower()
    if availability_text not in {"in stock", "out of stock"}:
        raise ValueError(f"Invalid availability: {availability_text!r}")
    return dict(zip(COLUMNS, [title, price, ratings[0], availability_text.capitalize(),
                              site_url(page_url, link.get("href"))]))


def scrape_books(max_pages=None, delay=0.25):
    """Follow Next links; skip malformed books, but abort on an unreadable page."""
    if max_pages is not None and max_pages < 1:
        raise ValueError("max_pages must be positive")
    if delay < 0:
        raise ValueError("delay must not be negative")
    url = BASE_URL
    visited, book_urls, records = set(), set(), []
    skipped = 0
    while url:
        if url in visited:
            raise ScrapeError(f"Pagination cycle detected: {url}")
        visited.add(url)
        soup = BeautifulSoup(fetch_page(url), "html.parser")
        cards = soup.select("article.product_pod")
        if not cards:
            raise ScrapeError(f"No book cards found; page structure may have changed: {url}")
        for index, card in enumerate(cards, start=1):
            try:
                book = parse_book(card, url)
            except ValueError as exc:
                skipped += 1
                LOG.error("Skipping book %s on %s: %s", index, url, exc)
                continue
            # A repeated product should not inflate the CSV row count.
            if book["URL"] in book_urls:
                LOG.warning("Skipping duplicate product: %s", book["URL"])
                continue
            book_urls.add(book["URL"])
            records.append(book)
        LOG.info("Page %s: %s cards, %s valid books total", len(visited), len(cards), len(records))
        if max_pages is not None and len(visited) >= max_pages:
            break
        next_container = soup.select_one("li.next")
        if next_container is None:
            break
        next_link = next_container.select_one("a")
        try:
            url = site_url(url, next_link.get("href") if next_link else None)
        except ValueError as exc:
            raise ScrapeError("Invalid pagination link") from exc
        time.sleep(delay)
    if not records:
        raise ScrapeError("No valid books found; no CSV written")
    LOG.info("Finished: pages=%s, saved=%s, invalid=%s", len(visited), len(records), skipped)
    return records


def write_csv(records, output):
    """Write UTF-8 CSV atomically, preserving the previous file if writing fails."""
    output = Path(output)
    if output.suffix.lower() != ".csv":
        raise ValueError("Output filename must end with .csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(records)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="books_data.csv")
    parser.add_argument("--max-pages", type=int, help="Use 1 to scrape only the homepage")
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between pages")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if Path(args.output).suffix.lower() != ".csv":
            raise ValueError("Output filename must end with .csv")
        # Only publish the CSV after every requested page has been read successfully.
        records = scrape_books(args.max_pages, args.delay)
        write_csv(records, args.output)
    except (ScrapeError, OSError, ValueError) as exc:
        LOG.error("Scrape failed: %s", exc)
        return 1
    LOG.info("Saved %s books to %s", len(records), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
