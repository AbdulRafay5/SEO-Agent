import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from app import app, generate_ai_text, IncompleteAIResponse, _generation_lock


class ProviderCompletionTests(unittest.TestCase):
    def test_gemini_truncation_rejected(self):
        gemini = Mock()
        gemini.models.generate_content.return_value = SimpleNamespace(
            text="Unfinished", candidates=[SimpleNamespace(finish_reason="MAX_TOKENS")])
        with patch("app.gemini_client", gemini), patch("app.client", None):
            with self.assertRaises(IncompleteAIResponse):
                generate_ai_text("test", 100)

    def test_groq_truncation_rejected(self):
        groq = Mock()
        groq.chat.completions.create.return_value = SimpleNamespace(choices=[
            SimpleNamespace(finish_reason="length", message=SimpleNamespace(content="Incomplete"))])
        with patch("app.gemini_client", None), patch("app.client", groq):
            with self.assertRaises(IncompleteAIResponse):
                generate_ai_text("test", 100)

    def test_complete_groq_response(self):
        groq = Mock()
        groq.chat.completions.create.return_value = SimpleNamespace(choices=[
            SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="Complete article."))])
        with patch("app.gemini_client", None), patch("app.client", groq):
            self.assertEqual(generate_ai_text("test", 100), "Complete article.")

    def test_title_requests_respect_lock(self):
        with _generation_lock, patch("app.generate_title_text") as provider:
            response = app.test_client().get("/api/titles/herbs")
            self.assertEqual(response.status_code, 429)
            provider.assert_not_called()

    def test_keyword_research_respects_lock(self):
        with _generation_lock, patch("app.gemini_client", object()), patch("app.generate_ai_text") as provider:
            response = app.test_client().post("/api/keywords/research", json={"topic":"herbs"})
            self.assertEqual(response.status_code, 200)
            provider.assert_not_called()
            self.assertIn("busy", response.json["ai_status"])
