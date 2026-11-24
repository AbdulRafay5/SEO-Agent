import unittest
from unittest.mock import patch
from app import app


class EditorTests(unittest.TestCase):
    def test_preview(self):
        with patch("app.gemini_client", object()), patch("app.generate_ai_text", return_value="## Care\n\nRevised section."):
            response = app.test_client().post("/api/editor/revise", json={"section":"## Care\n\nOriginal.", "action":"rewrite"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Revised section.", response.get_json()["revision"])

    def test_invalid_action(self):
        response = app.test_client().post("/api/editor/revise", json={"section":"Original", "action":[]})
        self.assertEqual(response.status_code, 400)

    def test_provider_failure(self):
        with patch("app.gemini_client", object()), patch("app.generate_ai_text", side_effect=RuntimeError("offline")):
            response = app.test_client().post("/api/editor/revise", json={"section":"Original", "action":"rewrite"})
        self.assertEqual(response.status_code, 502)
