from datetime import datetime, timezone, timedelta

from runtime_quality_guard import (
    canonical_world_url,
    install_nc_intent_guard,
    install_world_shard_guard,
    world_target_rejection,
)

install_nc_intent_guard()

from north_cyprus_intent_classifier import classify_intent


def _nc_item(text, chat="СЕВЕРНЫЙ КИПР | ФОРУМ"):
    return {
        "text": text,
        "author": "@test",
        "telegram_chat": chat,
        "url": "https://t.me/example/1",
    }


def test_nc_cases():
    cases = [
        (
            "recovery_supply_caesar",
            "Долгосрочная аренда 1+1, Искеле, Caesar Resort 2, 1 этаж (не граунд) 550€ месяц, айдат включен, возвратный депозит, коммунальные расходы оплачиваются отдельно.",
            "OWNER",
            [],
        ),
        (
            "recovery_supply_karsiyaka",
            "АРЕНДА 📍Каршияка 🏡 3+1 1200£/мес, долгосрочная аренда",
            "OWNER",
            [],
        ),
        (
            "recovery_supply_short_and_long",
            "Аренда 2+1 Цезарь Резорт 5 Граунд с личным выходом на бассейн 45€ посуточно свободна с 20.09 - 26.09 доступна на долгосрок после 08.10",
            "OWNER",
            [],
        ),
        (
            "real_long_term_tenant",
            "Здравствуйте срочно ищу комнату с 14 сентября на долгий срок в Гирне центр или ближе к Финалу университет. Или сниму с кем нибудь квартиру.",
            "TENANT",
            ["LONG_TERM_TENANT"],
        ),
        (
            "real_shared_tenant",
            "Здравствуйте, ищу соседа, чтобы снять вместе квартиру на долгий срок, ближе к университету Финал.",
            "TENANT",
            ["SHARED_RENTAL"],
        ),
        (
            "one_day_is_short_term_tenant",
            "Ищу дом с бассейном на 1 день Искеле Лонг бич",
            "TENANT",
            ["SHORT_TERM_TENANT"],
        ),
        (
            "after_sale_not_new_buyer",
            "15.07.2026 получили разрешение на покупку квартиры. Пошли в TAPU, там сказали: титулы ещё не готовы - ждите.",
            "UNKNOWN",
            [],
        ),
        (
            "explicit_title_buyer_stays_buyer",
            "Куплю квартиру 2+1/2+2 с титулом Цезарь Резорт",
            "BUYER",
            [],
        ),
    ]

    failures = []
    for name, text, expected, subtypes in cases:
        result = classify_intent(_nc_item(text))
        if result.get("intent_class") != expected:
            failures.append((name, expected, result))
        for subtype in subtypes:
            if subtype not in (result.get("intent_subtypes") or []):
                failures.append((name, "missing subtype " + subtype, result))
    if failures:
        raise AssertionError(failures)


def test_world_cases():
    assert canonical_world_url(
        "https://www.expat.com/en/forum/europe/italy/1115893-planning.html#6136844"
    ) == "https://www.expat.com/en/forum/europe/italy/1115893-planning.html"

    assert world_target_rejection({
        "source_bucket": "shard_north_cyprus_cis_direct",
        "title": "Chinese speakers in Bursa",
        "text": "I am looking to buy an apartment in Bursa and would like advice.",
        "author": "user",
    }) == "north_cyprus_cis_off_target"

    assert world_target_rejection({
        "source_bucket": "shard_north_cyprus_cis_direct",
        "title": "Buying in North Cyprus",
        "text": "I am looking to buy an apartment in North Cyprus near Iskele.",
        "author": "user",
    }) == ""

    assert world_target_rejection({
        "source_bucket": "shard_golden_south_direct",
        "title": "Planning My First Long Stay in Italy – Looking for Advice",
        "text": "I am planning a long stay in Italy and would like advice about where to live and accommodation.",
        "author": "user",
    }) == "golden_south_no_property_purchase"

    assert world_target_rejection({
        "source_bucket": "shard_golden_south_direct",
        "title": "Buying a home in Italy",
        "text": "We are planning to buy an apartment in Italy for our relocation.",
        "author": "user",
    }) == ""

    assert world_target_rejection({
        "source_bucket": "shard_golden_south_direct",
        "title": "Last post 17 hours ago by La Relocation Group",
        "text": "We help clients purchase property in Italy.",
        "author": "La Relocation Group",
    }) == "golden_south_commercial_provider"


def test_world_install_integration():
    import main

    install_world_shard_guard()
    now = datetime.now(timezone.utc)
    item = {
        "source_bucket": "shard_north_cyprus_cis_direct",
        "url": "https://www.expat.com/en/forum/middle-east/turkey/bursa/example.html",
        "title": "Chinese speakers in Bursa",
        "text": "I want to buy property in Bursa and need advice from forum members.",
        "published": now.isoformat(),
        "author": "forum user",
    }
    keep, reason = main.keep_candidate(item, now - timedelta(hours=24))
    if keep or reason != "north_cyprus_cis_off_target":
        raise AssertionError((keep, reason))


if __name__ == "__main__":
    test_nc_cases()
    test_world_cases()
    test_world_install_integration()
    print("RUNTIME_QUALITY_GUARD_OK")
