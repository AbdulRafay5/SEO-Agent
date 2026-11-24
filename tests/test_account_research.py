import unittest
from unittest.mock import patch
from account_store import AccountStore
from app import app


class AccountResearchTests(unittest.TestCase):
    def test_research_and_article_isolation(self):
        files = {}
        def save(path, content, **kwargs):
            self.assertIsNone(kwargs["expected_sha"])
            files[path] = content
            return True
        def get(path):
            return files.get(path), None
        first, second = AccountStore("a"*32), AccountStore("b"*32)
        with patch("account_store.github_store.save_file", side_effect=save), patch("account_store.github_store.get_file", side_effect=get):
            research = first.create_research({"title":"Herbs","text":"Herbs need sunlight."})
            filename = research["filename"]
            self.assertIsNone(second.read_research(filename))
            with self.assertRaises(ValueError):
                second.create_article("Private", "herbs", research_ids=[filename])
            article = first.create_article("Herbs need sunlight [S1].", "herbs", research_ids=[filename])
            self.assertEqual(article["evidence"]["passages"][0]["source_id"], "S1")
            self.assertEqual(article["evidence"]["passages"][0]["passage"], "Herbs need sunlight.")
            revision = first.create_article("Updated text [S2].", version_of=article["filename"])
            self.assertEqual(revision["evidence"]["passages"], article["evidence"]["passages"])
            self.assertEqual(first.read_article(revision["filename"])["evidence"]["citations"], revision["evidence"]["citations"])

    def test_research_validation(self):
        store = AccountStore("a"*32)
        with patch("account_store.github_store.get_file") as get:
            for ids in ("string", ["../private.json"], ["a"*32+".json"]*2):
                with self.assertRaises(ValueError):
                    store.resolve_research(ids)
            get.assert_not_called()
        with self.assertRaises(ValueError):
            store.create_research({"text":""})

    def test_research_api_scope(self):
        config = {"SEO_ACCOUNT_MODE":"1","SEO_OWNER_AUTH":"0","SEO_GUEST_MODE":"0","SEO_DATABASE_URL":"test","SEO_ACCOUNT_SETUP_KEY":"k"*32}
        headers = {"X-Account-Setup-Key":"k"*32}
        with patch.dict("os.environ",config), patch("app.account_auth.current_account",return_value={"id":"a"*32,"username":"alice"}), patch("app.github_store._configured",return_value=True), patch("account_store.github_store.get_file",return_value=(None,None)) as get:
            client = app.test_client()
            filename = "b"*32+".json"
            self.assertEqual(client.get("/api/accounts/research/"+filename).status_code,403)
            self.assertEqual(client.get("/api/accounts/research/"+filename,headers=headers).status_code,404)
            get.assert_called_once_with("users/"+"a"*32+"/research/"+filename)
            self.assertEqual(client.post("/api/accounts/research",json={"source":{"text":"test"},"account_id":"b"*32},headers=headers).status_code,400)
