import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests

import main

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
WATCHLIST_COLLECTION = "bay_s_youtube_watchlist"
NOTIFIED_COLLECTION = "bay_s_youtube_notified_leads"
SCAN_COLLECTION = "bay_s_youtube_scans"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "BAY-S-YouTube-Radar/1.0"})

# Search both generic North Cyprus terms and commercially important projects/areas.
DISCOVERY_QUERIES = [
    "North Cyprus property",
    "Northern Cyprus real estate",
    "North Cyprus apartment",
    "North Cyprus investment property",
    "Iskele Long Beach property",
    "Girne Kyrenia property",
    "Esentepe North Cyprus property",
    "Famagusta North Cyprus property",
    "Kuzey Kıbrıs emlak",
    "Kuzey Kıbrıs ev fiyatları",
    "İskele Long Beach daire",
    "Северный Кипр недвижимость",
    "Северный Кипр квартира",
    "Северный Кипр купить недвижимость",
    "Isatis Elysium North Cyprus",
    "Isatis Fiora North Cyprus",
    "Isatis Orchard North Cyprus",
    "Caesar Resort North Cyprus",
    "Grand Sapphire North Cyprus",
    "Royal Sun Long Beach",
    "Riverside Life North Cyprus",
    "K'Saba Iskele villa",
]

# A video only enters the watchlist when its title/description/channel context is
# clearly related to North Cyprus or a well-known local project/developer.
VIDEO_CONTEXT_PATTERNS = [
    r"north(?:ern)? cyprus", r"\btrnc\b", r"kuzey k[ıi]br[ıi]s", r"северн\w* кипр",
    r"\biskele\b", r"\bİskele\b", r"long beach", r"\bgirne\b", r"\bkyrenia\b",
    r"\besentepe\b", r"\bfamagusta\b", r"gazima[ğg]usa", r"yenibo[ğg]azi[çc]i",
    r"\btatl[ıi]su\b", r"\bbah[çc]eli\b", r"\bbafra\b", r"\blapta\b",
    r"\balsancak\b", r"kar[şs][ıi]yaka", r"\bcatalkoy\b", r"[çc]atalk[öo]y",
    r"\bbellapais\b", r"\bcaesar resort\b", r"grand sapphire", r"royal sun",
    r"riverside life", r"four seasons life", r"lagoon verde", r"\bhabitat\b",
    r"e[- ]?volve", r"\bisatis\b", r"\belysium\b", r"\bfiora\b", r"\borchard\b",
    r"isatis hillside", r"isatis infinity", r"northernland", r"d[öo]ve[çc]", r"noyanlar",
]

STRONG_BUYER_PATTERNS = [
    r"looking to buy", r"want(?:ing)? to buy", r"planning to buy", r"ready to buy",
    r"interested in buying", r"how (?:can|do) i buy", r"where can i buy", r"can foreigners buy",
    r"i want (?:a|an|to buy)", r"we want (?:a|an|to buy)", r"looking for (?:a|an)?\s*(?:studio|flat|apartment|villa|house|property)",
    r"cash buyer", r"make an offer", r"book a viewing", r"viewing.*property",
    r"sat[ıi]n almak istiyorum", r"ev almak istiyorum", r"daire almak istiyorum",
    r"villa almak istiyorum", r"ev ar[ıi]yorum", r"daire ar[ıi]yorum", r"yat[ıi]r[ıi]ml[ıi]k bak[ıi]yorum",
    r"хочу купить", r"хотим купить", r"ищу квартир", r"ищу апартамент", r"ищу дом",
    r"ищу вилл", r"купить недвижимост", r"готов\w* купить", r"хотел\w* бы купить",
    r"ich m[öo]chte .* kaufen", r"wohnung kaufen", r"haus kaufen", r"je veux acheter",
    r"acheter .* appartement", r"ik wil .* kopen", r"huis kopen", r"woning kopen",
    r"أريد شراء", r"أبحث عن شقة", r"شراء عقار",
]

REQUEST_PATTERNS = [
    r"\bprice\??$", r"how much", r"what(?:'s| is) the price", r"price please", r"price list",
    r"current price", r"starting price", r"payment plan", r"installments?", r"deposit",
    r"down payment", r"mortgage", r"title deed", r"deed type", r"resale", r"owner sale",
    r"available\??$", r"is .* available", r"any .* available", r"send (?:me )?(?:details|prices|price)",
    r"more details", r"can you send", r"which project", r"which area", r"best area",
    r"worth buying", r"good investment", r"investment return", r"rental yield",
    r"\b[1-5]\s*\+\s*[01]\b", r"\bstudio\b", r"\b\d\s*bed(?:room)?\b",
    r"fiyat\??$", r"fiyat[ıi] nedir", r"ne kadar", r"fiyat alabilir miyim", r"bilgi alabilir miyim",
    r"detay alabilir miyim", r"var m[ıi]", r"mevcut mu", r"pe[şs]inat", r"taksit", r"ko[çc]an",
    r"hangi proje", r"hangi b[öo]lge", r"mant[ıi]kl[ıi] m[ıi]", r"ne alabilirim",
    r"сколько стоит", r"какая цена", r"цена\??$", r"есть ли", r"какие варианты",
    r"что можно купить", r"рассроч", r"первоначальн\w* взнос", r"ипотек", r"титул",
    r"какой район", r"какой комплекс", r"стоит ли покупать",
]

CONCRETE_PATTERNS = [
    r"(?:£|€|\$|₺|₽)\s*\d[\d,. ]*(?:k|m)?", r"\b\d{2,3}\s*k\b",
    r"\bbudget\b", r"b[üu]t[çc]e", r"бюджет", r"deposit", r"payment plan",
    r"installment", r"mortgage", r"title deed", r"ko[çc]an", r"pe[şs]inat", r"taksit",
]

PROPERTY_PATTERNS = [
    r"property", r"apartment", r"flat", r"house", r"home", r"villa", r"studio", r"land", r"plot",
    r"daire", r"\bev\b", r"villa", r"arsa", r"gayrimenkul", r"emlak", r"[1-5]\s*\+\s*[01]",
    r"квартир", r"апартамент", r"дом", r"вилл", r"недвижимост", r"студи",
]

NOISE_PATTERNS = [
    r"nice video", r"great video", r"beautiful video", r"thanks for sharing", r"thank you for the video",
    r"awesome", r"amazing video", r"love cyprus", r"beautiful place", r"good job", r"great content",
    r"first comment", r"subscribe", r"subscribed", r"❤+$", r"🔥+$", r"👏+$",
]

SELLER_PROMO_PATTERNS = [
    r"contact us", r"contact me", r"dm (?:me|us) for", r"whatsapp (?:me|us)", r"call (?:me|us)",
    r"we offer", r"we have available", r"our project", r"our properties", r"for sale now",
    r"estate agent", r"real estate agent", r"realtor", r"broker", r"developer", r"commission",
    r"sat[ıi]l[ıi]k", r"portf[öo]y", r"emlak dan[ıi][şs]man", r"продается", r"агентств", r"риэлтор",
    r"застройщик", r"пишите в личку", r"обращайтесь", r"для консультации",
]

SERVICE_AD_PATTERNS = [
    r"scholarship", r"university admission", r"study in north cyprus", r"airport transfer",
    r"transfer service", r"услуги трансфера", r"visa service", r"residency service",
    r"car rental", r"rent a car", r"аренда авто",
]


def _api_key():
    return os.getenv("YOUTUBE_API_KEY", "").strip()


def _now():
    return datetime.now(timezone.utc)


def _parse_dt(value):
    return main.parse_dt(value)


def _matches(text, patterns):
    return any(re.search(p, text, re.I) for p in patterns)


def _count(text, patterns):
    return sum(1 for p in patterns if re.search(p, text, re.I))


def _get(path, params):
    key = _api_key()
    if not key:
        return None
    payload = dict(params)
    payload["key"] = key
    try:
        r = SESSION.get(f"{YOUTUBE_API}/{path}", params=payload, timeout=30)
        if r.status_code != 200:
            print("YOUTUBE_API_ERROR", path, r.status_code, r.text[:500])
            return None
        return r.json()
    except Exception as exc:
        print("YOUTUBE_API_EXCEPTION", path, exc)
        return None


def _video_context(text):
    return _matches(text, VIDEO_CONTEXT_PATTERNS)


def discover_videos(deep=False):
    """Discover videos and persist a reusable watchlist.

    Normal discovery favors recently published videos. Deep discovery is intended
    for a weekly run and also finds older evergreen videos that keep receiving new
    buyer comments.
    """
    db = main.firestore_client()
    if not db:
        print("YOUTUBE_DISCOVERY_DISABLED no_firestore")
        return 0

    max_queries = int(os.getenv("YOUTUBE_DISCOVERY_QUERY_LIMIT", "12" if not deep else "22"))
    max_results = min(25, int(os.getenv("YOUTUBE_SEARCH_RESULTS", "15")))
    recent_days = int(os.getenv("YOUTUBE_DISCOVERY_DAYS", "14"))
    queries = DISCOVERY_QUERIES[:max_queries]
    discovered = 0

    for idx, query in enumerate(queries, 1):
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": max_results,
            "order": "relevance" if deep else "date",
            "safeSearch": "none",
        }
        if not deep:
            params["publishedAfter"] = (_now() - timedelta(days=recent_days)).isoformat().replace("+00:00", "Z")

        data = _get("search", params)
        if not data:
            continue

        kept_here = 0
        for row in data.get("items", []):
            video_id = str((row.get("id") or {}).get("videoId") or "").strip()
            snippet = row.get("snippet") or {}
            if not video_id:
                continue
            title = str(snippet.get("title") or "")
            description = str(snippet.get("description") or "")
            channel_title = str(snippet.get("channelTitle") or "")
            combined = f"{title} {description} {channel_title} {query}"
            if not _video_context(combined):
                continue

            doc = {
                "video_id": video_id,
                "title": title,
                "description": description[:1500],
                "channel_id": str(snippet.get("channelId") or ""),
                "channel_title": channel_title,
                "video_published_at": str(snippet.get("publishedAt") or ""),
                "discovered_query": query,
                "discovered_at": _now().isoformat(),
                "last_seen": _now().isoformat(),
                "status": "active",
                "market": "north_cyprus",
                "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
            }
            db.collection(WATCHLIST_COLLECTION).document(video_id).set(doc, merge=True)
            discovered += 1
            kept_here += 1
        print(f"YOUTUBE_DISCOVERY [{idx}/{len(queries)}] query={query!r} kept={kept_here}")

    print(f"YOUTUBE_DISCOVERY_COMPLETE deep={deep} saved={discovered}")
    return discovered


def load_watchlist():
    db = main.firestore_client()
    if not db:
        return []
    limit = int(os.getenv("YOUTUBE_WATCHLIST_LIMIT", "160"))
    videos = []
    try:
        for doc in db.collection(WATCHLIST_COLLECTION).limit(limit * 2).stream():
            data = doc.to_dict() or {}
            if data.get("status") != "active" or data.get("market") != "north_cyprus":
                continue
            if data.get("video_id"):
                videos.append(data)
            if len(videos) >= limit:
                break
    except Exception as exc:
        print("YOUTUBE_WATCHLIST_ERROR", exc)
    print(f"YOUTUBE_WATCHLIST count={len(videos)}")
    return videos


def _iter_comments(video, cutoff):
    """Return recent top-level comments and available replies, newest first."""
    video_id = video.get("video_id")
    pages = max(1, min(3, int(os.getenv("YOUTUBE_COMMENT_PAGES", "1"))))
    page_token = None
    uploader_channel_id = str(video.get("channel_id") or "")

    for _ in range(pages):
        params = {
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 100,
            "order": "time",
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token
        data = _get("commentThreads", params)
        if not data:
            break

        oldest = None
        for thread in data.get("items", []):
            top = (((thread.get("snippet") or {}).get("topLevelComment") or {}))
            comments = [top]
            comments.extend(((thread.get("replies") or {}).get("comments") or []))

            for comment in comments:
                snippet = comment.get("snippet") or {}
                published = _parse_dt(snippet.get("publishedAt"))
                if not published:
                    continue
                oldest = published if oldest is None or published < oldest else oldest
                if published < cutoff:
                    continue

                author_channel = ((snippet.get("authorChannelId") or {}).get("value") or "")
                # Never treat the video's own uploader replying to viewers as a lead.
                if uploader_channel_id and author_channel == uploader_channel_id:
                    continue

                comment_id = str(comment.get("id") or "")
                text = str(snippet.get("textDisplay") or "").strip()
                if not comment_id or not text:
                    continue
                yield {
                    "comment_id": comment_id,
                    "video_id": video_id,
                    "video_title": video.get("title", ""),
                    "channel_title": video.get("channel_title", ""),
                    "text": text,
                    "author": str(snippet.get("authorDisplayName") or ""),
                    "author_channel_id": author_channel,
                    "published": published.isoformat(),
                    "updated": str(snippet.get("updatedAt") or ""),
                    "url": f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}",
                    "source": "YouTube Comment",
                }

        # Because results are ordered newest first, we can stop once this page
        # already reaches beyond the lookback window.
        if oldest and oldest < cutoff:
            break
        page_token = data.get("nextPageToken")
        if not page_token:
            break


def classify_comment(item):
    comment = item.get("text", "")
    video_context = f"{item.get('video_title','')} {item.get('channel_title','')}"
    full = f"{comment} {video_context}"

    if not _video_context(video_context):
        return None
    if _matches(comment, NOISE_PATTERNS):
        return None
    if _matches(comment, SERVICE_AD_PATTERNS):
        return None

    seller_hits = _count(comment, SELLER_PROMO_PATTERNS)
    strong_hits = _count(comment, STRONG_BUYER_PATTERNS)
    request_hits = _count(comment, REQUEST_PATTERNS)
    concrete_hits = _count(comment, CONCRETE_PATTERNS)
    property_hits = _count(full, PROPERTY_PATTERNS)

    # Do not reject a genuine user who says "I am interested, contact me" just
    # because one commercial-looking phrase is present. Repeated seller language is required.
    if seller_hits >= 2 and strong_hits == 0:
        return None

    # High-recall YouTube rule: on a clearly relevant property video, terse
    # questions like "price?", "2+1?", "рассрочка?" are commercially useful.
    if strong_hits == 0 and request_hits == 0:
        return None
    if property_hits == 0 and request_hits == 0:
        return None

    intent = min(100, 56 + strong_hits * 18 + request_hits * 9 + concrete_hits * 7)
    credibility = min(100, 64 + (6 if item.get("author") else 0) + min(12, len(comment) // 25) + concrete_hits * 5)
    fit = 94

    if strong_hits and (concrete_hits or request_hits >= 2) and intent >= 82:
        label = "HOT"
    elif strong_hits or request_hits >= 1:
        label = "WARM"
    else:
        label = "POTENTIAL"

    return {
        **item,
        "classification": label,
        "intent_score": intent,
        "credibility_score": credibility,
        "market_fit_score": fit,
        "market": "north_cyprus",
        "scanned_at": _now().isoformat(),
        "why": "Recent YouTube viewer comment with North Cyprus property purchase, pricing, availability, project, budget or transaction intent.",
    }


def _notified_before(db, comment_id):
    if not db:
        return False
    key = hashlib.sha1(comment_id.encode("utf-8")).hexdigest()
    try:
        return db.collection(NOTIFIED_COLLECTION).document(key).get().exists
    except Exception as exc:
        print("YOUTUBE_DEDUPE_READ_ERROR", exc)
        return False


def _mark_notified(db, lead):
    if not db:
        return
    key = hashlib.sha1(lead["comment_id"].encode("utf-8")).hexdigest()
    try:
        db.collection(NOTIFIED_COLLECTION).document(key).set({
            "comment_id": lead["comment_id"],
            "video_id": lead["video_id"],
            "url": lead["url"],
            "classification": lead["classification"],
            "notified_at": _now().isoformat(),
        }, merge=True)
    except Exception as exc:
        print("YOUTUBE_DEDUPE_WRITE_ERROR", exc)


def scan_comments():
    lookback_hours = int(os.getenv("YOUTUBE_LOOKBACK_HOURS", "6"))
    cutoff = _now() - timedelta(hours=lookback_hours)
    db = main.firestore_client()
    videos = load_watchlist()
    candidates = 0
    leads = []
    errors = 0

    for idx, video in enumerate(videos, 1):
        try:
            found_here = 0
            for item in _iter_comments(video, cutoff):
                candidates += 1
                lead = classify_comment(item)
                if not lead:
                    continue
                if _notified_before(db, lead["comment_id"]):
                    continue
                leads.append(lead)
                found_here += 1
            if found_here:
                print(f"YOUTUBE_VIDEO_LEADS [{idx}/{len(videos)}] {video.get('title','')[:80]!r} leads={found_here}")
        except Exception as exc:
            errors += 1
            print("YOUTUBE_VIDEO_ERROR", video.get("video_id"), exc)

    # One comment id is globally unique; this also protects against API overlap.
    unique = {x["comment_id"]: x for x in leads}
    leads = list(unique.values())
    rank = {"HOT": 3, "WARM": 2, "POTENTIAL": 1}
    leads.sort(key=lambda x: (rank.get(x["classification"], 0), x["intent_score"], x["credibility_score"]), reverse=True)

    scan_id = _now().strftime("%Y%m%d%H%M%S")
    if db:
        try:
            scan_ref = db.collection(SCAN_COLLECTION).document(scan_id)
            batch = db.batch()
            for lead in leads[:100]:
                doc_id = hashlib.sha1(lead["comment_id"].encode("utf-8")).hexdigest()
                batch.set(scan_ref.collection("leads").document(doc_id), lead, merge=True)
            batch.set(scan_ref, {
                "scanned_at": _now().isoformat(),
                "lookback_hours": lookback_hours,
                "watchlist_videos": len(videos),
                "recent_comments": candidates,
                "new_leads": len(leads),
                "errors": errors,
            }, merge=True)
            batch.commit()
        except Exception as exc:
            print("YOUTUBE_FIRESTORE_ERROR", exc)

    if leads:
        lines = [f"📺 BAY-S YOUTUBE RADAR | {len(leads)} YENİ ADAY"]
        for lead in leads[:12]:
            excerpt = " ".join(lead.get("text", "").split())[:240]
            lines.append(
                f"\n{lead['classification']} | {lead.get('author') or 'kullanıcı'} | "
                f"I{lead['intent_score']} C{lead['credibility_score']}\n"
                f"🎬 {lead.get('video_title','')[:95]}\n"
                f"💬 {excerpt}\n{lead['url']}"
            )
            _mark_notified(db, lead)
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(
            f"📺 BAY-S YOUTUBE RADAR tamamlandı.\n"
            f"Yeni alıcı adayı yok.\n"
            f"İzlenen video: {len(videos)}\n"
            f"Son {lookback_hours} saatte incelenen yorum: {candidates}"
        )

    print(
        "YOUTUBE_SCAN_COMPLETE",
        json.dumps({
            "watchlist": len(videos),
            "recent_comments": candidates,
            "new_leads": len(leads),
            "errors": errors,
            "lookback_hours": lookback_hours,
        }, ensure_ascii=False),
    )
    return leads


def run():
    if not _api_key():
        print("YOUTUBE_RADAR_DISABLED missing YOUTUBE_API_KEY")
        return

    mode = os.getenv("YOUTUBE_MODE", "scan").strip().lower()
    if mode in ("discover", "discover_scan"):
        discover_videos(deep=False)
    elif mode in ("deep", "deep_scan"):
        discover_videos(deep=True)

    if mode in ("scan", "discover_scan", "deep_scan"):
        scan_comments()


if __name__ == "__main__":
    run()
