import base64
import unittest
from unittest.mock import patch
from app import app


class RemoteVersionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.headers = {"Authorization": "Basic " + base64.b64encode(b"owner:test-password").decode()}
        self.config = {"SEO_REMOTE_VERSIONS": "1", "SEO_OWNER_AUTH": "1",
                       "SEO_OWNER_USERNAME": "owner", "SEO_OWNER_PASSWORD": "test-password",
                       "GITHUB_REPO": "example/private", "GITHUB_TOKEN": "test"}
        self.payload = {"content": "# Revised\n\nContent.", "keyword": "Topic", "version_of": "original.md"}

    def test_disabled_without_owner_auth(self):
        with patch.dict("os.environ", {**self.config, "SEO_OWNER_AUTH":"0"}):
            self.assertEqual(self.client.post("/api/blog/versions", json=self.payload).status_code, 503)

    def test_requires_auth(self):
        with patch.dict("os.environ", self.config):
            self.assertEqual(self.client.post("/api/blog/versions", json=self.payload).status_code, 401)

    def test_save_creates_separate_file(self):
        with patch.dict("os.environ", self.config), patch("app.github_store.save_file", return_value=True) as save, patch("app.github_store.get_file", return_value=(None,None)):
            response = self.client.post("/api/blog/versions", json=self.payload, headers=self.headers)
            self.assertEqual(response.status_code, 201)
            data = response.get_json()
            self.assertTrue(data["metadata_saved"])
            self.assertTrue(data["filename"].startswith("remote_version_"))
            self.assertEqual(save.call_args_list[0].args[0], "drafts/" + data["filename"])
            self.assertEqual(save.call_args_list[0].args[1], self.payload["content"])

    def test_index_failure_is_reported(self):
        with patch.dict("os.environ", self.config), patch("app.github_store.save_file", side_effect=[True, False]), patch("app.github_store.get_file", return_value=(None,None)):
            response = self.client.post("/api/blog/versions", json=self.payload, headers=self.headers)
            self.assertEqual(response.status_code, 201)
            self.assertFalse(response.get_json()["metadata_saved"])

    def test_write_failure(self):
        with patch.dict("os.environ", self.config), patch("app.github_store.save_file", return_value=False):
            self.assertEqual(self.client.post("/api/blog/versions", json=self.payload, headers=self.headers).status_code, 503)
