import unittest

import youtube_radar_guard as guard


class YouTubeRadarGuardTests(unittest.TestCase):
    def item(self, text, reply_context=""):
        return {
            "comment_id": "test-comment",
            "video_id": "test-video",
            "video_title": "KIBRIS, İSKELE'DE LÜKS YAŞAM KAÇ PARA? 2026",
            "channel_title": "North Cyprus Property",
            "text": text,
            "reply_context": reply_context,
            "author": "viewer",
            "published": "2026-09-01T12:00:00+00:00",
            "url": "https://www.youtube.com/watch?v=test-video&lc=test-comment",
            "source": "YouTube Comment",
        }

    def test_rejects_off_topic_ne_kadar_phrase(self):
        lead = guard.classify_comment_guarded(self.item(
            "Şu an izliyoruz sizi Nihal hanımı düşünün koltuk altı kıllı düşünün ne kadar çirkin olurdu, anlatabildim mi"
        ))
        self.assertIsNone(lead)

    def test_accepts_real_price_question(self):
        lead = guard.classify_comment_guarded(self.item("2+1 daire fiyatı ne kadar?"))
        self.assertIsNotNone(lead)
        self.assertIn(lead["classification"], {"WARM", "HOT"})

    def test_rejects_bare_fiyat_comment(self):
        self.assertIsNone(guard.classify_comment_guarded(self.item("Fiyat")))

    def test_rejects_bare_price_question(self):
        self.assertIsNone(guard.classify_comment_guarded(self.item("Price?")))

    def test_rejects_terse_ne_kadar_without_property_reference(self):
        self.assertIsNone(guard.classify_comment_guarded(self.item("Ne kadar?")))

    def test_rejects_generic_availability_phrase(self):
        lead = guard.classify_comment_guarded(self.item("Vaktiniz var mı, bir şey soracağım"))
        self.assertIsNone(lead)

    def test_accepts_property_availability(self):
        lead = guard.classify_comment_guarded(self.item("2+1 satılık daire var mı?"))
        self.assertIsNotNone(lead)

    def test_rejects_existing_caesar_owner_residency_question(self):
        lead = guard.classify_comment_guarded(self.item(
            "Скажите пожалуйста, подойдет ли квартира студия (пока еще в рассрочке, в комплексе Цезарь) для оформления ВНЖ на семью из 4 человек?"
        ))
        self.assertIsNone(lead)

    def test_rejects_followup_title_question_when_parent_shows_existing_purchase(self):
        parent = (
            "Скажите пожалуйста, подойдет ли квартира студия (пока еще в рассрочке, "
            "в комплексе Цезарь) для оформления ВНЖ на семью из 4 человек?"
        )
        followup = (
            "Получается квадратура не важна? Если семья из 4 человек и студия подойдет? "
            "Какие ваши прогнозы по поводу титулов? (Цезарь 8)"
        )
        lead = guard.classify_comment_guarded(self.item(followup, reply_context=parent))
        self.assertIsNone(lead)

    def test_does_not_block_fresh_buyer_only_because_of_residency_goal(self):
        lead = guard.classify_comment_guarded(self.item(
            "Хочу купить студию в Caesar Resort. Какая цена и подойдет ли она для ВНЖ?"
        ))
        self.assertIsNotNone(lead)


if __name__ == "__main__":
    unittest.main()
