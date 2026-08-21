import hashlib
from urllib.parse import urlparse

import main
import world_engine

COLLECTION = "bay_s_dynamic_sources"

QUERY = (
    "past 7 days active public communities where real people discuss moving to or buying property in "
    "North Cyprus, Northern Cyprus or TRNC; find public Telegram groups/channels, expat forums, Reddit "
    "communities and public Facebook groups with current user discussions; prioritize Iskele, Long Beach, "
    "Kyrenia, Girne, Esentepe, Famagusta, Lapta, Tatlisu and Bafra; exclude estate agency pages, developers, "
    "property listing portals, news sites and generic guides"
)

DOMAINS = [
    "t.me",
    "reddit.com",
    "expat.com",
    "expatforum.com",
    "kibkomnorthcyprusforum.com",
    "britishexpats.com",
    "facebook.com",
    "tripadvisor.com",
    "turkishliving.com",
    "telegid.me",
    "tlgrm.ru",
]


def _telegram_username(url):
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().replace("www.", "")
        if host not in ("t.me", "telegram.me"):
            return ""
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            return ""
        if parts[0] == "s" and len(parts) > 1:
            parts = parts[1:]
        username = parts[0].lstrip("@").strip()
        if not username or username.startswith("+") or username.lower() in ("joinchat", "share"):
            return ""
        return username
    except Exception:
        return ""


def _doc_id(kind, value):
    return hashlib.sha1(f"{kind}|{value.lower()}".encode("utf-8")).hexdigest()


def run():
    db = main.firestore_client()
    if not db:
        print("SOURCE_SCOUT_DISABLED missing Firestore")
        return

    results = world_engine.exa_search(QUERY, DOMAINS)
    now = main.now_utc().isoformat()
    new_count = 0
    telegram_count = 0
    candidate_count = 0

    for item in results:
        url = str(item.get("url", "")).strip()
        if not url:
            continue

        username = _telegram_username(url)
        if username:
            kind = "telegram_public"
            key = _doc_id(kind, username)
            ref = db.collection(COLLECTION).document(key)
            existed = ref.get().exists
            ref.set({
                "type": kind,
                "market": "north_cyprus",
                "username": username,
                "url": f"https://t.me/{username}",
                "title": item.get("title", ""),
                "status": "active",
                "discovered_by": "weekly_exa_scout",
                "last_seen": now,
            }, merge=True)
            telegram_count += 1
            if not existed:
                new_count += 1
            continue

        domain = urlparse(url).netloc.lower().replace("www.", "")
        if not domain:
            continue
        kind = "community_candidate"
        key = _doc_id(kind, url)
        ref = db.collection(COLLECTION).document(key)
        existed = ref.get().exists
        ref.set({
            "type": kind,
            "market": "north_cyprus",
            "domain": domain,
            "url": url,
            "title": item.get("title", ""),
            "status": "candidate",
            "discovered_by": "weekly_exa_scout",
            "last_seen": now,
        }, merge=True)
        candidate_count += 1
        if not existed:
            new_count += 1

    print(
        f"SOURCE_SCOUT_COMPLETE results={len(results)} telegram={telegram_count} "
        f"community_candidates={candidate_count} new={new_count}"
    )

    if new_count:
        main.notify_telegram(
            f"🛰 BAY-S SOURCE SCOUT\nNorth Cyprus için {new_count} yeni kaynak adayı bulundu.\n"
            f"Public Telegram: {telegram_count}\nDiğer community adayları: {candidate_count}\n"
            "Public Telegram kaynakları sonraki North Cyprus Hunter taramalarında otomatik havuza alınır."
        )


if __name__ == "__main__":
    run()
