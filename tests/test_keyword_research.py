import unittest
from keyword_research import combine_keywords, infer_intent, parse_ai_suggestions


class KeywordResearchTests(unittest.TestCase):
    def test_invalid_ai_output(self):
        self.assertEqual(parse_ai_suggestions("not JSON"), [])

    def test_merge_and_provenance(self):
        ai = parse_ai_suggestions('[{"keyword":"Indoor herbs","intent":"informational","cluster":"Growing"}]')
        rows = combine_keywords("indoor herbs", ai, {"top_queries":[{"query":"INDOOR HERBS","value":90}]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trend_top"], 90)
        self.assertEqual(rows[0]["cluster"], "Growing")
        self.assertEqual(len(rows[0]["sources"]), 3)
        self.assertIsNone(rows[0]["search_volume"])
        self.assertIsNone(rows[0]["difficulty"])

    def test_intent(self):
        self.assertEqual(infer_intent("how to grow herbs"), "informational")
        self.assertEqual(infer_intent("buy seeds"), "transactional")

    def test_unicode_query(self):
        rows = combine_keywords("jardinería", [], {"rising_queries":[{"query":"semillas","value":"Breakout"}]})
        self.assertEqual(rows[1]["trend_rising"], "Breakout")
