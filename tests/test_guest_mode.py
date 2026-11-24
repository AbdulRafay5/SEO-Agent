import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import app


class GuestModeTests(unittest.TestCase):
    def test_guest_home_does_not_read_owner_storage(self):
        with patch.dict("os.environ", {"SEO_GUEST_MODE":"1","SEO_OWNER_AUTH":"0"}), \
             patch("app.github_store.list_dir") as listing, patch("app._load_manifest") as manifest, \
             patch("app._safe_listdir") as local:
            response = app.test_client().get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"const guestWorkspace=true", response.data)
            listing.assert_not_called()
            manifest.assert_not_called()
            local.assert_not_called()

    def test_guest_cannot_read_owner_drafts(self):
        with patch.dict("os.environ", {"SEO_GUEST_MODE":"1","SEO_OWNER_AUTH":"0"}), \
             patch("app.github_store.get_file") as read:
            for path in ("/api/blog/private.md", "/blog/private.md"):
                self.assertEqual(app.test_client().get(path).status_code, 404)
            read.assert_not_called()

    def test_conflicting_modes_fail_closed(self):
        with patch.dict("os.environ", {"SEO_GUEST_MODE":"1","SEO_OWNER_AUTH":"1"}):
            self.assertEqual(app.test_client().get("/").status_code, 503)

    def test_guest_generation_does_not_save_server_draft(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.dict("os.environ", {"SEO_GUEST_MODE":"1","SEO_OWNER_AUTH":"0"}), \
             patch("app.BLOGS_FOLDER", folder), \
             patch("app.LAST_GEN_FILE", str(Path(folder) / "last.txt")), \
             patch("app.MIN_WORD_COUNT", 1), \
             patch("app.gemini_client", object()), \
             patch("app.generate_ai_text", return_value="# Herbs\n\nHerbs need sunlight."), \
             patch("app.github_store.save_file") as save, \
             patch("app._upsert_manifest_entry") as manifest:
            response = app.test_client().post("/api/generate", json={"primary_keyword":"herbs"})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.get_json()["storage"]["article_saved"])
            self.assertFalse(response.get_json()["storage"]["remote_configured"])
            self.assertEqual(list(Path(folder).glob("*.md")), [])
            save.assert_not_called()
            manifest.assert_not_called()
