import unittest
from competitor_research import compare_competitors
from app import app


class CompetitorTests(unittest.TestCase):
    def test_coverage(self):
        result = compare_competitors("indoor herbs", [
            {"url":"https://example.com/a","title":"Indoor herbs","headings":"Watering\nLight\nWatering"},
            {"url":"https://example.org/b","title":"Garden guide","headings":"watering\nSoil"}
        ], "# Indoor herbs\n\n## Watering\n\nText.")
        self.assertEqual(result["themes"][0]["heading"], "Watering")
        self.assertEqual(result["themes"][0]["competitors"], 2)
        self.assertTrue(result["themes"][0]["in_draft"])
        self.assertTrue(result["competitors"][0]["topic_in_title"])

    def test_invalid_url(self):
        with self.assertRaises(ValueError):
            compare_competitors("herbs", [{"url":"file:///etc/passwd","title":"bad"}])

    def test_api(self):
        client = app.test_client()
        response = client.post("/api/competitors/compare", json={"topic":"herbs","competitors":[{"url":"https://example.com","title":"Herbs","headings":"Care"}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["themes"][0]["heading"], "Care")

    def test_invalid_input(self):
        self.assertEqual(app.test_client().post("/api/competitors/compare",json={"topic":"herbs","competitors":[]}).status_code,400)

    def test_live_search_no_key(self):
        from unittest.mock import patch
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY": ""}):
            self.assertEqual(app.test_client().post("/api/competitors/search", json={"topic":"herbs"}).status_code, 503)

    def test_live_search_mock(self):
        from unittest.mock import patch, Mock
        response = Mock(status_code=200)
        response.json.return_value = {"web":{"results":[{"url":"https://example.com/herbs","title":"<b>Herbs</b>","description":"Guide"}]}}
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY":"test"}), patch("app.requests.get", return_value=response) as get:
            result = app.test_client().post("/api/competitors/search", json={"topic":"herbs","geo":"GB"})
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.get_json()["results"][0]["title"],"Herbs")
            self.assertEqual(get.call_args.kwargs["params"]["country"],"GB")
