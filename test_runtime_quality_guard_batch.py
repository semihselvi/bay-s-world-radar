from runtime_quality_guard_batch import install_nc_intent_guard, world_target_rejection

install_nc_intent_guard()

from north_cyprus_intent_classifier import classify_intent


def _item(text, chat="СЕВЕРНЫЙ КИПР | ФОРУМ"):
    return {
        "text": text,
        "author": "@test",
        "telegram_chat": chat,
        "url": "https://t.me/example/1",
    }


def test_nc_batch_cases():
    # Reviewed Buyer Catcher false positive: a joke/general discussion that only
    # says "before buying housing" is not personal purchase intent.
    result = classify_intent(_item(
        "Я думал генералы только на виллах 😌 А вот секретные склады боеприпасов - "
        "в жилых комплексах что ли? И как о них узнать перед покупкой жилья, они же секретные 😀",
        "СЕВЕРНЫЙ КИПР | ЧАТ",
    ))
    assert result["intent_class"] == "UNKNOWN", result
    assert "purchase_mention_without_personal_buyer_voice" in result["intent_reasons"], result

    # Strong explicit buyer must remain a buyer.
    result = classify_intent(_item(
        "Куплю от собственника 1+1 или 2+1 в Royal Sun или Royal Sun Elite. Этаж только граунд!",
        "СЕВЕРНЫЙ КИПР | НЕДВИЖИМОСТЬ",
    ))
    assert result["intent_class"] == "BUYER", result

    # Incidental apartment/home words in goods purchases must not create buyer intent.
    result = classify_intent(_item(
        "Здравствуйте! Может кто-нибудь ещё продаёт робот-пылесос моющий? Геолокация Искеле-Фамагуста. "
        "Интересует для большой квартиры. В пределах 150 евро",
        "СЕВЕРНЫЙ КИПР | БАРАХОЛКА",
    ))
    assert result["intent_class"] == "UNKNOWN", result

    result = classify_intent(_item(
        "Куплю школьную форму şht Ertugrul ilkokulu Lefkoşa для сына 6,7 лет, у кого завалялась дома",
        "СЕВЕРНЫЙ КИПР | БАРАХОЛКА",
    ))
    assert result["intent_class"] == "UNKNOWN", result

    # One month is routed as short-term; genuine long-term requests stay long-term.
    result = classify_intent(_item(
        "Сниму 1+1 на месяц в современном районе с 12 сентября. 500 — 700 € за месяц",
        "СЕВЕРНЫЙ КИПР | НЕДВИЖИМОСТЬ",
    ))
    assert result["intent_class"] == "TENANT", result
    assert "SHORT_TERM_TENANT" in result["intent_subtypes"], result

    result = classify_intent(_item(
        "Ищу 1+1 в Гирне на долгосрочную аренду, от собственника",
        "СЕВЕРНЫЙ КИПР | НЕДВИЖИМОСТЬ",
    ))
    assert result["intent_class"] == "TENANT", result
    assert "LONG_TERM_TENANT" in result["intent_subtypes"], result
    assert "SHORT_TERM_TENANT" not in result["intent_subtypes"], result


def test_golden_south_expat_cases():
    reviewed = {
        "source_bucket": "shard_golden_south_direct",
        "source": "Expat.com Italy",
        "url": "https://www.expat.com/en/forum/europe/italy/1115893-planning-my-first-long-stay-in-italy-looking-for-advice.html",
        "title": "Planning My First Long Stay in Italy – Looking for Advice",
        "author": "mlutsdblursyo",
        "text": (
            "Hello everyone! I'm new to the Expat.com community and am currently planning a long-term stay in Italy. "
            "I'd love advice about which city to choose, making friends and preparations. "
            "See also Real estate listings in Italy Buying a property in Italy Guide."
        ),
    }
    assert world_target_rejection(reviewed) == "golden_south_expat_no_personal_property_purchase"

    real_buyer = {
        "source_bucket": "shard_golden_south_direct",
        "source": "Expat.com Italy",
        "url": "https://www.expat.com/en/forum/europe/italy/123-looking-to-buy-house-in-sicily.html",
        "title": "Looking to buy house in Sicily",
        "author": "buyer",
        "text": "I am planning to buy a house in Sicily and would like advice about the purchase process.",
    }
    assert world_target_rejection(real_buyer) == ""


if __name__ == "__main__":
    test_nc_batch_cases()
    test_golden_south_expat_cases()
    print("RUNTIME_QUALITY_GUARD_BATCH_OK")
