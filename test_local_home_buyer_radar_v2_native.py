import unittest
from datetime import datetime, timezone

import local_home_buyer_radar_v2_native as native


class LocalHomeBuyerRadarNativeTests(unittest.TestCase):
    def test_extracts_reddit_post_link_from_reader_markdown(self):
        text = "[Buying a home in Germany](https://www.reddit.com/r/germany/comments/abc/buying_a_home/)"
        links = native.extract_markdown_links(text)
        self.assertEqual(len(links), 1)
        self.assertTrue(native.relevant_thread_link(*links[0]))

    def test_rejects_generic_profile_or_index_link(self):
        self.assertFalse(
            native.relevant_thread_link(
                "Germany community",
                "https://www.reddit.com/r/germany/",
            )
        )

    def test_parse_reader_page_builds_classifiable_item(self):
        published = datetime.now(timezone.utc).isoformat()
        text = f"""Title: Buying a home in Germany\nPublished Time: {published}\nMarkdown Content:\nI am looking to buy an apartment in Berlin. Budget €450000 and mortgage pre-approved.\n"""
        item = native.parse_reader_page(
            "Reddit Germany",
            "https://www.reddit.com/r/germany/comments/abc/buying_a_home/",
            text,
            "germany_home",
        )
        self.assertIsNotNone(item)
        lead = native.classify_v2("germany_home", item)
        self.assertIsNotNone(lead)
        self.assertEqual(lead["classification"], "HOT")
        self.assertEqual(lead["buyer_stage"], "READY")


if __name__ == "__main__":
    unittest.main()
