import unittest
from evidence_retrieval import citation_report


class CitationTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{"source_id":"S1","title":"Guide","url":"https://example.com","kind":"excerpt"},
                        {"source_id":"S2","title":"Another guide","url":"","kind":"excerpt"}]

    def test_known_and_unknown(self):
        report = citation_report("Claim [S1]. Another [S1, S9].", self.sources)
        self.assertEqual(report["status"], "unknown_ids")
        self.assertEqual(report["cited_sources"][0]["mentions"], 2)
        self.assertEqual(report["unknown_ids"][0]["source_id"], "S9")
        self.assertEqual(report["uncited_sources"][0]["source_id"], "S2")

    def test_known_ids(self):
        self.assertEqual(citation_report("Fact [S1].", self.sources)["status"], "known_ids")

    def test_missing_citations(self):
        self.assertEqual(citation_report("Article without references.", self.sources)["status"], "no_citations")

    def test_code_ignored(self):
        report = citation_report("Example \x60[S9]\x60\n\n~~~\n[S8]\n~~~\n\nFact [S1].", self.sources)
        self.assertEqual(report["status"], "known_ids")
        self.assertEqual(report["citation_count"], 1)

    def test_repeated_passages_same_source(self):
        report = citation_report("Fact [S1].", [self.sources[0], self.sources[0]])
        self.assertEqual(report["available_sources"], 1)
