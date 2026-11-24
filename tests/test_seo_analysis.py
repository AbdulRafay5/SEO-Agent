import unittest
from seo_analysis import analyze_article


class SeoAnalysisTests(unittest.TestCase):
    def test_heading_and_keyword(self):
        result = analyze_article("# Indoor herbs\n\nIndoor herbs are easy to grow.\n\n## Care\n\nWater regularly.", "indoor herbs")
        self.assertEqual(result["keyword_count"], 2)
        self.assertEqual(result["heading_count"], 2)
        self.assertEqual(result["checks"][0]["status"], "pass")

    def test_optional_checks(self):
        result = analyze_article("# Topic\n\nText.")
        checks = {check["name"]: check["status"] for check in result["checks"]}
        self.assertEqual(checks["Meta description"], "not applicable")
        self.assertEqual(checks["Image descriptions"], "not applicable")
        self.assertEqual(checks["Keyword in title"], "not applicable")

    def test_unicode(self):
        result = analyze_article("# Jardinería\n\nLa jardinería es útil.", "JARDINERÍA")
        self.assertEqual(result["keyword_count"], 2)

    def test_images_and_links(self):
        result = analyze_article("# Plants\n\n![Leaves](https://example.com/leaf.jpg)\n\n[Guide](https://example.com/guide)")
        self.assertEqual(result["image_count"], 1)
        self.assertEqual(result["link_count"], 1)
