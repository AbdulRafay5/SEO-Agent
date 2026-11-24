import unittest
from app import build_prompt


class EditorialPromptTests(unittest.TestCase):
    def test_preserves_brief(self):
        prompt = build_prompt("urban gardening", "Urban Gardening Guide", "Teach beginners", "Which plants?", "conversational", [{"keyword":"balcony plants","count":3}], "Spanish", "beginners", "Spain", "https://example.com/guide")
        for value in ("urban gardening", "Urban Gardening Guide", "Teach beginners", "Which plants?", "conversational", "balcony plants", "Spanish", "beginners", "Spain", "https://example.com/guide"):
            self.assertIn(value, prompt)

    def test_editorial_structure(self):
        prompt = build_prompt("gardening")
        for value in ("H2/H3", "FAQs", "grammatically complete", "never stack", "not retrieved evidence", "never imply it was inspected"):
            self.assertIn(value, prompt)
        self.assertIn("worldwide; do not assume a country", prompt)
        self.assertNotIn("ExampleBrand", prompt)
