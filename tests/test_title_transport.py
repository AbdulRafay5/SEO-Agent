import unittest
from unittest.mock import patch
from app import app


class TitleTransportTests(unittest.TestCase):
    def test_json_preserves_question_and_spaces(self):
        keyword = "How to start a coffee farm?"
        with patch("app.generate_title_text", return_value="1. How to start a coffee farm? || Practical guide") as generate:
            response = app.test_client().post("/api/titles", json={"keyword": keyword})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["keyword"], keyword)
        self.assertIn(keyword, generate.call_args.args[0])
        self.assertNotIn("%20", str(response.json))

    def test_legacy_encoded_path_is_decoded(self):
        with patch("app.generate_title_text", return_value="1. How to start a coffee farm? || Practical guide"):
            response = app.test_client().get("/api/titles/How%2520to%2520start%2520a%2520coffee%2520farm%253F")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["keyword"], "How to start a coffee farm?")
        self.assertNotIn("%20", str(response.json))

    def test_json_preserves_literal_percent_and_special_characters(self):
        keyword = "100% coffee + tea / café & %20"
        with patch("app.generate_title_text", return_value="1. A guide to coffee and tea || Practical guide"):
            response = app.test_client().post("/api/titles", json={"keyword": keyword})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["keyword"], keyword)

    def test_invalid_json_options(self):
        for payload in ([], {"keyword": 123}, {"keyword": "coffee", "language": []}):
            self.assertEqual(app.test_client().post("/api/titles", json=payload).status_code, 400)
