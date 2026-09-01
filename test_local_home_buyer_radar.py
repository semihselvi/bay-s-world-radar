import unittest

import local_home_buyer_radar as radar


class LocalHomeBuyerRadarTests(unittest.TestCase):
    def item(self, text, title="User discussion", query="", url="https://www.reddit.com/r/example/comments/123"):
        return {
            "source": "Test",
            "url": url,
            "title": title,
            "text": text,
            "published": "",
            "author": "user",
            "discovery_query": query,
        }

    def test_germany_home_buyer_hot(self):
        lead = radar.classify("germany_home", self.item(
            "Ich suche eine Wohnung zum Kauf in Berlin. Budget €480.000 und Eigenkapital ist vorhanden."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["target_market"], "germany")
        self.assertEqual(lead["classification"], "HOT")

    def test_netherlands_home_buyer(self):
        lead = radar.classify("netherlands_home", self.item(
            "Ik zoek een huis om te kopen in Utrecht. Budget €550000 en hypotheek is al besproken."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["target_market"], "netherlands")

    def test_belgium_home_buyer_french(self):
        lead = radar.classify("belgium_home", self.item(
            "Je cherche un appartement à acheter à Bruxelles. Budget de €350000."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["target_market"], "belgium")

    def test_switzerland_home_buyer(self):
        lead = radar.classify("switzerland_home", self.item(
            "Wir suchen eine Wohnung zum Kauf in Zürich. Eigenkapital CHF 250000."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["target_market"], "switzerland")
        self.assertEqual(lead["classification"], "HOT")

    def test_rejects_rental(self):
        lead = radar.classify("germany_home", self.item(
            "Ich suche eine Mietwohnung in Berlin. Monatsmiete bis €1600."
        ))
        self.assertIsNone(lead)

    def test_rejects_seller(self):
        lead = radar.classify("belgium_home", self.item(
            "Je vends un appartement à Bruxelles. Agence immobilière, contactez-nous sur WhatsApp."
        ))
        self.assertIsNone(lead)

    def test_rejects_wrong_country(self):
        lead = radar.classify("germany_home", self.item(
            "I am looking to buy a house in Spain. Budget €300000."
        ))
        self.assertIsNone(lead)

    def test_query_context_bridge(self):
        lead = radar.classify("netherlands_home", self.item(
            "Looking for an apartment to buy. Budget €420000.",
            query='site:reddit.com Netherlands "looking to buy apartment"'
        ))
        self.assertIsNotNone(lead)
        self.assertTrue(lead.get("target_context_bridge"))


if __name__ == "__main__":
    unittest.main()
