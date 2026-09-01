import unittest

import audience_radar as ar


class AudienceRadarTests(unittest.TestCase):
    def item(self, text, url="https://www.reddit.com/r/example/comments/123", title="User discussion"):
        return {
            "source": "Test",
            "url": url,
            "title": title,
            "text": text,
            "published": "",
            "author": "user",
        }

    def test_germany_buyer_abroad(self):
        lead = ar.classify("germany", self.item(
            "I live in Germany and I am planning to buy a second home abroad. My budget is €180,000."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["classification"], "HOT")

    def test_germany_north_cyprus_target(self):
        lead = ar.classify("germany", self.item(
            "Ich wohne in Deutschland und möchte eine Wohnung in Nordzypern kaufen. Budget €140.000."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["target_market"], "north_cyprus")

    def test_netherlands_buyer(self):
        lead = ar.classify("netherlands", self.item(
            "Ik woon in Nederland en wil een tweede huis in het buitenland kopen. Budget €220.000."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["classification"], "HOT")

    def test_belgium_buyer_french(self):
        lead = ar.classify("belgium", self.item(
            "Je vis en Belgique et je cherche une maison à acheter à l'étranger. Budget de €250000."
        ))
        self.assertIsNotNone(lead)

    def test_switzerland_buyer(self):
        lead = ar.classify("switzerland", self.item(
            "Wir wohnen in der Schweiz und möchten eine Ferienwohnung im Ausland kaufen. Eigenkapital €200000."
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["classification"], "HOT")

    def test_rejects_rental(self):
        lead = ar.classify("germany", self.item(
            "I live in Germany and I am looking to rent an apartment abroad for €900 per month."
        ))
        self.assertIsNone(lead)

    def test_rejects_seller_ad(self):
        lead = ar.classify("netherlands", self.item(
            "Netherlands investors: apartment for sale, contact us, WhatsApp us, real estate agent, available now."
        ))
        self.assertIsNone(lead)

    def test_golden_visa_interest(self):
        lead = ar.classify("golden_visa", self.item(
            "I am looking for a Golden Visa. My investment budget is €350,000. Which country should I consider?"
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["classification"], "HOT")

    def test_golden_visa_question_without_budget_is_warm(self):
        lead = ar.classify("golden_visa", self.item(
            "We are considering residency by investment. Which Golden Visa program would fit a family?"
        ))
        self.assertIsNotNone(lead)
        self.assertEqual(lead["classification"], "WARM")

    def test_rejects_golden_visa_marketing_ad(self):
        lead = ar.classify("golden_visa", self.item(
            "Golden Visa available now. Contact us on WhatsApp. Our real estate agency offers properties and consultation."
        ))
        self.assertIsNone(lead)


if __name__ == "__main__":
    unittest.main()
