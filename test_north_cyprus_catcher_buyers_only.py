import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import north_cyprus_catcher_buyers_only as guard


class BuyerOnlyCatcherTests(unittest.TestCase):
    def item(self, text):
        return {
            "source": "Telegram",
            "url": "https://t.me/russiansin_northcyprus/51528",
            "title": "",
            "text": text,
            "message": text,
            "author": "@AnastasyTok",
            "telegram_chat": "Русские на Северном Кипре",
        }

    def test_rejects_shared_rental_false_positive(self):
        item = self.item("Ищу студию в аренду или комнату на подселение с 1 сентября")
        intent = {
            "intent_class": "TENANT",
            "intent_subtypes": ["SHARED_RENTAL"],
            "intent_confidence": 77,
            "intent_reasons": ["rental demand"],
            "requirements": {"property_type": "STUDIO"},
        }
        with patch.object(guard.expanded, "classify_intent", return_value=intent), \
             patch.object(guard.expanded, "observe_source"), \
             patch.object(guard.expanded, "observe_query"):
            lead, reason = guard.buyer_only_classify(item, datetime.now(timezone.utc))
        self.assertIsNone(lead)
        self.assertEqual(reason, "buyer_only_reject_tenant")

    def test_rejects_explicit_rental_text_even_if_upstream_unknown(self):
        item = self.item("Looking to rent a studio in Iskele from September")
        intent = {
            "intent_class": "UNKNOWN",
            "intent_subtypes": [],
            "intent_confidence": 40,
            "intent_reasons": [],
            "requirements": {},
        }
        with patch.object(guard.expanded, "classify_intent", return_value=intent), \
             patch.object(guard.expanded, "observe_source"), \
             patch.object(guard.expanded, "observe_query"):
            lead, reason = guard.buyer_only_classify(item, datetime.now(timezone.utc))
        self.assertIsNone(lead)
        self.assertEqual(reason, "buyer_only_reject_rental_text")

    def test_purchase_word_prevents_rental_text_hard_reject(self):
        item = self.item("I currently rent in Iskele but I want to buy an apartment now")
        intent = {
            "intent_class": "BUYER",
            "intent_subtypes": [],
            "intent_confidence": 88,
            "intent_reasons": ["buy intent"],
            "requirements": {},
        }
        expected = {"intent_class": "BUYER", "classification": "WARM"}
        with patch.object(guard.expanded, "classify_intent", return_value=intent), \
             patch.object(guard.expanded, "observe_source"), \
             patch.object(guard.expanded, "observe_query"), \
             patch.object(guard, "_ORIGINAL_CLASSIFY", return_value=(expected, "accepted")):
            lead, reason = guard.buyer_only_classify(item, datetime.now(timezone.utc))
        self.assertIsNotNone(lead)
        self.assertEqual(reason, "accepted")


if __name__ == "__main__":
    unittest.main()
