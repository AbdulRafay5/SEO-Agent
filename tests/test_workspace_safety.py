import unittest
from unittest.mock import patch
from app import app


class WorkspaceSafetyTests(unittest.TestCase):
    def test_explicit_protection_requirement(self):
        with patch.dict("os.environ", {"SEO_REQUIRE_PROTECTED_WORKSPACE":"1","SEO_OWNER_AUTH":"0","SEO_GUEST_MODE":"0","SEO_ACCOUNT_MODE":"0"}):
            for path in ("/", "/api/blog/private.md", "/api/titles/herbs"):
                self.assertEqual(app.test_client().get(path).status_code, 503)
            self.assertEqual(app.test_client().post("/api/generate", json={}).status_code, 503)

    def test_unprotected_local_responses_are_not_cached(self):
        with patch.dict("os.environ", {"SEO_REQUIRE_PROTECTED_WORKSPACE":"0","SEO_OWNER_AUTH":"0","SEO_GUEST_MODE":"0","SEO_ACCOUNT_MODE":"0"}):
            response = app.test_client().post("/api/generate", json={})
            self.assertEqual(response.status_code, 400)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    def test_trends_keyword_limit(self):
        with patch("app.fetch_trends_data") as fetch:
            self.assertEqual(app.test_client().get("/api/trends", query_string={"keyword":"x"*241}).status_code, 400)
            fetch.assert_not_called()

    def test_unsafe_draft_name_rejected_before_storage(self):
        with patch("app.github_store.get_file") as get:
            self.assertEqual(app.test_client().get("/api/blog/a%3Fb.md").status_code, 404)
            get.assert_not_called()
