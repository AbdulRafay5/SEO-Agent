import unittest
from evidence_retrieval import validate_sources, retrieve, evidence_prompt
from app import app


class EvidenceTests(unittest.TestCase):
    def test_relevant_source(self):
        sources = validate_sources([{"title":"Cooking","text":"Herbs need sunlight and water."},{"title":"Cars","text":"Engines need oil."}])
        result = retrieve("herbs sunlight", sources)
        self.assertEqual(result[0]["source_id"], "S1")
        self.assertEqual(len(result), 1)
        self.assertIn("Herbs need sunlight", evidence_prompt(result))

    def test_no_matches(self):
        self.assertEqual(retrieve("volcano", validate_sources([{"text":"Herbs need water."}])), [])
        self.assertEqual(evidence_prompt([]), "")

    def test_validation(self):
        for sources in ([{"text":"abc","url":"file:///etc/passwd"}], [{"text":""}], [{"text":"x"*12001}], [{}]*6):
            with self.assertRaises(ValueError):
                validate_sources(sources)

    def test_preview_api(self):
        response = app.test_client().post("/api/evidence/preview", json={"topic":"herbs","evidence_sources":[{"text":"Herbs need water."}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["passages"][0]["source_id"], "S1")

    def test_bad_generation_evidence(self):
        response = app.test_client().post("/api/generate", json={"primary_keyword":"herbs","evidence_sources":"invalid"})
        self.assertEqual(response.status_code, 400)

    def test_snippet_provenance(self):
        sources = validate_sources([{"text":"Herbs need sunlight.", "kind":"search_snippet"}])
        result = retrieve("herbs", sources)
        self.assertEqual(result[0]["kind"], "search_snippet")
        self.assertIn("not full documents", evidence_prompt(result))

    def test_invalid_kind(self):
        with self.assertRaises(ValueError):
            validate_sources([{"text":"Herbs", "kind":[]}])

    def test_online_search_mock(self):
        from unittest.mock import patch, Mock
        response = Mock(status_code=200)
        response.json.return_value = {"web":{"results":[{"url":"https://example.com/herbs","title":"Herbs","description":"Herbs need light"}]}}
        with patch.dict("os.environ", {"BRAVE_SEARCH_API_KEY":"test"}), patch("app.requests.get", return_value=response):
            result = app.test_client().post("/api/evidence/search", json={"topic":"herbs","geo":"GB"})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.get_json()["results"][0]["snippet"], "Herbs need light")
