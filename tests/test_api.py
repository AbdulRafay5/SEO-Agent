import os
import unittest
from unittest.mock import patch

for name in ("GITHUB_REPO", "GITHUB_TOKEN", "GEMINI_API_KEY", "GROQ_API_KEY", "QWEN_API_KEY"):
    os.environ[name] = ""

from app import app, get_fallback_trend_data


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_generation_requires_post(self):
        self.assertEqual(self.client.get("/api/generate").status_code, 405)

    def test_empty_topic(self):
        self.assertEqual(self.client.post("/api/generate", json={}).status_code, 400)

    def test_bad_secondary_keywords(self):
        response = self.client.post("/api/generate", json={"primary_keyword": "gardening", "secondary_keywords": None})
        self.assertEqual(response.status_code, 400)

    def test_invalid_reference(self):
        response = self.client.post("/api/generate", json={"primary_keyword": "gardening", "links": "javascript:alert(1)"})
        self.assertEqual(response.status_code, 400)

    def test_missing_provider(self):
        with patch("app.gemini_client", None), patch("app.client", None):
            response = self.client.post("/api/generate", json={"primary_keyword": "gardening"})
        self.assertEqual(response.status_code, 503)

    def test_trend_scope(self):
        self.assertEqual(get_fallback_trend_data()["region_scope"], "Worldwide")
        self.assertEqual(get_fallback_trend_data("GB")["region_scope"], "GB")

    def test_invalid_country(self):
        self.assertEqual(self.client.get("/api/trends?keyword=gardening&geo=INVALID").status_code, 400)
