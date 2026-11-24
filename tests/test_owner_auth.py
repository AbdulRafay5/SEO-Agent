import base64
import unittest
from unittest.mock import patch
from app import app


class OwnerAuthTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def authorization(self, user, password):
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def test_disabled_keeps_existing_api(self):
        with patch.dict("os.environ", {"SEO_OWNER_AUTH": "0"}):
            response = self.client.post("/api/editor/revise", json={})
            self.assertEqual(response.status_code, 400)

    def test_protects_home_drafts_and_generation(self):
        with patch.dict("os.environ", {"SEO_OWNER_AUTH":"1","SEO_OWNER_USERNAME":"owner","SEO_OWNER_PASSWORD":"test-password"}):
            for path in ("/", "/api/blog/private.md", "/blog/private.md"):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401)
                self.assertIn("Basic", response.headers["WWW-Authenticate"])
            self.assertEqual(self.client.post("/api/generate", json={}).status_code, 401)
            self.assertEqual(self.client.post("/api/editor/revise", json={}).status_code, 401)

    def test_valid_credentials_reach_route(self):
        with patch.dict("os.environ", {"SEO_OWNER_AUTH":"1","SEO_OWNER_USERNAME":"owner","SEO_OWNER_PASSWORD":"test-password"}):
            response = self.client.post("/api/editor/revise", json={}, headers=self.authorization("owner","test-password"))
            self.assertEqual(response.status_code, 400)
            self.assertIn("no-store", response.headers["Cache-Control"])
            self.assertIn("Authorization", response.headers["Vary"])

    def test_wrong_credentials_rejected(self):
        with patch.dict("os.environ", {"SEO_OWNER_AUTH":"1","SEO_OWNER_USERNAME":"owner","SEO_OWNER_PASSWORD":"test-password"}):
            self.assertEqual(self.client.get("/", headers=self.authorization("owner","wrong")).status_code, 401)

    def test_incomplete_configuration_fails_closed(self):
        with patch.dict("os.environ", {"SEO_OWNER_AUTH":"1","SEO_OWNER_USERNAME":"owner","SEO_OWNER_PASSWORD":""}):
            self.assertEqual(self.client.get("/").status_code, 503)
