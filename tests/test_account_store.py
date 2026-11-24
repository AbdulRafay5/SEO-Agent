import json
import unittest
from unittest.mock import patch
from account_store import AccountStore
from app import app


class AccountStoreTests(unittest.TestCase):
    def test_invalid_paths(self):
        for value in ("../owner", "alice", "A"*32):
            with self.assertRaises(ValueError):
                AccountStore(value)
        store = AccountStore("a"*32)
        for value in ("../private.json", "a/b.json", "manifest.json", "a"*32+".md"):
            with self.assertRaises(ValueError):
                store.path(value)

    def test_isolated_records_and_versions(self):
        files = {}
        def save(path, content, **kwargs):
            self.assertIsNone(kwargs["expected_sha"])
            self.assertNotIn(path, files)
            files[path] = content
            return True
        def get(path):
            return files.get(path), None
        first, second = AccountStore("a"*32), AccountStore("b"*32)
        with patch("account_store.github_store.save_file", side_effect=save), patch("account_store.github_store.get_file", side_effect=get):
            article = first.create_article("# Private", "topic", "description")
            filename = article["filename"]
            self.assertEqual(first.read_article(filename), article)
            self.assertIsNone(second.read_article(filename))
            with self.assertRaises(ValueError):
                second.create_article("copy", version_of=filename)
            version = first.create_article("revision", version_of=filename)
            self.assertEqual(version["version_of"], filename)
            self.assertEqual(first.read_article(filename)["content"], "# Private")

    def test_listing_filters_unexpected_names(self):
        with patch("account_store.github_store.list_dir", return_value=["manifest.json", "a"*32+".json"]) as listing:
            self.assertEqual(AccountStore("b"*32).list_articles(), ["a"*32+".json"])
            listing.assert_called_once_with("users/"+"b"*32+"/drafts")

    def test_api_uses_verified_identity(self):
        config = {"SEO_ACCOUNT_MODE":"1","SEO_OWNER_AUTH":"0","SEO_GUEST_MODE":"0","SEO_DATABASE_URL":"test","SEO_ACCOUNT_SETUP_KEY":"k"*32}
        headers = {"X-Account-Setup-Key":"k"*32}
        with patch.dict("os.environ", config), patch("app.account_auth.current_account", return_value={"id":"a"*32,"username":"alice"}), patch("app.github_store._configured",return_value=True), patch("account_store.github_store.get_file",return_value=(None,None)) as get:
            client=app.test_client()
            filename="b"*32+".json"
            self.assertEqual(client.get("/api/accounts/articles/"+filename).status_code,403)
            self.assertEqual(client.get("/api/accounts/articles/"+filename,headers=headers).status_code,404)
            get.assert_called_once_with("users/"+"a"*32+"/drafts/"+filename)
            self.assertEqual(client.post("/api/accounts/articles",json={"content":"text","account_id":"b"*32},headers=headers).status_code,400)

    def test_unauthenticated_requests_cannot_read(self):
        config={"SEO_ACCOUNT_MODE":"1","SEO_OWNER_AUTH":"0","SEO_GUEST_MODE":"0","SEO_DATABASE_URL":"test"}
        with patch.dict("os.environ",config), patch("app.account_auth.current_account",return_value=None), patch("account_store.github_store.list_dir") as listing:
            self.assertEqual(app.test_client().get("/api/accounts/articles").status_code,401)
            listing.assert_not_called()
