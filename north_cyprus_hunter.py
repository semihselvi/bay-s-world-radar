import hashlib
import os
import re

import main
import shard_runner
import source_crawler_v2
import north_cyprus_focus

DYNAMIC_SOURCE_COLLECTION = "bay_s_dynamic_sources"


def _load_dynamic_channels(limit=40):
    db = main.firestore_client()
    if not db:
        return set()
    channels = set()
    try:
        docs = (
            db.collection(DYNAMIC_SOURCE_COLLECTION)
            .where("market", "==", "north_cyprus")
            .where("type", "==", "telegram_public")
            .where("status", "==", "active")
            .limit(limit)
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            username = str(data.get("username", "")).strip().lstrip("@")
            if username:
                channels.add(username)
    except Exception as exc:
        print("DYNAMIC_SOURCE_LOAD_FALLBACK", exc)
        try:
            for doc in db.collection(DYNAMIC_SOURCE_COLLECTION).limit(100).stream():
                data = doc.to_dict() or {}
                if data.get("market") != "north_cyprus" or data.get("type") != "telegram_public" or data.get("status") != "active":
                    continue
                username = str(data.get("username", "")).strip().lstrip("@")
                if username:
                    channels.add(username)
                if len(channels) >= limit:
                    break
        except Exception as inner:
            print("DYNAMIC_SOURCE_LOAD_ERROR", inner)
    print(f"DYNAMIC_TELEGRAM_LOADED count={len(channels)}")
    return channels


def _persist_channels(channels, discovered_by):
    if not channels:
        return
    db = main.firestore_client()
    if not db:
        return
    now = main.now_utc().isoformat()
    batch = db.batch()
    count = 0
    for username in sorted(set(channels)):
        username = str(username).strip().lstrip("@")
        if not username:
            continue
        doc_id = hashlib.sha1(username.lower().encode("utf-8")).hexdigest()
        batch.set(
            db.collection(DYNAMIC_SOURCE_COLLECTION).document(doc_id),
            {
                "type": "telegram_public",
                "market": "north_cyprus",
                "username": username,
                "url": f"https://t.me/{username}",
                "status": "active",
                "discovered_by": discovered_by,
                "last_seen": now,
            },
            merge=True,
        )
        count += 1
    if count:
        batch.commit()
        print(f"DYNAMIC_TELEGRAM_SAVED count={count} by={discovered_by}")


_dynamic_channels = _load_dynamic_channels()

# The dedicated hunter can use community domains that the general World Radar
# intentionally keeps out of its stricter production allow-list.
north_cyprus_focus.ALLOWED_USER_DOMAINS.add("forum.awd.ru")

# High-recall scanning also sees service advertisements in mixed Cyprus groups.
# Keep those out without narrowing genuine property-buyer phrases. A direct
# transfer-service phrase is enough; otherwise require several commercial signals.
_original_promotional_service_ad = north_cyprus_focus._promotional_service_ad
TRANSFER_SERVICE_PATTERNS = [
    r"услуги трансфера",
    r"трансфер (?:в|до|из) аэропорт",
    r"трансфер до места проживания",
    r"airport transfer",
    r"transfer service",
    r"licensed (?:car|vehicle)",
    r"лицензированн(?:ых|ые) автомобил",
    r"надежный водитель",
    r"встреч[аи] в аэропорте",
    r"детск(?:ого|ое) кресл",
    r"mercedes vito",
    r"mercedes v[- ]?class",
    r"mercedes e[- ]?class",
]


def _promotional_or_transfer_service_ad(text):
    if _original_promotional_service_ad(text):
        return True
    direct = re.search(
        r"услуги трансфера|airport transfer|transfer service|трансфер до места проживания",
        text,
        re.I,
    )
    if direct:
        return True
    hits = sum(1 for pattern in TRANSFER_SERVICE_PATTERNS if re.search(pattern, text, re.I))
    commercial_hits = sum(
        1
        for pattern in (
            r"\+?90\s*5\d{2}",
            r"\bотличн(?:ые|ая) альтернативы по цене\b",
            r"\b1\s*до\s*7 человек\b",
            r"\bводитель\b",
            r"\bаэропорт\b",
        )
        if re.search(pattern, text, re.I)
    )
    return hits >= 2 or (hits >= 1 and commercial_hits >= 2)


north_cyprus_focus._promotional_service_ad = _promotional_or_transfer_service_ad

# Kibkom exposes current/latest topic links on its public index. Individual sales
# areas can require login, but scanning the public latest-topic surface is free.
if not any(x.get("name") == "Kibkom North Cyprus Latest" for x in shard_runner.DIRECT_INDEX_SOURCES):
    shard_runner.DIRECT_INDEX_SOURCES.append({
        "name": "Kibkom North Cyprus Latest",
        "url": "https://kibkomnorthcyprusforum.com/",
        "domain": "kibkomnorthcyprusforum.com",
        "market": "north_cyprus",
        "include_path": ["viewtopic.php"],
        "max_links": 30,
    })

# Forum AWD has a dedicated Северный Кипр forum and was still receiving posts in
# 2026. It is especially useful for Russian-speaking relocation/property intent.
if not any(x.get("name") == "AWD North Cyprus Forum" for x in shard_runner.DIRECT_INDEX_SOURCES):
    shard_runner.DIRECT_INDEX_SOURCES.append({
        "name": "AWD North Cyprus Forum",
        "url": "https://forum.awd.ru/viewforum.php?f=1683",
        "domain": "forum.awd.ru",
        "market": "north_cyprus",
        "include_path": ["viewtopic.php"],
        "max_links": 30,
    })

# Dedicated North Cyprus shard. High recall is intentional: a terse genuine buyer
# question is more valuable than a perfectly classified lead we discover too late.
shard_runner.SHARDS["north_cyprus_hunter"] = {
    "index_names": {
        "Expat.com North Cyprus",
        "Kibkom North Cyprus Latest",
        "AWD North Cyprus Forum",
    },
    "topic_names": set(),
    "telegram": {
        "cyprusy",
        "searchnorthcyprus",
        "snchubTalkroom",
        "meetinnorthcyprus",
        "northcyprus29",
    } | _dynamic_channels,
    "catalogs": {"TeleGid Cyprus", "SNC Community Hub"},
    "member": True,
    "exa_calls": 1,
    "exa_query": (
        "past 7 days genuine person asking about buying, finding, pricing or choosing a home, apartment, studio, "
        "villa, land or investment property in North Cyprus, Northern Cyprus or TRNC; include Iskele, Long Beach, "
        "Kyrenia, Girne, Esentepe, Famagusta, Gazimagusa, Lapta, Tatlisu, Bahceli, Bafra, Alsancak, Karsiyaka, "
        "Catalkoy, Bellapais and Yenibogazici. Explicitly include buyer discussions mentioning Isatis, Isatis Construction, "
        "Elysium, Elysium 2, Isatis Hillside, Isatis Infinity, Fiora or Isatis Orchard, including resale, owner sale, "
        "availability, price, studio, 1+1, 2+1, villa, payment plan, deposit and title deed questions. Include short buyer "
        "questions such as 1+1, 2+1, 3+1, studio wanted, what can I get for a budget, how much is an apartment, which "
        "area is best, Iskele or Girne, which project or developer is reliable, title deed/kocan, lawyer, mortgage, deposit, "
        "down payment, installment/payment plan, viewing, offer, off-plan versus resale, ready property, relocation, "
        "retirement or second home. Search English, Turkish, Russian, German, French, Dutch and Persian wording including "
        "ev ariyorum, daire ariyorum, var mi, ne kadar, hangi bolge, butce, pesinat, taksit, хочу купить, ищу квартиру, "
        "что можно купить, сколько стоит, какой район лучше, рассрочка. Prioritize recent user posts/comments in "
        "r/NorthCyprus, r/cyprus, r/expats, r/Investors, r/realestateinvesting, expat forums, Facebook groups and Telegram "
        "communities. Exclude agents, brokers, developers, listings, advertising, rental-only requests, guides and news."
    ),
    "exa_domains": [
        "reddit.com",
        "expat.com",
        "expatforum.com",
        "kibkomnorthcyprusforum.com",
        "forum.awd.ru",
        "britishexpats.com",
        "tripadvisor.com",
        "facebook.com",
        "t.me",
        "turkishliving.com",
    ],
    "reddit_focus": ["NorthCyprus", "cyprus", "expats", "ExpatFIRE", "AmerExit"],
}

# Persist channels found by live catalogs so tomorrow's scan does not depend on
# discovering the same link again.
_original_discover = source_crawler_v2.discover_public_telegram_channels


def discover_and_persist(catalog_names=None):
    channels = _original_discover(catalog_names)
    _persist_channels(channels, "catalog")
    return channels


source_crawler_v2.discover_public_telegram_channels = discover_and_persist

# Override only for this process. Other World Radar shards keep their current filters.
main.keep_candidate = north_cyprus_focus.keep_candidate
main.buyer_scores = north_cyprus_focus.buyer_scores

_original_market_for = main.market_for
_original_notify = main.notify_telegram
_original_mark_notified = shard_runner.mark_notified
_CAPTURED_NEW_LEADS = []


def north_cyprus_market_for(text, bucket_name="", url="", title=""):
    market = _original_market_for(text, bucket_name, url, title)
    return "north_cyprus" if market == "unknown" else market


def mark_and_capture(db, lead_key, lead):
    _original_mark_notified(db, lead_key, lead)
    _CAPTURED_NEW_LEADS.append(lead)


def hunter_notify(default_message):
    if not _CAPTURED_NEW_LEADS:
        _original_notify(default_message)
        return

    lines = [f"🔥 BAY-S NORTH CYPRUS HUNTER | {len(_CAPTURED_NEW_LEADS)} YENİ LEAD"]
    for lead in _CAPTURED_NEW_LEADS[:8]:
        author = lead.get("author", "") or "kullanıcı"
        place = lead.get("telegram_chat", "") or lead.get("title", "") or lead.get("source", "")
        excerpt = " ".join(str(lead.get("text", "")).split())[:260]
        lines.append(
            f"\n{lead.get('classification','WARM')} | {author} | {place[:80]}\n"
            f"I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)} F{lead.get('market_fit_score',0)}\n"
            f"{excerpt}\n{lead.get('url','')}"
        )
    _original_notify("\n".join(lines))


main.market_for = north_cyprus_market_for
main.notify_telegram = hunter_notify
shard_runner.mark_notified = mark_and_capture

if __name__ == "__main__":
    os.environ["WORLD_RADAR_SHARD"] = "north_cyprus_hunter"
    shard_runner.SHARD = "north_cyprus_hunter"
    shard_runner.run()
