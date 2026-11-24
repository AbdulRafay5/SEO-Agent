import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import app, valid_title_text, extract_ai_title_candidates


class GenerationReliabilityTests(unittest.TestCase):
    def test_unsegmented_titles(self):
        self.assertTrue(valid_title_text("室内植物の育て方"))
        self.assertTrue(valid_title_text("室内植物养护指南"))
        self.assertTrue(valid_title_text("How to grow herbs"))
        self.assertFalse(valid_title_text("123"))
        self.assertIn("室内植物の育て方", extract_ai_title_candidates("1. 室内植物の育て方"))

    def test_short_article_does_not_trigger_repeated_generation(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict("os.environ", {"SEO_ACCOUNT_MODE":"0","SEO_GUEST_MODE":"1","SEO_OWNER_AUTH":"0"}), \
             patch("app.BLOGS_FOLDER", folder), \
             patch("app.LAST_GEN_FILE", str(Path(folder) / "last.txt")), \
             patch("app.gemini_client", object()), \
             patch("app.generate_ai_text", return_value="# Herbs\n\nHerbs need sunlight.") as generate:
            response = app.test_client().post("/api/generate", json={"primary_keyword":"herbs"})
            self.assertEqual(response.status_code, 200)
            generate.assert_called_once()
            self.assertIn("Herbs need sunlight.", response.get_json()["content"])

    def test_unicode_evidence_fits_transport_limit(self):
        with patch.dict("os.environ", {"SEO_ACCOUNT_MODE":"0","SEO_GUEST_MODE":"1","SEO_OWNER_AUTH":"0"}):
            response = app.test_client().post("/api/evidence/preview", json={
                "topic":"植物", "evidence_sources":[{"title":"植物","text":"植物の育て方"*1500} for _ in range(3)]})
            self.assertEqual(response.status_code, 200)
