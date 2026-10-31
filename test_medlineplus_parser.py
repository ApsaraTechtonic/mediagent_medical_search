import unittest
from unittest.mock import patch, Mock
import requests
import _medical_search_under_test as app

class TestMedlinePlusSearch(unittest.TestCase):
    @patch("_medical_search_under_test.requests.get")
    def test_parses_title_url_and_summary(self, get):
        response = Mock()
        response.content = b"""<results><document rank="0" url="https://medlineplus.gov/asthma.html"><content name="title">Asthma</content><content name="FullSummary">Asthma affects the airways.</content></document></results>"""
        response.raise_for_status.return_value = None
        get.return_value = response
        self.assertEqual(
            [{"title": "Asthma", "url": "https://medlineplus.gov/asthma.html",
              "summary": "Asthma affects the airways."}],
            app.search_medlineplus("asthma")
        )

    @patch("_medical_search_under_test.requests.get")
    def test_empty_results(self, get):
        response = Mock()
        response.content = b"<results></results>"
        response.raise_for_status.return_value = None
        get.return_value = response
        self.assertEqual([], app.search_medlineplus("no matching topic"))

    @patch("_medical_search_under_test.requests.get")
    def test_network_error_is_actionable(self, get):
        get.side_effect = requests.exceptions.Timeout()
        with self.assertRaisesRegex(RuntimeError, "timed out"):
            app.search_medlineplus("asthma")

if __name__ == "__main__":
    unittest.main(verbosity=2)
