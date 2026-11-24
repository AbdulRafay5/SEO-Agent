import unittest
from unittest.mock import patch
from app import app, extract_title_meta_options


class TitleRepairTests(unittest.TestCase):
    def test_international_titles_are_not_rewritten(self):
        rows = extract_title_meta_options("1. Cómo cultivar albahaca - guía práctica || Aprende a cultivar albahaca", ["albahaca"], True, "Spanish")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Cómo cultivar albahaca - guía práctica")
        self.assertEqual(rows[0]["source"], "ai")

    def test_fallbacks_are_labelled(self):
        rows = extract_title_meta_options("1. Growing herbs indoors || A useful guide", ["herbs"], False)
        self.assertEqual(rows[0]["source"], "ai")
        self.assertTrue(any(row["source"] == "fallback" for row in rows))
        self.assertEqual(len({row["title"].casefold() for row in rows}), len(rows))

    def test_non_english_provider_failure(self):
        with patch("app.generate_title_text", side_effect=RuntimeError("offline")):
            response = app.test_client().get("/api/titles/albahaca?language=Spanish")
        self.assertEqual(response.status_code, 502)
        self.assertIn("language", response.get_json()["error"])

    def test_title_input_limits(self):
        self.assertEqual(app.test_client().get("/api/titles/"+"a"*301).status_code, 400)
