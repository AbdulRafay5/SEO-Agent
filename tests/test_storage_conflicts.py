import json
import unittest
from unittest.mock import patch, Mock
import requests
import github_store
from app import _upsert_manifest_entry


class StorageConflictTests(unittest.TestCase):
    def test_explicit_sha_is_not_refetched(self):
        response = Mock()
        with patch.dict("os.environ", {"GITHUB_REPO":"example/private","GITHUB_TOKEN":"test"}), patch("github_store.get_file") as read, patch("github_store.requests.put", return_value=response) as write:
            self.assertTrue(github_store.save_file("drafts/manifest.json", "[]", "Update", expected_sha="old-sha"))
            read.assert_not_called()
            self.assertEqual(write.call_args.kwargs["json"]["sha"], "old-sha")

    def test_explicit_none_is_create_only(self):
        with patch.dict("os.environ", {"GITHUB_REPO":"example/private","GITHUB_TOKEN":"test"}), patch("github_store.get_file") as read, patch("github_store.requests.put", return_value=Mock()) as write:
            github_store.save_file("drafts/manifest.json", "[]", "Create", expected_sha=None)
            read.assert_not_called()
            self.assertNotIn("sha", write.call_args.kwargs["json"])

    def test_conflicting_write_merges_latest_index(self):
        response = requests.Response()
        response.status_code = 409
        conflict = requests.HTTPError(response=response)
        first = [{"filename":"original.md"}]
        second = first + [{"filename":"concurrent.md"}]
        with patch("app.github_store.get_file", side_effect=[(json.dumps(first),"sha1"), (json.dumps(second),"sha2")]), patch("app.github_store.save_file", side_effect=[conflict,True]) as save:
            self.assertTrue(_upsert_manifest_entry({"filename":"new.md"}))
            self.assertEqual(save.call_args_list[0].kwargs["expected_sha"], "sha1")
            self.assertEqual(save.call_args_list[1].kwargs["expected_sha"], "sha2")
            filenames = {row["filename"] for row in json.loads(save.call_args.args[1])}
            self.assertEqual(filenames, {"original.md","concurrent.md","new.md"})

    def test_invalid_index_is_not_overwritten(self):
        for content in ("not json", "{}", "[null]"):
            with patch("app.github_store.get_file", return_value=(content,"sha")), patch("app.github_store.save_file") as save:
                self.assertFalse(_upsert_manifest_entry({"filename":"new.md"}))
                save.assert_not_called()

    def test_retries_are_bounded(self):
        response = requests.Response()
        response.status_code = 409
        with patch("app.github_store.get_file", return_value=("[]","sha")), patch("app.github_store.save_file", side_effect=requests.HTTPError(response=response)) as save:
            self.assertFalse(_upsert_manifest_entry({"filename":"new.md"}))
            self.assertEqual(save.call_count,3)
