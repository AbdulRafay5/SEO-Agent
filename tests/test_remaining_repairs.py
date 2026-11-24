import base64
import unittest
from unittest.mock import patch
from app import app
from competitor_research import compare_competitors


class RemainingRepairTests(unittest.TestCase):
    def test_duplicate_competitor_urls_rejected(self):
        entries = [{"url":"https://example.com/article","title":"One","headings":"Care"},
                   {"url":"https://example.com/article/#section","title":"Two","headings":"Care"}]
        with self.assertRaises(ValueError):
            compare_competitors("herbs", entries)

    def test_remote_version_inherits_evidence(self):
        config = {"SEO_REMOTE_VERSIONS":"1","SEO_REMOTE_EVIDENCE":"1","SEO_OWNER_AUTH":"1",
                  "SEO_OWNER_USERNAME":"owner","SEO_OWNER_PASSWORD":"password",
                  "GITHUB_REPO":"example/private","GITHUB_TOKEN":"test"}
        headers = {"Authorization":"Basic "+base64.b64encode(b"owner:password").decode()}
        evidence = {"method":"BM25 lexical retrieval","status":"retrieved","passages":[
            {"source_id":"S1","title":"Herbs","url":"https://example.com/herbs","kind":"excerpt","passage":"Herbs need water."}]}
        with patch.dict("os.environ",config), patch("app.github_store.get_file",return_value=("Original",None)), \
             patch("app.load_remote_evidence",return_value=evidence), patch("app.github_store.save_file",return_value=True), \
             patch("app._upsert_manifest_entry",return_value=True), patch("app.save_remote_evidence",return_value=True) as save:
            response = app.test_client().post("/api/blog/versions",headers=headers,json={
                "content":"# Revised\n\nHerbs need water [S1].","keyword":"herbs","version_of":"original.md"})
            self.assertEqual(response.status_code,201)
            self.assertTrue(response.json["evidence_saved"])
            self.assertEqual(save.call_args.args[2],evidence)
