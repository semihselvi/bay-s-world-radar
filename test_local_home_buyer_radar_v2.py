import unittest

import local_home_buyer_radar_v2_stagefix as radar


class LocalHomeBuyerRadarV2Tests(unittest.TestCase):
    def item(self, text, title="User discussion", query="", url="https://www.reddit.com/r/example/comments/123", published=""):
        return {
            "source": "Test",
            "url": url,
            "title": title,
            "text": text,
            "published": published,
            "author": "user",
            "discovery_query": query,
        }

    def test_germany_ready_buyer_is_hot(self):
        lead = radar.classify_v2("germany_home", self.item(
            "Ich suche eine Wohnung zum Kauf in Berlin. Budget €480000 und Eigenkapital ist vorhanden."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["classification"], "HOT")
        self.assertEqual(lead["buyer_stage"], "READY")
        self.assertEqual(lead["requirements"].get("city"), "Berlin")
        self.assertEqual(lead["requirements"].get("property_type"), "apartment")

    def test_netherlands_active_buyer(self):
        lead = radar.classify_v2("netherlands_home", self.item(
            "Ik zoek een huis om te kopen in Utrecht. Budget €550000 en hypotheek is besproken."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["buyer_stage"], "ACTIVE")
        self.assertEqual(lead["requirements"].get("city"), "Utrecht")
        self.assertEqual(lead["requirements"].get("property_type"), "house")

    def test_belgium_french_buyer(self):
        lead = radar.classify_v2("belgium_home", self.item(
            "Je cherche un appartement à acheter à Bruxelles. Budget €350000 et apport disponible."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["target_market"], "belgium")
        self.assertEqual(lead["buyer_stage"], "READY")

    def test_switzerland_ready_buyer(self):
        lead = radar.classify_v2("switzerland_home", self.item(
            "Wir suchen eine Wohnung zum Kauf in Zürich. Eigenkapital CHF 250000 ist vorhanden."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["classification"], "HOT")
        self.assertEqual(lead["buyer_stage"], "READY")

    def test_rejects_rental(self):
        lead = radar.classify_v2("germany_home", self.item(
            "Ich suche eine Mietwohnung in Berlin. Monatsmiete bis €1600."
        ))
        self.assertIsNone(lead)

    def test_rejects_seller(self):
        lead = radar.classify_v2("belgium_home", self.item(
            "Je vends un appartement à Bruxelles. Agence immobilière, contactez-nous sur WhatsApp."
        ))
        self.assertIsNone(lead)

    def test_rejects_german_resident_buying_spain(self):
        lead = radar.classify_v2("germany_home", self.item(
            "I live in Germany and I want to buy a house in Spain. My budget is €300000."
        ))
        self.assertIsNone(lead)

    def test_accepts_spanish_resident_buying_berlin(self):
        lead = radar.classify_v2("germany_home", self.item(
            "I live in Spain but I am looking to buy an apartment in Berlin. Budget €420000."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["requirements"].get("city"), "Berlin")

    def test_rejects_dutch_resident_buying_portugal(self):
        lead = radar.classify_v2("netherlands_home", self.item(
            "Ik woon in Nederland en wil een huis in Portugal kopen. Budget €300000."
        ))
        self.assertIsNone(lead)

    def test_accepts_belgium_target_from_foreign_resident(self):
        lead = radar.classify_v2("belgium_home", self.item(
            "I currently live in France and want to buy an apartment in Brussels. Budget €400000."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["target_market"], "belgium")

    def test_query_context_bridge_is_warm_when_date_unknown(self):
        lead = radar.classify_v2("netherlands_home", self.item(
            "Looking for an apartment to buy. Budget €420000.",
            query='site:reddit.com Netherlands "looking to buy apartment"'
        ))
        self.assertIsNotNone(lead)
        self.assertTrue(lead.get("target_context_bridge"))
        self.assertEqual(lead["classification"], "WARM")
        self.assertFalse(lead["freshness_verified"])

    def test_extracts_bedrooms_finance_and_timeframe(self):
        lead = radar.classify_v2("germany_home", self.item(
            "Ich suche eine 3 Zimmer Wohnung zum Kauf in Hamburg. Budget €650000, Finanzierung steht. Dieses Jahr."
        ))
        self.assertIsNotNone(lead)
        req = lead["requirements"]
        self.assertEqual(req.get("city"), "Hamburg")
        self.assertEqual(req.get("bedrooms"), 3)
        self.assertEqual(req.get("financing"), "mentioned")
        self.assertTrue(req.get("timeframe"))

    def test_same_content_has_same_semantic_key_across_urls(self):
        lead1 = radar.classify_v2("germany_home", self.item(
            "Ich suche eine Wohnung zum Kauf in Berlin. Budget €480000.",
            url="https://www.reddit.com/r/a/comments/1"
        ))
        lead2 = radar.classify_v2("germany_home", self.item(
            "Ich suche eine Wohnung zum Kauf in Berlin. Budget €480000.",
            url="https://www.reddit.com/r/b/comments/2"
        ))
        self.assertIsNotNone(lead1)
        self.assertIsNotNone(lead2)
        self.assertEqual(radar.semantic_key("germany_home", lead1), radar.semantic_key("germany_home", lead2))

    def test_selected_queries_keep_core_queries(self):
        selected = radar.selected_queries("switzerland_home", 10)
        for query in radar.radar.CORE_QUERIES["switzerland_home"]:
            self.assertIn(query, selected)
        self.assertEqual(len(selected), 10)


if __name__ == "__main__":
    unittest.main()
