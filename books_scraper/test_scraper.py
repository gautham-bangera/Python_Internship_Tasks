"""Offline acceptance tests: deterministic fixtures and mocked HTTP responses."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
import requests
from scraper import BASE_URL, COLUMNS, fetch_page, parse_page, scrape, write_csv


def card(title='A Book', price='£12.50', rating='Three', stock='In stock', href='catalogue/book_1/index.html'):
    return f'''<article class="product_pod"><h3><a title='{title}' href='{href}'>Short title</a></h3>
    <p class="price_color">{price}</p><p class="star-rating {rating}"></p>
    <p class="availability">{stock}</p></article>'''


def response(html, status=200):
    result = Mock(status_code=status, text=html)
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError(str(status))
    return result


class BookTests(unittest.TestCase):
    def test_01_csv_file_download(self):
        # The site supplies HTML, so "CSV download" means fetch -> export file.
        session = Mock()
        session.get.return_value = response(''.join(card(href=f'catalogue/{i}/index.html') for i in range(20)))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'books_data.csv'
            write_csv(scrape(session, max_pages=1), path)
            self.assertTrue(path.is_file())
            with path.open(encoding='utf-8', newline='') as file:
                self.assertEqual(len(list(csv.DictReader(file))), 20)

    def test_02_csv_file_extraction(self):
        rows, _ = parse_page(card(title='Books, café &amp; more'), BASE_URL)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'books_data.csv'
            write_csv(rows, path)
            with path.open(encoding='utf-8', newline='') as file:
                row = next(csv.DictReader(file))
            self.assertEqual(row, dict(zip(COLUMNS, ['Books, café & more', '12.50', '3', 'In stock', BASE_URL + 'catalogue/book_1/index.html'])))

    def test_03_file_type_and_format(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                write_csv([], Path(folder) / 'books.json')
            path = Path(folder) / 'books.csv'
            write_csv([], path)
            self.assertEqual(path.read_bytes(), b'Title,Price,Rating,Availability,URL\r\n')

    def test_04_data_structure(self):
        for number, word in enumerate(['One', 'Two', 'Three', 'Four', 'Five'], 1):
            rows, _ = parse_page(card(rating=word, stock='Out of stock'), BASE_URL)
            self.assertEqual(list(rows[0]), COLUMNS)
            self.assertEqual(rows[0]['Rating'], number)
            self.assertEqual(rows[0]['Availability'], 'Out of stock')

    def test_05_missing_invalid_data(self):
        invalid = [card(title=''), card(price='free'), card(rating='Six'), card(stock='Unknown'),
                   card(href=''), card(href='https://example.com/a'), card().replace('price_color', 'missing')]
        for broken in invalid:
            with self.subTest(broken=broken), self.assertLogs('scraper', level='ERROR'):
                rows, _ = parse_page(broken + card(), BASE_URL)
                self.assertEqual(len(rows), 1)

    def test_pagination_and_duplicates(self):
        session = Mock()
        session.get.side_effect = [response(card() + '<li class="next"><a href="catalogue/page-2.html">next</a></li>'),
                                   response(card(href='book_1/index.html') + card(href='book_2/index.html'))]
        rows = scrape(session, sleep=lambda _: None)
        self.assertEqual(len(rows), 2)
        self.assertEqual(session.get.call_args.args[0], BASE_URL + 'catalogue/page-2.html')

    def test_503_retry_then_success(self):
        session = Mock()
        session.get.side_effect = [response('', 503), response(card())]
        self.assertEqual(fetch_page(session, BASE_URL, sleep=lambda _: None), card())
        self.assertEqual(session.get.call_count, 2)

    def test_404_no_retry(self):
        session = Mock()
        session.get.return_value = response('', 404)
        with self.assertRaises(requests.HTTPError):
            fetch_page(session, BASE_URL)
        self.assertEqual(session.get.call_count, 1)

    def test_timeout_retry_limit(self):
        session = Mock()
        session.get.side_effect = requests.Timeout('timeout')
        with self.assertRaises(requests.Timeout):
            fetch_page(session, BASE_URL, sleep=lambda _: None)
        self.assertEqual(session.get.call_count, 3)

    def test_empty_page_and_pagination_loop(self):
        with self.assertRaises(ValueError):
            parse_page('<html></html>', BASE_URL)
        session = Mock()
        session.get.return_value = response(card() + '<li class="next"><a href="/">next</a></li>')
        with self.assertRaisesRegex(ValueError, 'loop'):
            scrape(session, sleep=lambda _: None)


if __name__ == '__main__':
    unittest.main()
