import unittest
from unittest.mock import patch
from evidence_retrieval import validate_sources, retrieve_hybrid, cosine
from app import app


class HybridRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.sources = validate_sources([{"text":"Automobiles require regular servicing."},{"text":"Flowers need water."}])

    def test_semantic_match_without_exact_words(self):
        rows, method = retrieve_hybrid("car maintenance", self.sources, lambda texts: [[1,0],[1,0],[0,1]])
        self.assertEqual(rows[0]["source_id"], "S1")
        self.assertIn("Hybrid", method)

    def test_provider_error_falls_back(self):
        def offline(texts):
            raise RuntimeError("Offline")
        rows, method = retrieve_hybrid("flowers", self.sources, offline)
        self.assertEqual(method, "BM25 fallback")
        self.assertEqual(rows[0]["source_id"], "S2")

    def test_cosine_invalid_vector(self):
        with self.assertRaises(ValueError):
            cosine([1,0], [0,0])

    def test_disabled_provider_fallback(self):
        with patch.dict("os.environ", {"SEO_SEMANTIC_RETRIEVAL":"0"}):
            response = app.test_client().post("/api/evidence/preview", json={"topic":"flowers","evidence_sources":self.sources,"evidence_mode":"hybrid"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["method"], "BM25 fallback")

    def test_invalid_mode(self):
        response = app.test_client().post("/api/evidence/preview", json={"topic":"flowers","evidence_mode":[]})
        self.assertEqual(response.status_code,400)
