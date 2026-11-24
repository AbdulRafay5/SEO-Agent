import unittest
from unittest.mock import patch, Mock
from app import rank_pexels_photos, get_pexels_image, clean_image_search_query


def photo(i, alt):
    return {"id": i, "alt": alt, "src": {"large": f"https://images.pexels.com/photos/{i}/photo.jpg"}}


class ImageRelevanceTests(unittest.TestCase):
    def test_relevant_result_beats_first_result(self):
        photos = [photo(1, "Woman at office desk with laptop"),
                  photo(2, "Fresh basil plants growing in pots on a sunny windowsill")]
        self.assertEqual(rank_pexels_photos(photos, "basil plants pots", "indoor herb gardening", "Growing basil"),
                         [photos[1]["src"]["large"]])

    def test_generic_and_missing_descriptions_are_rejected(self):
        self.assertEqual(rank_pexels_photos([photo(1, "business meeting"), photo(2, "")],
                                           "solar panels roof", "solar energy", "Rooftop installation"), [])
        self.assertEqual(rank_pexels_photos([photo(1, "office desk")], "person working at desk"), [])

    def test_duplicate_and_untrusted_urls_are_rejected(self):
        first = photo(1, "solar panels roof")
        bad = {"alt":"solar panels roof", "src":{"large":"https://example.com/image.jpg"}}
        second = photo(2, "solar panels roof")
        self.assertEqual(rank_pexels_photos([first, bad, second], "solar panels roof",
                                           used_urls={first["src"]["large"]}), [second["src"]["large"]])

    def test_search_falls_back_only_to_relevant_results(self):
        first = Mock(status_code=200)
        first.json.return_value = {"photos":[photo(1,"office desk")]}
        second = Mock(status_code=200)
        second.json.return_value = {"photos":[photo(2,"basil plants pots")]}
        with patch("app.pexels_key","test"), patch("app.requests.get",side_effect=[first,second]) as request:
            self.assertEqual(get_pexels_image("basil plants pots","indoor herb gardening","Growing basil"),
                             photo(2,"")["src"]["large"])
            self.assertEqual(request.call_count,2)
            self.assertEqual(request.call_args_list[0].kwargs["params"]["query"],"basil plant pot")

    def test_rate_limit_does_not_trigger_another_request(self):
        with patch("app.pexels_key","test"), patch("app.requests.get",return_value=Mock(status_code=429)) as request:
            self.assertIsNone(get_pexels_image("solar panels roof","solar energy","Installation"))
            request.assert_called_once()

    def test_query_does_not_default_to_nature(self):
        self.assertEqual(clean_image_search_query("photo of a person"), "")
