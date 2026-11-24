import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import app, _load_manifest, extract_ai_title_candidates


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_home_when_storage_unavailable(self):
        with patch("app.github_store.list_dir", side_effect=RuntimeError("offline")), patch("app.github_store.get_file", side_effect=RuntimeError("offline")):
            self.assertEqual(self.client.get("/").status_code, 200)

    def test_manifest_invalid_entries(self):
        with patch("app.github_store.get_file", return_value=('["bad", {"filename":"a.md"}]', None)):
            self.assertEqual(_load_manifest(), [{"filename": "a.md"}])

    def test_remote_draft_unavailable(self):
        with tempfile.TemporaryDirectory() as folder, patch("app.BLOGS_FOLDER", folder), patch("app.BUNDLED_BLOGS_FOLDER", folder), patch("app.github_store.get_file", side_effect=RuntimeError("offline")):
            self.assertEqual(self.client.get("/api/blog/missing.md").status_code, 503)

    def test_non_latin_title_candidates(self):
        self.assertTrue(extract_ai_title_candidates("1. بہترین باغبانی کی رہنمائی"))

    def test_generation_and_reload(self):
        body = "# Indoor herbs\n\nIndoor herbs can grow in containers.\n\n## Care\n\nWater when soil is dry."
        with tempfile.TemporaryDirectory() as folder, patch("app.BLOGS_FOLDER", folder), patch("app.LAST_GEN_FILE", str(Path(folder) / "last.txt")), patch("app.MIN_WORD_COUNT", 5), patch("app.gemini_client", object()), patch("app.generate_ai_text", return_value=body), patch("app.github_store.save_file", return_value=False), patch("app.github_store.get_file", return_value=(None, None)):
            response = self.client.post("/api/generate", json={"primary_keyword": "Indoor herbs", "title": "Indoor herbs"})
            self.assertEqual(response.status_code, 200, response.get_json())
            data = response.get_json()
            self.assertIn("Indoor herbs", data["content"])
            saved = self.client.get("/api/blog/" + data["filename"])
            self.assertEqual(saved.status_code, 200)
            self.assertEqual(saved.get_json()["content"], data["content"])
            self.assertEqual(self.client.post("/api/generate", json={"primary_keyword": "Indoor herbs"}).status_code, 429)
