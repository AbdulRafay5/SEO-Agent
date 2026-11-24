import unittest
from unittest.mock import patch
from app import ensure_h1_title, create_unique_blog_filename, replace_image_markers


class CoreRepairTests(unittest.TestCase):
    def test_explicit_heading_is_preserved(self):
        self.assertEqual(ensure_h1_title("# Wrong heading\n\nBody.", "Chosen heading"), "# Chosen heading\n\nBody.")
        self.assertEqual(ensure_h1_title("First paragraph.\n\nSecond paragraph.", "Chosen heading"), "# Chosen heading\n\nFirst paragraph.\n\nSecond paragraph.")
        self.assertEqual(ensure_h1_title("# Chosen heading\n\nBody.", "Chosen heading"), "# Chosen heading\n\nBody.")

    def test_filename_is_bounded_and_unique(self):
        first = create_unique_blog_filename("topic", "a"*300)
        second = create_unique_blog_filename("topic", "a"*300)
        self.assertLess(len(first), 200)
        self.assertNotEqual(first, second)

    def test_media_budget(self):
        text = "\n\n".join("[IMAGE: herbs]" for _ in range(10))
        with patch("app.get_pexels_image", return_value=None) as photo:
            output, photos, diagrams = replace_image_markers(text)
            self.assertEqual(photo.call_count, 4)
            self.assertNotIn("[IMAGE:", output)
            self.assertEqual(photos, 0)
            self.assertEqual(diagrams, 0)
