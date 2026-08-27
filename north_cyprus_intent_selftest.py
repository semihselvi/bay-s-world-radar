from north_cyprus_intent_classifier import classify_intent
from north_cyprus_publisher_classifier import annotate_publisher_types
from north_cyprus_semantic_dedupe import semantic_dedupe_items, consolidate_buyer_leads


# Human-reviewed Catcher false positives and real leads are kept here as regressions.
def _item(text, author="@test", uid="", chat="СЕВЕРНЫЙ КИПР | ФОРУМ", **extra):
    row = {"text": text, "author": author, "telegram_user_id": uid, "telegram_chat": chat, "url": extra.pop("url", "https://example.test/x"), "published": extra.pop("published", "2026-08-26T10:00:00+00:00")}
    row.update(extra)
    return row


def main():
    cases = [
        ("buyer", _item("Хочу купить квартиру 2+1 в Фамагусте, важно близко к университету. От собственника."), "BUYER", []),
        ("long_tenant", _item("Ищу 2+1 в Grand Sapphire Resort на долгий срок, помесячно, от собственника."), "TENANT", ["LONG_TERM_TENANT"]),
        ("lea_longosrok", _item("Ищу квартиру 1+1 от собственника, на долгосрок. Караогланоглу-алсанджак Срочно", author="@Lea_Kasim"), "TENANT", ["LONG_TERM_TENANT"]),
        ("short_multi", _item("Ищу в Caesar Resort 3+1 или несколько квартир рядом, с 3 по 10 сентября."), "TENANT", ["SHORT_TERM_TENANT", "MULTI_UNIT_RENTAL"]),
        ("shared", _item("Ищу человека, чтобы вместе снять 2+1 в центре Гирне."), "TENANT", ["SHARED_RENTAL"]),
        ("boris_long_ground", _item("Ищу квартиру 2+1 или 3+1 на долгосрок в Гирне, желательно на первом этаже.", author="@Boris2906"), "TENANT", ["LONG_TERM_TENANT"]),
        ("owner", _item("Сдам свою квартиру 2+1 в Искеле, от собственника."), "OWNER", []),
        ("owner_long_term", _item("Сдам квартиру 1+1 в Искеле на долгосрок, от собственника."), "OWNER", []),
        ("usdt", _item("Хочу купить USDT прямо сейчас. Ищу продавца USDT."), "FINANCIAL", []),
        ("bank", _item("Срочно ищу человека с европейским счетом. Переведу всю сумму сразу."), "FINANCIAL", []),
        ("cleaning", _item("Ищу уборку квартиры в Кирении, нужен клининг."), "SERVICE", []),
        ("delivery", _item("Доставка TEMU, SHEIN, ZARA, AMAZON до вашего города, до 30 кг."), "SERVICE", []),
        ("pet", _item("Ищут дом два мальчика. Были на передержке, ветеринар, обработаны от блох."), "SPAM", []),
        ("ambiguous", _item("Ищу квартиру 2+1 в Фамагусте."), "UNKNOWN", []),
        ("owner_direct_ambiguous", _item("Ищу квартиру 2+1 от собственника в Фамагусте."), "UNKNOWN", []),
        ("owner_direct_buy", _item("Хочу купить квартиру 2+1 от собственника в Фамагусте."), "BUYER", []),
        ("matan_ready_title", _item("Хочу купить квартиру с готовым титулом в Искеле. Caesar Resort тоже рассматриваю.", author="@MatanHappy"), "BUYER", []),
        ("reply_sale", _item("цена?", reply_context="Продается квартира 2+1 в Искеле, цена £100000"), "BUYER", []),
        ("reply_rent", _item("price?", chat="North Cyprus Chat", reply_context="For rent apartment 2+1 in North Cyprus, monthly"), "TENANT", []),
    ]
    failed = []
    results = {}
    for name, row, expected, subtypes in cases:
        result = classify_intent(row)
        results[name] = result
        if result["intent_class"] != expected:
            failed.append((name, expected, result["intent_class"], result))
        for subtype in subtypes:
            if subtype not in result.get("intent_subtypes", []):
                failed.append((name, "missing_subtype", subtype, result))

    lea = results["lea_longosrok"]
    lea_req = lea.get("requirements") or {}
    if lea_req.get("property_type") != "1+1":
        failed.append(("lea_property_type", "1+1", lea_req.get("property_type"), lea))
    for region in ("Karaoğlanoğlu", "Alsancak"):
        if region not in lea_req.get("regions", []):
            failed.append(("lea_region", region, lea_req.get("regions"), lea))
    for pref in ("LONG_TERM", "URGENT", "OWNER_DIRECT", "KARAOGLANOGLU_ALSANCAK"):
        if pref not in lea_req.get("preferences", []):
            failed.append(("lea_preference", pref, lea_req.get("preferences"), lea))

    boris = results["boris_long_ground"]
    boris_req = boris.get("requirements") or {}
    if boris_req.get("property_type") != "2+1_OR_3+1":
        failed.append(("boris_property_type", "2+1_OR_3+1", boris_req.get("property_type"), boris))
    if "GROUND_FLOOR" not in boris_req.get("preferences", []):
        failed.append(("boris_ground_floor", "GROUND_FLOOR", boris_req.get("preferences"), boris))

    matan = results["matan_ready_title"]
    matan_req = matan.get("requirements") or {}
    for pref in ("READY_TITLE", "CAESAR_RESORT_ACCEPTED"):
        if pref not in matan_req.get("preferences", []):
            failed.append(("matan_preference", pref, matan_req.get("preferences"), matan))
    if "İskele" not in matan_req.get("regions", []):
        failed.append(("matan_region", "İskele", matan_req.get("regions"), matan))

    publishers = [
        _item("Сдам свою квартиру 2+1 в Искеле, собственник", author="@owner", uid="100", url="https://e/o1"),
        _item("Продается 1+1 в Искеле, цена £70000", author="@inventory", uid="200", url="https://e/a1"),
        _item("Продается 2+1 в Гирне, цена £120000", author="@inventory", uid="200", url="https://e/a2"),
    ]
    annotate_publisher_types(publishers)
    if publishers[0].get("publisher_type") != "OWNER":
        failed.append(("publisher_owner", "OWNER", publishers[0].get("publisher_type"), publishers[0]))
    if publishers[1].get("publisher_type") != "AGENT" or publishers[2].get("publisher_type") != "AGENT":
        failed.append(("publisher_agent", "AGENT", [x.get("publisher_type") for x in publishers[1:]], publishers[1:]))

    repeated = [
        _item("Water filter service call +90 555 111 22 33 WhatsApp now, available today " * 2, author="@farshaddz86", url="https://e/s1"),
        _item("Water filter service call +90 555 111 22 33 WhatsApp now, available today!! " * 2, author="@farshad_dz", url="https://e/s2"),
    ]
    if len(semantic_dedupe_items(repeated)) != 1:
        failed.append(("semantic_campaign", 1, len(semantic_dedupe_items(repeated)), {}))

    buyer_rows = [
        {**_item("Хочу купить квартиру 2+1 в Искеле", author="@buyer", uid="300", url="https://e/b1"), "classification": "WARM", "intent_class": "BUYER", "intent_confidence": 80, "intent_score": 80},
        {**_item("Бюджет £100000, только от собственника", author="@buyer", uid="300", url="https://e/b2", published="2026-08-26T11:00:00+00:00"), "classification": "HOT", "intent_class": "BUYER", "intent_confidence": 90, "intent_score": 90},
    ]
    consolidated = consolidate_buyer_leads(buyer_rows)
    if len(consolidated) != 1 or consolidated[0].get("evidence_count", 0) < 2:
        failed.append(("one_person_one_candidate", 1, len(consolidated), consolidated))

    if failed:
        raise SystemExit("NC_INTENT_SELFTEST_FAILED " + repr(failed))
    print(f"NC_INTENT_SELFTEST_OK cases={len(cases)}")


if __name__ == "__main__":
    main()
