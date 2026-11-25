"""Offline acceptance and failure tests; no live website is needed."""

import csv
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from bs4 import BeautifulSoup
import scraper


def card(title='A Book, Volume 1', href='catalogue/book_1/index.html',
         price='£12.34', rating='Three', availability='In stock'):
    return (f'<article class="product_pod"><h3><a title="{title}" href="{href}">'
            f'Short title...</a></h3><p class="price_color">{price}</p>'
            f'<p class="star-rating {rating}"></p>'
            f'<p class="availability">\n {availability} \n</p></article>')


def response(body, content_type='text/html; charset=utf-8'):
    result = MagicMock()
    result.__enter__.return_value = result
    result.status = 200
    result.headers = Message()
    result.headers['Content-Type'] = content_type
    result.read.return_value = body.encode('utf-8')
    return result


class TestBookScraper(unittest.TestCase):
    def test_01_csv_file_download(self):
        # The source is HTML: this acceptance case verifies download -> generated CSV.
        with tempfile.TemporaryDirectory() as folder, patch(
                'scraper.urlopen', return_value=response(card())):
            output = Path(folder) / 'books_data.csv'
            self.assertEqual(scraper.main(['--output', str(output)]), 0)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 0)

    def test_02_csv_file_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'books_data.csv'
            record = scraper.parse_book(BeautifulSoup(card(), 'html.parser'), scraper.BASE_URL)
            scraper.write_csv([record], output)
            with output.open(encoding='utf-8', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['Title'], 'A Book, Volume 1')
            self.assertEqual(rows[0]['Price'], '12.34')
            self.assertEqual(rows[0]['Rating'], '3')

    def test_03_file_type_and_format(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                scraper.write_csv([], Path(folder) / 'books.xlsx')
        with patch('scraper.urlopen', return_value=response('{}', 'application/json')):
            with self.assertRaises(scraper.ScrapeError):
                scraper.fetch_page(scraper.BASE_URL)

    def test_04_data_structure(self):
        result = scraper.parse_book(BeautifulSoup(card(), 'html.parser'), scraper.BASE_URL)
        self.assertEqual(list(result), scraper.COLUMNS)
        self.assertIsInstance(result['Rating'], int)
        self.assertEqual(result['Availability'], 'In stock')
        self.assertEqual(result['URL'], 'https://books.toscrape.com/catalogue/book_1/index.html')

    def test_05_missing_or_invalid_data(self):
        invalid = [card(title=''), card(price='£-1.00'), card(price='unknown'),
                   card(rating='Six'), card(availability='Unknown'), card(href=''),
                   card(href='https://example.com/book'), card().replace('price_color', 'absent')]
        with patch('scraper.fetch_page', return_value=''.join(invalid) + card()), self.assertLogs(
                'scraper', level='ERROR') as logs:
            records = scraper.scrape_books(delay=0)
        self.assertEqual(len(records), 1)
        self.assertEqual(len(logs.output), len(invalid))

    def test_pagination_and_duplicate_products(self):
        first = card() + '<li class="next"><a href="catalogue/page-2.html">next</a></li>'
        second = card(href='book_1/index.html') + card(title='Second', href='book_2/index.html')
        with patch('scraper.fetch_page', side_effect=[first, second]) as fetch:
            records = scraper.scrape_books(delay=0)
        self.assertEqual(len(records), 2)
        self.assertEqual(fetch.call_args_list[1].args[0],
                         'https://books.toscrape.com/catalogue/page-2.html')
        self.assertEqual(records[1]['URL'], 'https://books.toscrape.com/catalogue/book_2/index.html')

    def test_homepage_only_has_twenty_books(self):
        page = ''.join(card(href=f'catalogue/book_{i}/index.html') for i in range(20))
        page += '<li class="next"><a href="catalogue/page-2.html">next</a></li>'
        with patch('scraper.fetch_page', return_value=page) as fetch:
            self.assertEqual(len(scraper.scrape_books(max_pages=1)), 20)
        self.assertEqual(fetch.call_count, 1)

    def test_all_five_ratings_and_out_of_stock(self):
        for word, number in scraper.RATINGS.items():
            result = scraper.parse_book(BeautifulSoup(card(rating=word, availability='Out of stock'),
                                                      'html.parser'), scraper.BASE_URL)
            self.assertEqual(result['Rating'], number)
            self.assertEqual(result['Availability'], 'Out of stock')

    def test_503_retry_then_success(self):
        error = HTTPError(scraper.BASE_URL, 503, 'Unavailable', {}, None)
        with patch('scraper.urlopen', side_effect=[error, response(card())]) as fetch, patch(
                'scraper.time.sleep'):
            self.assertIn('product_pod', scraper.fetch_page(scraper.BASE_URL))
        self.assertEqual(fetch.call_count, 2)

    def test_404_is_not_retried(self):
        with patch('scraper.urlopen', side_effect=HTTPError(
                scraper.BASE_URL, 404, 'Not found', {}, None)) as fetch:
            with self.assertRaises(scraper.ScrapeError):
                scraper.fetch_page(scraper.BASE_URL)
        self.assertEqual(fetch.call_count, 1)

    def test_network_retry_limit(self):
        for error in (URLError('offline'), TimeoutError('timeout')):
            with self.subTest(error=error), patch('scraper.urlopen', side_effect=error) as fetch, patch(
                    'scraper.time.sleep'):
                with self.assertRaises(scraper.ScrapeError):
                    scraper.fetch_page(scraper.BASE_URL)
                self.assertEqual(fetch.call_count, 3)

    def test_failed_second_page_preserves_existing_csv(self):
        first = card() + '<li class="next"><a href="catalogue/page-2.html">next</a></li>'
        with tempfile.TemporaryDirectory() as folder, patch('scraper.fetch_page', side_effect=[
                first, scraper.ScrapeError('HTTP 503')]):
            output = Path(folder) / 'books_data.csv'
            output.write_text('previous successful data', encoding='utf-8')
            self.assertEqual(scraper.main(['--output', str(output), '--delay', '0']), 1)
            self.assertEqual(output.read_text(encoding='utf-8'), 'previous successful data')

    def test_empty_or_all_invalid_page_fails(self):
        for page in ('<html>Maintenance</html>', card(title='')):
            with patch('scraper.fetch_page', return_value=page), self.assertRaises(scraper.ScrapeError):
                scraper.scrape_books(delay=0)

    def test_pagination_cycle_and_broken_link(self):
        for next_html in ('<li class="next"><a href="/">next</a></li>',
                          '<li class="next"><a>next</a></li>'):
            with patch('scraper.fetch_page', return_value=card() + next_html), self.assertRaises(
                    scraper.ScrapeError):
                scraper.scrape_books(delay=0)

    def test_invalid_cli_options_fail_before_download(self):
        for args in (['--max-pages', '0'], ['--delay', '-1'], ['--output', 'books.json']):
            with patch('scraper.fetch_page') as fetch:
                self.assertEqual(scraper.main(args), 1)
                fetch.assert_not_called()

    def test_atomic_write_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'books_data.csv'
            output.write_text('previous', encoding='utf-8')
            with patch('scraper.os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    scraper.write_csv([], output)
            self.assertEqual(output.read_text(encoding='utf-8'), 'previous')
            self.assertEqual(list(Path(folder).iterdir()), [output])


if __name__ == '__main__':
    unittest.main()
