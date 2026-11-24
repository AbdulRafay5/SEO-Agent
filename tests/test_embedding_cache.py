import unittest
from unittest.mock import Mock, patch
from evidence_retrieval import EmbeddingCache
from app import select_evidence


class EmbeddingCacheTests(unittest.TestCase):
    def test_reuses_and_deduplicates_texts(self):
        cache = EmbeddingCache()
        provider = Mock(return_value=[[1, 0], [0, 1]])
        expected = [[1, 0], [0, 1], [1, 0]]
        self.assertEqual(cache.embed("model", ["a", "b", "a"], provider), expected)
        provider.assert_called_once_with(["a", "b"])
        self.assertEqual(cache.embed("model", ["a", "b", "a"], provider), expected)
        self.assertEqual(provider.call_count, 1)

    def test_model_isolation(self):
        cache = EmbeddingCache()
        provider = Mock(side_effect=[[[1, 0]], [[0, 1]]])
        self.assertEqual(cache.embed("model-a", ["a"], provider), [[1, 0]])
        self.assertEqual(cache.embed("model-b", ["a"], provider), [[0, 1]])
        self.assertEqual(provider.call_count, 2)

    def test_ttl(self):
        now = [0]
        cache = EmbeddingCache(ttl=10, clock=lambda: now[0])
        provider = Mock(return_value=[[1, 0]])
        cache.embed("model", ["a"], provider)
        now[0] = 11
        cache.embed("model", ["a"], provider)
        self.assertEqual(provider.call_count, 2)

    def test_lru(self):
        cache = EmbeddingCache(capacity=2)
        provider = Mock(side_effect=lambda texts: [[1, 0] for _ in texts])
        cache.embed("model", ["a", "b"], provider)
        cache.embed("model", ["a"], provider)
        cache.embed("model", ["c"], provider)
        cache.embed("model", ["b"], provider)
        self.assertEqual(provider.call_count, 3)
        self.assertEqual(provider.call_args.args[0], ["b"])

    def test_failed_response_not_cached(self):
        cache = EmbeddingCache()
        provider = Mock(side_effect=[[[float("nan"), 0]], [[1, 0]]])
        with self.assertRaises(ValueError):
            cache.embed("model", ["a"], provider)
        self.assertEqual(cache.embed("model", ["a"], provider), [[1, 0]])
        self.assertEqual(provider.call_count, 2)

    def test_anonymous_requests_bypass_cache(self):
        from evidence_retrieval import validate_sources
        provider = Mock()
        provider.models.embed_content.return_value.embeddings = [Mock(values=[1,0]), Mock(values=[1,0])]
        with patch.dict("os.environ", {"SEO_EMBEDDING_CACHE":"1","SEO_OWNER_AUTH":"0","SEO_SEMANTIC_RETRIEVAL":"1"}), patch("app.gemini_client", provider), patch("app._embedding_cache.embed") as cached:
            rows, method = select_evidence("herbs", validate_sources([{"text":"herbs need light"}]), "hybrid")
        cached.assert_not_called()
        self.assertIn("Hybrid", method)
        self.assertTrue(rows)
