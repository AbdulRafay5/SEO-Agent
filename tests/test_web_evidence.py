import unittest
from unittest.mock import patch
from web_evidence import resolve_public, extract_page, PageText
from app import app


class WebEvidenceTests(unittest.TestCase):
    def test_private_dns_rejected(self):
        with patch("web_evidence.socket.getaddrinfo", return_value=[(2,1,6,"",("127.0.0.1",443))]):
            with self.assertRaises(ValueError):
                resolve_public("example.com")

    def test_invalid_urls(self):
        for url in ("http://example.com", "https://user:pass@example.com", "https://example.com:8443", "https://127.0.0.1"):
            with self.assertRaises(ValueError):
                extract_page(url)

    def test_parser(self):
        parser = PageText()
        parser.feed("<head><title>Title</title></head><nav>Menu</nav><main><p>Useful evidence</p><script>bad()</script></main>")
        self.assertEqual(parser.parts, ["Useful evidence"])

    def test_disabled(self):
        with patch.dict("os.environ", {"SEO_WEB_EXTRACTION":"0","SEO_OWNER_AUTH":"0"}):
            self.assertEqual(app.test_client().post("/api/evidence/extract", json={"url":"https://example.com"}).status_code,503)
