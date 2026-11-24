import unittest
from unittest.mock import patch
from app import app
from account_auth import normalize_username, validate_password, valid_token, token_hash


class AccountAuthTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(normalize_username(" Alice_123 "), "alice_123")
        for value in ("ab", "a/b", None):
            with self.assertRaises(ValueError):
                normalize_username(value)
        with self.assertRaises(ValueError):
            validate_password("short")

    def test_token_validation(self):
        self.assertTrue(valid_token("a"*43))
        self.assertFalse(valid_token("a"*42))
        self.assertEqual(len(token_hash("a"*43)),64)

    def test_disabled_by_default(self):
        with patch.dict("os.environ", {"SEO_ACCOUNT_MODE":"0","SEO_OWNER_AUTH":"0","SEO_GUEST_MODE":"0"}):
            self.assertEqual(app.test_client().post("/api/accounts/register").status_code,404)

    def test_restricted_and_cookie(self):
        config = {"SEO_ACCOUNT_MODE":"1","SEO_OWNER_AUTH":"0","SEO_GUEST_MODE":"0","SEO_DATABASE_URL":"test","SEO_ACCOUNT_SETUP_KEY":"k"*32}
        with patch.dict("os.environ",config), patch("app.account_auth.login",return_value="a"*43):
            client=app.test_client()
            self.assertEqual(client.post("/api/accounts/login",json={}).status_code,403)
            response=client.post("/api/accounts/login",json={"username":"alice","password":"longpassword12"},headers={"X-Account-Setup-Key":"k"*32})
            self.assertEqual(response.status_code,200)
            cookie=response.headers["Set-Cookie"]
            for flag in ("Secure","HttpOnly","SameSite=Strict"):
                self.assertIn(flag,cookie)

    def test_workspace_fails_closed(self):
        config={"SEO_ACCOUNT_MODE":"1","SEO_OWNER_AUTH":"0","SEO_GUEST_MODE":"0","SEO_DATABASE_URL":"test"}
        with patch.dict("os.environ",config), patch("app.account_auth.current_account",return_value={"id":"a","username":"alice"}), patch("app.github_store.list_dir") as listing:
            self.assertEqual(app.test_client().get("/").status_code,503)
            listing.assert_not_called()
