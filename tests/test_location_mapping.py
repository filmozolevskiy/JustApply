import os
import sys
import unittest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.core.enrichment.contact_sample import detect_country_from_location


class TestLocationMapping(unittest.TestCase):
    def test_canada_full_name(self):
        self.assertEqual(detect_country_from_location("Montreal, Quebec, Canada"), "Canada")
        self.assertEqual(detect_country_from_location("Canada"), "Canada")

    def test_canada_province_abbreviations(self):
        # All 13 Canadian provinces and territories
        provinces = {
            "ON": "Toronto, ON",
            "QC": "Laval, QC",
            "BC": "Richmond, BC",
            "AB": "Edmonton, AB",
            "MB": "Winnipeg, MB",
            "NB": "Moncton, NB",
            "NL": "St. John's, NL",
            "NS": "Halifax, NS",
            "PE": "Charlottetown, PE",
            "SK": "Saskatoon, SK",
            "YT": "Whitehorse, YT",
            "NT": "Yellowknife, NT",
            "NU": "Iqaluit, NU",
        }
        for code, location in provinces.items():
            with self.subTest(province=code):
                self.assertEqual(detect_country_from_location(location), "Canada")

    def test_canada_province_full_names(self):
        self.assertEqual(detect_country_from_location("Vancouver, British Columbia"), "Canada")
        self.assertEqual(detect_country_from_location("Calgary, Alberta"), "Canada")
        self.assertEqual(detect_country_from_location("City, Ontario"), "Canada")
        self.assertEqual(detect_country_from_location("City, Quebec"), "Canada")

    def test_us_full_name(self):
        self.assertEqual(detect_country_from_location("United States"), "United States")
        self.assertEqual(detect_country_from_location("New York, United States"), "United States")

    def test_us_state_abbreviations(self):
        # At least 10 US state abbreviations
        states = {
            "NY": "New York, NY",
            "CA": "San Francisco, CA",
            "IL": "Chicago, IL",
            "FL": "Miami, FL",
            "WA": "Seattle, WA",
            "TX": "Dallas, TX",
            "PA": "Philadelphia, PA",
            "OH": "Columbus, OH",
            "GA": "Atlanta, GA",
            "NC": "Charlotte, NC",
            "MA": "Boston, MA",
            "AZ": "Phoenix, AZ",
        }
        for code, location in states.items():
            with self.subTest(state=code):
                self.assertEqual(detect_country_from_location(location), "United States")

    def test_us_state_full_names(self):
        self.assertEqual(detect_country_from_location("Austin, Texas"), "United States")
        self.assertEqual(detect_country_from_location("Los Angeles, California"), "United States")
        self.assertEqual(detect_country_from_location("City, Florida"), "United States")
        self.assertEqual(detect_country_from_location("City, New York"), "United States")

    def test_remote_returns_none(self):
        self.assertIsNone(detect_country_from_location("Remote"))
        self.assertIsNone(detect_country_from_location("remote"))
        self.assertIsNone(detect_country_from_location("REMOTE"))

    def test_none_returns_none(self):
        self.assertIsNone(detect_country_from_location(None))

    def test_remote_with_country_returns_country(self):
        self.assertEqual(detect_country_from_location("United States (Remote)"), "United States")
        self.assertEqual(detect_country_from_location("Canada (Remote)"), "Canada")

    def test_unrecognized_locations_return_none(self):
        self.assertIsNone(detect_country_from_location("London, UK"))
        self.assertIsNone(detect_country_from_location("Berlin, Germany"))
        self.assertIsNone(detect_country_from_location("Paris"))
        self.assertIsNone(detect_country_from_location("Sydney, Australia"))

    def test_case_insensitivity(self):
        self.assertEqual(detect_country_from_location("montreal, quebec"), "Canada")
        self.assertEqual(detect_country_from_location("Toronto, on"), "Canada")
        self.assertEqual(detect_country_from_location("new york, ny"), "United States")


if __name__ == "__main__":
    unittest.main()
