import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import app, save_local_metadata, local_metadata


class LocalMetadataTests(unittest.TestCase):
    def test_local_reload_preserves_target_and_brief(self):
        with tempfile.TemporaryDirectory() as folder, patch("app.BLOGS_FOLDER", folder), patch("app.github_store.get_file", return_value=(None, None)):
            filename = "local.md"
            body = "# Herbs\n\nWater regularly."
            Path(folder, filename).write_text(body, encoding="utf-8")
            self.assertTrue(save_local_metadata(filename, body, {"filename":filename,"keyword":"herbs","targetWords":750,"metaDescription":"Grow herbs","brief":{"language":"English"}}))
            response = app.test_client().get("/api/blog/local.md")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["target_words"], 750)
            self.assertEqual(response.json["keyword"], "herbs")
            self.assertEqual(response.json["meta_description"], "Grow herbs")
            self.assertEqual(response.json["brief"]["language"], "English")

    def test_metadata_cannot_attach_to_changed_content(self):
        with tempfile.TemporaryDirectory() as folder, patch("app.BLOGS_FOLDER", folder):
            self.assertTrue(save_local_metadata("local.md", "Old", {"filename":"local.md"}))
            self.assertEqual(local_metadata("local.md", "New"), {})
            self.assertEqual(local_metadata("../local.md", "Old"), {})
