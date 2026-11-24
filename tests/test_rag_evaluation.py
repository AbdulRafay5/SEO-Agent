import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from rag_evaluation import evaluate, metrics


class RAGEvaluationTests(unittest.TestCase):
    def test_metrics(self):
        result = metrics(["S2", "S1", "S1"], ["S1", "S3"], 3)
        self.assertAlmostEqual(result["precision_at_k"], 1/3)
        self.assertEqual(result["recall_at_k"], 0.5)
        self.assertEqual(result["mrr_at_k"], 0.5)
        self.assertGreater(result["ndcg_at_k"], 0)
        self.assertTrue(metrics([], [], 3)["no_match_correct"])

    def test_fixture_regression(self):
        report = evaluate()
        rows = {(row["case"], row["mode"]): row for row in report["cases"]}
        for name in ("gardening", "software", "finance", "spanish", "french", "urdu"):
            self.assertEqual(rows[name, "lexical"]["recall_at_k"], 1, name)
        self.assertTrue(rows["no_match", "lexical"]["no_match_correct"])
        self.assertEqual(rows["semantic_paraphrase", "hybrid_mock"]["ranked"], ["S1"])
        self.assertEqual(rows["semantic_paraphrase", "lexical"]["recall_at_k"], 0)
        self.assertEqual(rows["partial_overlap", "lexical"]["ranked"][0], "S1")
        # Japanese is deliberately reported, not asserted as supported.

    def test_generation_receives_selected_evidence(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch("app.BLOGS_FOLDER", folder), \
             patch("app.LAST_GEN_FILE", str(Path(folder) / "last.txt")), \
             patch("app.MIN_WORD_COUNT", 1), \
             patch("app.gemini_client", object()), \
             patch("app.github_store.save_file"), \
             patch("app._upsert_manifest_entry"), \
             patch("app.generate_ai_text", return_value="# Herb care\n\nHerbs need sunlight [S1].") as generator:
            response = app.test_client().post("/api/generate", json={
                "primary_keyword": "herbs sunlight",
                "title": "Herb care",
                "evidence_sources": [
                    {"title":"Garden guide","text":"Herbs need sunlight."},
                    {"title":"Unrelated","text":"Engines require oil."}
                ]
            })
            self.assertEqual(response.status_code, 200)
            prompt = generator.call_args.args[0]
            self.assertIn("Herbs need sunlight.", prompt)
            self.assertNotIn("Engines require oil.", prompt)
            evidence = response.get_json()["evidence"]
            self.assertEqual(evidence["status"], "retrieved")
            self.assertEqual(evidence["citations"]["status"], "known_ids")
            self.assertEqual(evidence["citations"]["cited_sources"][0]["source_id"], "S1")
