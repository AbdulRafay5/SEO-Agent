import unittest
from app import distribute_media_markers


class MediaPlacementTests(unittest.TestCase):
    def test_media_not_moved_to_unrelated_sections(self):
        article = "# Garden\n\n## Watering\n\nWater regularly.\n\n## Harvest\n\nPick ripe tomatoes.\n\n[IMAGE: ripe tomatoes]\n\n[IMAGE: tomatoes in a basket]"
        self.assertEqual(distribute_media_markers(article), article)

    def test_article_without_media_unchanged(self):
        article = "# Topic\n\n## Details\n\nExample."
        self.assertEqual(distribute_media_markers(article), article)
