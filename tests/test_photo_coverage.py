import unittest
from unittest.mock import patch, Mock
from app import add_section_photo_candidates, replace_image_markers, rank_pexels_photos


class PhotoCoverageTests(unittest.TestCase):
    def test_candidates_from_visual_sections(self):
        body = "# Coffee farm\n\n## Coffee seedlings\n\n" + "Plant seedlings in suitable soil. "*4 + "\n\n## Coffee cherry harvest\n\n" + "Pick the ripe cherries by hand. "*4 + "\n\n## Coffee bean drying\n\n" + "Dry the beans in a clean area. "*4
        with patch("app.pexels_key", "test"):
            planned = add_section_photo_candidates(body, "coffee farm", 3)
        self.assertEqual(planned.count("[IMAGE:"), 3)
        self.assertIn("seedling", planned)
        self.assertIn("harvest", planned)
        self.assertIn("drying", planned)

    def test_no_generic_abstract_fallback(self):
        body = "# Accounting\n\n## Benefits\n\n" + "Understand the rules. "*5
        with patch("app.pexels_key", "test"):
            self.assertEqual(add_section_photo_candidates(body, "accounting", 3), body)

    def test_sparse_but_topic_specific_metadata(self):
        url = "https://images.pexels.com/photos/1/photo.jpg"
        photos = [{"alt":"Coffee cherries", "src":{"large":url}}]
        self.assertEqual(rank_pexels_photos(photos, "coffee cherries ripe harvest branch basket", "coffee farm"), [url])

    def test_three_photos_with_section_fallback(self):
        body = "# Coffee farm\n\n## Coffee seedlings\n\n" + "Plant seedlings in suitable soil. "*4 + "\n\n## Coffee cherry harvest\n\n" + "Pick the ripe cherries by hand. "*4 + "\n\n## Coffee bean drying\n\n" + "Dry the beans in a clean area. "*4
        urls = [f"https://images.pexels.com/photos/{i}/photo.jpg" for i in range(3)]
        with patch("app.pexels_key", "test"), patch("app.get_pexels_image", side_effect=urls) as fetch:
            result, count, _ = replace_image_markers(body, "coffee farm", 3)
        self.assertEqual(count, 3)
        self.assertEqual(fetch.call_count, 3)
        self.assertNotIn("[IMAGE:", result)
