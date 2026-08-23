from datetime import datetime, timezone

import north_cyprus_catcher as base
import north_cyprus_focus as nf
import north_cyprus_spam_guard
import telegram_global_search as tgs

from north_cyprus_open_web import OPEN_WEB_ALLOWED_DOMAINS, collect_open_web
from telegram_channel_comments import collect_channel_comments
from telegram_member_deep_search import collect_member_deep_search

for _domain in OPEN_WEB_ALLOWED_DOMAINS:
    nf.ALLOWED_USER_DOMAINS.add(_domain)

CORE_GLOBAL_QUERIES = [
    "North Cyprus property", "Kuzey Kıbrıs daire", "İskele daire", "Long Beach İskele",
    "Северный Кипр квартира", "Северный Кипр недвижимость",
]

EXTRA_GLOBAL_QUERIES = [
    "North Cyprus apartment", "Northern Cyprus property", "North Cyprus looking for apartment",
    "North Cyprus want to buy", "North Cyprus resale", "North Cyprus price", "Long Beach 1+1",
    "Long Beach 2+1", "Long Beach resale", "İskele arıyorum", "İskele sahibinden", "İskele fiyat",
    "Girne daire", "Girne arıyorum", "Girne sahibinden", "Esentepe villa", "Esentepe arıyorum",
    "Kuzey Kıbrıs ev", "Kuzey Kıbrıs arıyorum", "Kuzey Kıbrıs satın almak", "Kuzey Kıbrıs sahibinden",
    "Kuzey Kıbrıs peşinat", "Kuzey Kıbrıs taksit", "Северный Кипр ищу", "Северный Кипр хочу купить",
    "Северный Кипр нужна квартира", "Северный Кипр цена", "Северный Кипр рассрочка",
    "Северный Кипр вторичка", "Северный Кипр от собственника", "Caesar Resort", "Caesar Resort resale",
    "Grand Sapphire", "Grand Sapphire resale", "Isatis", "Isatis resale", "Elysium", "Elysium 2", "Fiora",
    "Isatis Orchard", "Royal Sun", "Royal Sun resale", "Riverside Life", "K'Saba İskele",
    "Nordzypern Wohnung kaufen", "Nordzypern Immobilie kaufen", "Chypre du Nord acheter appartement",
    "Noord Cyprus woning kopen", "Cypr Północny szukam mieszkania", "Cypr Północny chcę kupić",
    "Північний Кіпр шукаю квартиру", "Північний Кіпр хочу купити", "شمال قبرص أبحث عن شقة",
    "شمال قبرص أريد شراء عقار", "צפון קפריסין דירה לקנות",
]

PUBLIC_GROUP_DISCOVERY_QUERIES = [
    "North Cyprus", "Northern Cyprus", "North Cyprus property", "North Cyprus expats", "Kuzey Kıbrıs",
    "Kuzey Kıbrıs emlak", "Kuzey Kıbrıs gayrimenkul", "Северный Кипр", "Северный Кипр недвижимость",
    "Северный Кипр чат", "İskele", "Long Beach Cyprus", "Girne", "Esentepe", "Famagusta Cyprus",
    "Caesar Resort Cyprus", "Grand Sapphire Cyprus", "Isatis Cyprus",
]


def _unique(values):
    out = []
    seen = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _rotating_queries():
    all_queries = _unique(list(tgs.GLOBAL_QUERIES) + EXTRA_GLOBAL_QUERIES)
    core_keys = {c.casefold() for c in CORE_GLOBAL_QUERIES}
    rotating = [x for x in all_queries if x.casefold() not in core_keys]
    rotate_count = 10
    if not rotating:
        return CORE_GLOBAL_QUERIES[:]
    now = datetime.now(timezone.utc)
    slot = now.timetuple().tm_yday * 8 + now.hour // 3
    start = (slot * rotate_count) % len(rotating)
    selected = [rotating[(start + i) % len(rotating)] for i in range(min(rotate_count, len(rotating)))]
    return _unique(CORE_GLOBAL_QUERIES + selected)


tgs.GLOBAL_QUERIES = _rotating_queries()
tgs.PUBLIC_GROUP_DISCOVERY_QUERIES = _unique(list(tgs.PUBLIC_GROUP_DISCOVERY_QUERIES) + PUBLIC_GROUP_DISCOVERY_QUERIES)

_original_collect_global = base.collect_global_telegram


def expanded_collect_global():
    buckets = []
    normal_global = _original_collect_global()
    buckets.append(("telegram_global_public", normal_global))
    deep_member = collect_member_deep_search()
    buckets.append(("telegram_joined_deep", deep_member))
    channel_comments = collect_channel_comments()
    buckets.append(("telegram_channel_comments", channel_comments))
    open_web = collect_open_web()
    buckets.append(("open_web_reddit_bing_dynamic", open_web))

    unique = {}
    counts = {}
    for name, items in buckets:
        counts[name] = len(items)
        for item in items:
            key = item.get("url") or base.main.dedupe_key(item)
            unique[key] = item
    print("NC_EXPANDED_SOURCE_COUNTS", counts, "unique", len(unique))
    return list(unique.values())


base.collect_global_telegram = expanded_collect_global

if __name__ == "__main__":
    base.run()
