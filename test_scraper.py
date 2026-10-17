import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError
import scraper


def sample_employee():
    return {
        "User Id": "EMP001", "First Name": "Test", "Last Name": "Employee",
        "Email": "test@example.com", "Job Title": "Developer", "Phone": "0123-456-789",
        "Hire Date": "2025-01-15", "Date of birth": "2000-06-20", "Sex": "Female",
    }


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def fake_response(content):
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.read.return_value = content
    return response


class TestEmployeeScraper(unittest.TestCase):
    def test_01_csv_download(self):
        content = csv_bytes([sample_employee()])
        connection = MagicMock(side_effect=[
            TimeoutError(), URLError("Simulated failure"), fake_response(content)])
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "employees.csv"
            with self.assertLogs("employee_scraper", level="WARNING"):
                _, rows = scraper.download_file(scraper.URL, destination, delay=0, opener=connection)
            self.assertEqual(destination.read_bytes(), content)
            self.assertEqual(len(rows), 1)
        self.assertEqual(connection.call_count, 3)
        connection.assert_called_with(scraper.URL, timeout=20)

    def test_02_csv_extraction(self):
        _, rows = scraper.parse_csv(csv_bytes([sample_employee()]))
        employee = scraper.map_employee(rows[0])
        for source, target in scraper.FIELD_MAPPING.items():
            self.assertEqual(employee[target], sample_employee()[source])
        self.assertEqual(employee["hire_date"], "2025-01-15")
        self.assertFalse(employee["hire_date_is_dummy"])

    def test_03_file_type_and_format(self):
        header = ",".join(sample_employee()).encode()
        for content in [b"", b"<html>Sign in</html>", b"PK\x03\x04invalid",
                        b"\xff\xfe\x00\x01", b"unexpected,text\none,two",
                        header + b'\n"unfinished quoted value', header + b"\n"]:
            with self.subTest(content=content[:20]), self.assertRaises(ValueError):
                scraper.parse_csv(content)

    def test_04_missing_hire_date(self):
        source = sample_employee()
        del source["Hire Date"]
        _, rows = scraper.parse_csv(csv_bytes([source]))
        employee = scraper.map_employee(rows[0])
        self.assertGreaterEqual(employee["hire_date"], "2020-01-01")
        self.assertLessEqual(employee["hire_date"], "2025-12-31")
        self.assertTrue(employee["hire_date_is_dummy"])
        self.assertEqual(employee["date_of_birth"], "2000-06-20")

    def test_05_missing_or_invalid_data(self):
        bad_name, bad_email, bad_date, bad_columns = [sample_employee() for _ in range(4)]
        bad_name["First Name"] = ""
        bad_email["Email"] = "invalid-email"
        bad_date["Hire Date"] = "2025-02-30"
        bad_columns[None] = ["extra"]
        accepted, rejected = scraper.process_employees([
            bad_name, bad_email, bad_date, bad_columns, sample_employee(), sample_employee()])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(len(rejected), 5)
        missing = sample_employee()
        del missing["Email"]
        with self.assertRaises(ValueError):
            scraper.parse_csv(csv_bytes([missing]))

    def test_06_retry_limit(self):
        connection = MagicMock(side_effect=HTTPError(scraper.URL, 503, "Unavailable", None, None))
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "employees.csv"
            with self.assertLogs("employee_scraper", level="WARNING"), self.assertRaises(RuntimeError):
                scraper.download_file(scraper.URL, destination, delay=0, opener=connection)
            self.assertFalse(destination.exists())
        self.assertEqual(connection.call_count, 3)

    def test_07_blank_hire_date(self):
        source = sample_employee()
        source["Hire Date"] = "  "
        employee = scraper.map_employee(source)
        self.assertGreaterEqual(employee["hire_date"], "2020-01-01")
        self.assertLessEqual(employee["hire_date"], "2025-12-31")
        self.assertTrue(employee["hire_date_is_dummy"])

    def test_08_real_hire_date_preserved(self):
        source = sample_employee()
        source["Hire Date"] = "2022-11-30"
        employee = scraper.map_employee(source)
        self.assertEqual(employee["hire_date"], "2022-11-30")
        self.assertFalse(employee["hire_date_is_dummy"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
