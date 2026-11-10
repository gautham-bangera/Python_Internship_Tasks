"""Download catalogue pages, validate book cards and publish a UTF-8 CSV."""
import argparse
import csv
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE_URL = 'https://books.toscrape.com/'
COLUMNS = ['Title', 'Price', 'Rating', 'Availability', 'URL']
RATINGS = dict(zip(['One', 'Two', 'Three', 'Four', 'Five'], range(1, 6)))
LOG = logging.getLogger(__name__)


def fetch_page(session, url, attempts=3, sleep=time.sleep):
    """Retry transient failures only; a permanent HTTP error ends the run."""
    for attempt in range(attempts):
        try:
            response = session.get(url, timeout=20)
            # Retry rate limiting and server failures, but do not retry a 404.
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.ConnectionError(f'HTTP {response.status_code}: {url}')
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except (requests.Timeout, requests.ConnectionError) as exc:
            LOG.warning('Attempt %s/%s failed: %s', attempt + 1, attempts, exc)
            if attempt + 1 == attempts:
                raise
            sleep(2 ** attempt)


def site_url(page_url, href):
    """Resolve relative links and reject links outside the intended website."""
    if not href or not href.strip():
        raise ValueError('Missing URL')
    url = urljoin(page_url, href)
    parts = urlparse(url)
    if parts.scheme not in ('http', 'https') or parts.netloc != 'books.toscrape.com':
        raise ValueError('Invalid product or pagination URL')
    return url


def parse_page(html, page_url):
    """Extract full titles from attributes, rather than truncated visible text."""
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.select('article.product_pod')
    if not cards:
        raise ValueError(f'No book cards found: {page_url}')
    rows = []
    for index, card in enumerate(cards, start=1):
        try:
            link = card.select_one('h3 a')
            price_node = card.select_one('.price_color')
            rating_node = card.select_one('.star-rating')
            stock_node = card.select_one('.availability')
            if any(node is None for node in (link, price_node, rating_node, stock_node)):
                raise ValueError('Missing required field')
            title = link.get('title', '').strip()
            price = price_node.get_text(strip=True)
            if not title or not re.fullmatch(r'£\d+\.\d{2}', price):
                raise ValueError('Invalid title or GBP price')
            ratings = [RATINGS[c] for c in rating_node.get('class', []) if c in RATINGS]
            if len(ratings) != 1:
                raise ValueError('Missing or invalid rating')
            stock = ' '.join(stock_node.get_text(' ', strip=True).split()).lower()
            if stock not in ('in stock', 'out of stock'):
                raise ValueError('Invalid availability')
            rows.append(dict(zip(COLUMNS, [title, price[1:], ratings[0],
                         stock.capitalize(), site_url(page_url, link.get('href'))])))
        except ValueError as exc:
            # One broken card must not prevent other valid books being exported.
            LOG.error('Skipping book %s on %s: %s', index, page_url, exc)
    next_node = soup.select_one('li.next a')
    next_url = site_url(page_url, next_node.get('href')) if next_node else None
    return rows, next_url


def scrape(session, max_pages=None, delay=0.25, sleep=time.sleep):
    """Follow actual Next links; never assume there are exactly 50 pages."""
    if max_pages is not None and max_pages < 1:
        raise ValueError('max_pages must be positive')
    url, visited, seen_books, result = BASE_URL, set(), set(), []
    while url:
        if url in visited:
            raise ValueError('Pagination loop detected')
        visited.add(url)
        rows, next_url = parse_page(fetch_page(session, url, sleep=sleep), url)
        for row in rows:
            if row['URL'] not in seen_books:
                result.append(row)
                seen_books.add(row['URL'])
        LOG.info('Page %s: %s valid books', len(visited), len(rows))
        if max_pages is not None and len(visited) >= max_pages:
            break
        url = next_url
        if url:
            sleep(delay)
    return result


def write_csv(rows, output):
    """Use csv quoting for commas/quotes; replace the output only after writing."""
    output = Path(output)
    if output.suffix.lower() != '.csv':
        raise ValueError('Output must have a .csv extension')
    temporary = output.with_suffix('.csv.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-pages', type=int, help='Use 1 for homepage only')
    parser.add_argument('--output', default='books_data.csv')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler('scraper.log', encoding='utf-8')])
    try:
        with requests.Session() as session:
            session.headers['User-Agent'] = 'BooksScraper-Educational/1.0'
            rows = scrape(session, args.max_pages)
        if not rows:
            raise ValueError('No valid books; existing output retained')
        write_csv(rows, args.output)
        LOG.info('Saved %s books to %s', len(rows), args.output)
        return 0
    except (requests.RequestException, ValueError, OSError) as exc:
        # Do not label a partially fetched catalogue as a successful complete CSV.
        LOG.error('Scrape failed; no new CSV published: %s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
