import unittest
from evidence_retrieval import retrieve, validate_sources
from seo_analysis import analyze_article
from app import app


class MultilingualRepairTests(unittest.TestCase):
    def test_chinese_matching(self):
        sources = validate_sources([{"text":"屋顶太阳能发电需要合适的设备。"},{"text":"烹饪米饭需要水。"}])
        self.assertEqual([r["source_id"] for r in retrieve("太阳能发电", sources)], ["S1"])

    def test_late_unsegmented_passage(self):
        sources = validate_sources([{"text":"料理には水が必要です。"*300+"太陽光発電は屋根で行います。"}])
        rows = retrieve("太陽光発電", sources)
        self.assertTrue(rows)
        self.assertIn("太陽光発電", rows[0]["passage"])

    def test_preview_includes_title(self):
        response = app.test_client().post("/api/evidence/preview", json={"topic":"garden","title":"sunlight","evidence_sources":[{"text":"Sunlight is important."}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["passages"][0]["source_id"], "S1")

    def test_metrics_ignore_code_and_source_ids(self):
        result = analyze_article("# Herbs\n\nHerbs grow [S1].\n\n~~~python\n# Fake heading\n![fake](https://example.com/a)\nherbs\n~~~", "herbs")
        self.assertEqual(result["keyword_count"], 2)
        self.assertEqual(result["word_count"], 3)
        self.assertEqual(result["image_count"], 0)
        self.assertEqual(result["heading_count"], 1)
