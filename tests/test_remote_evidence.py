import json
import unittest
from unittest.mock import patch
from app import save_remote_evidence, load_remote_evidence


class RemoteEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.body = "Herbs need sunlight [S1]."
        self.evidence = {"method":"BM25", "status":"retrieved", "passages":[
            {"source_id":"S1","title":"Guide","url":"","kind":"excerpt","passage":"Herbs need sunlight."}]}

    def test_round_trip_and_content_binding(self):
        with patch("app.remote_evidence_enabled", return_value=True), patch("app.github_store.save_file", return_value=True) as save:
            self.assertTrue(save_remote_evidence("article.md", self.body, self.evidence))
            path, payload = save.call_args.args
            self.assertEqual(path, "evidence/article.md.json")
            self.assertIsNone(save.call_args.kwargs["expected_sha"])
            with patch("app.github_store.get_file", return_value=(payload, "sha")):
                loaded = load_remote_evidence("article.md", self.body)
                self.assertEqual(loaded["citations"]["status"], "known_ids")
                self.assertIsNone(load_remote_evidence("article.md", "Changed article"))

    def test_disabled_does_not_access_store(self):
        with patch("app.remote_evidence_enabled", return_value=False), patch("app.github_store.save_file") as save, patch("app.github_store.get_file") as get:
            self.assertFalse(save_remote_evidence("article.md", self.body, self.evidence))
            self.assertIsNone(load_remote_evidence("article.md", self.body))
            save.assert_not_called()
            get.assert_not_called()

    def test_failed_storage(self):
        with patch("app.remote_evidence_enabled", return_value=True), patch("app.github_store.save_file", side_effect=RuntimeError("offline")):
            self.assertFalse(save_remote_evidence("article.md", self.body, self.evidence))

    def test_corrupt_data(self):
        with patch("app.remote_evidence_enabled", return_value=True), patch("app.github_store.get_file", return_value=("not json", None)):
            self.assertIsNone(load_remote_evidence("article.md", self.body))
