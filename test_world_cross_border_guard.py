import unittest

import world_cross_border_guard as guard


class WestEuropeCrossBorderGuardTests(unittest.TestCase):
    def test_rejects_domestic_st_helens_house_purchase(self):
        item = {
            "title": "Surveyors declined Level 3 – Unfinished flip red flags (St Helens)",
            "text": "We are buying a house in St Helens and two surveyors declined a Level 3 survey. We are worried about the unfinished flip.",
        }
        self.assertFalse(guard.cross_border_signal(item))

    def test_rejects_domestic_reservations_about_house_purchase(self):
        item = {
            "title": "Reservations about house purchase",
            "text": (
                "My daughter is in the process of buying a 3 bed terrace with a JBSP mortgage. "
                "The house is close to the hospital where she works. I worry about resale in ten years."
            ),
        }
        self.assertFalse(guard.cross_border_signal(item))

    def test_accepts_uk_buyer_researching_north_cyprus(self):
        item = {
            "title": "Buying a second home in North Cyprus",
            "text": "I live in the UK and am considering buying a 2 bed apartment in North Cyprus. Which title deed should I look for?",
        }
        self.assertTrue(guard.cross_border_signal(item))

    def test_accepts_property_abroad_without_named_destination(self):
        item = {
            "title": "Buying property abroad",
            "text": "We want to buy abroad for retirement and are comparing mortgage and legal costs.",
        }
        self.assertTrue(guard.cross_border_signal(item))

    def test_rejects_destination_mentioned_only_in_unrelated_footer(self):
        item = {
            "title": "Buying a house in Manchester",
            "text": "I am buying locally in Manchester. Forum footer links: Spain Portugal Cyprus travel guides.",
        }
        self.assertFalse(guard.cross_border_signal(item))


if __name__ == "__main__":
    unittest.main()
