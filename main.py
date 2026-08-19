import os
import re
import json
import time
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from google.cloud import firestore
from google.oauth2 import service_account

from config import *

UA = "Mozilla/5.0 (compatible; BAY-S-World-Radar/1.1)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
REQUEST_TIMEOUT = 15

# HARD COST GUARD: never make more than this many Exa requests in one run.
EXA_MAX_CALLS = int(os.getenv("WORLD_EXA_MAX_CALLS", "20"))


def now_utc():
    return datetime.now(timezone.utc)


def parse_dt(value):
    if not value:
        return None
    try:
        v = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        from email.utils import parsedate_to_datetime
        try:
            dt = parsedate_to_datetime(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None


def text_of(item):
    return " ".join(str(item.get(k, "")) for k in ("title", "text", "author")).lower()


def market_for(text):
    t = text.lower()
    for market, terms in MARKETS.items():
        if any(term.lower() in t for term in terms):
            return market
    return "unknown"


def route_for(market):
    return ROUTES.get(market, "Direct Review")


def contains_any(text, phrases):
    return any(p.lower() in text for p in phrases)


def dedupe_key(item):
    basis = item.get("url") or f"{item.get('source')}|{item.get('title')}|{item.get('author')}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def reddit_search(query):
    url = "https://www.reddit.com/search.rss"
    r = SESSION.get(url, params={"q": query, "sort": "new", "t": "day", "limit": MAX_RESULTS_PER_SOURCE}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for entry in soup.find_all("entry")[:MAX_RESULTS_PER_SOURCE]:
        link = entry.find("link")
        out.append({
            "source": "Reddit",
            "url": link.get("href", "") if link else "",
            "title": entry.find("title").get_text(" ", strip=True) if entry.find("title") else "",
            "text": entry.find("content").get_text(" ", strip=True) if entry.find("content") else "",
            "published": entry.find("published").get_text(strip=True) if entry.find("published") else "",
            "author": entry.find("name").get_text(" ", strip=True) if entry.find("name") else "",
        })
    return out


def google_news(query):
    # Discovery only. News pages are NEVER accepted as buyer leads by themselves.
    url = "https://news.google.com/rss/search"
    r = SESSION.get(url, params={"q": f"{query} when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for item in soup.find_all("item")[:MAX_RESULTS_PER_SOURCE]:
        out.append({
            "source": "Google News",
            "url": item.find("link").get_text(strip=True) if item.find("link") else "",
            "title": item.find("title").get_text(" ", strip=True) if item.find("title") else "",
            "text": item.find("description").get_text(" ", strip=True) if item.find("description") else "",
            "published": item.find("pubDate").get_text(strip=True) if item.find("pubDate") else "",
            "author": "",
        })
    return out


def exa_search(query):
    api_key = os.getenv("EXA_API_KEY", "").strip()
    if not api_key:
        return []
    payload = {
        "query": query,
        "type": "auto",
        "numResults": min(EXA_NUM_RESULTS, 5),
        "contents": {"text": True},
    }
    r = SESSION.post(
        "https://api.exa.ai/search",
        json=payload,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        timeout=30,
    )
    if r.status_code != 200:
        print("EXA", r.status_code, r.text[:400])
        return []
    data = r.json()
    return [{
        "source": "Exa",
        "url": x.get("url", ""),
        "title": x.get("title", ""),
        "text": x.get("text", ""),
        "published": x.get("publishedDate", ""),
        "author": "",
    } for x in data.get("results", [])]


def buyer_scores(item):
    text = text_of(item)
    # News and generic search pages are not buyers.
    if item.get("source") == "Google News":
        return 0, 0, 0, "COLD"

    intent_hits = sum(1 for p in INTENT_PHRASES if p.lower() in text)
    personal_hits = sum(1 for p in [
        "i am", "i'm", "we are", "we're", "my budget", "our budget", "i want", "we want",
        "ben", "biz", "bütçem", "я ", "мы ", "мой бюджет", "наш бюджет"
    ] if p in text)
    budget = bool(re.search(r"(?:€|£|\$|₺|₽)\s?\d[\d,.\s]*(?:k|m)?|\b\d{2,3}\s?[km]\b", text))
    location = market_for(text) != "unknown"
    transaction = sum(1 for p in ["viewing", "offer", "deposit", "mortgage", "lawyer", "title deed", "payment plan", "due diligence", "reservation"] if p in text)
    seller_hits = sum(1 for p in EXCLUDE_PHRASES if p.lower() in text)
    negative = contains_any(text, NEGATIVE_PHRASES)

    intent = min(100, 30 + intent_hits * 7 + personal_hits * 5 + (15 if budget else 0) + (12 if location else 0) + min(18, transaction * 3) - min(40, seller_hits * 8))
    credibility = min(100, 48 + personal_hits * 6 + (15 if budget else 0) + (12 if len(text) > 500 else 0) + (6 if item.get("author") else 0) - min(35, seller_hits * 9))
    fit = 55 + (15 if location else 0) + (10 if budget else 0)
    if "golden visa" in text or "residency by investment" in text:
        fit += 5
    fit = min(100, fit)

    if negative:
        return 0, 0, 0, "COLD"
    if intent >= 82 and credibility >= 72 and fit >= 65:
        label = "HOT"
    elif intent >= 60 and credibility >= 62 and fit >= 50:
        label = "WARM"
    elif intent >= 45:
        label = "REVIEW"
    else:
        label = "COLD"
    return intent, credibility, fit, label


def keep_candidate(item):
    text = text_of(item)
    if item.get("source") == "Google News":
        return False
    if contains_any(text, NEGATIVE_PHRASES):
        return False
    seller_hits = sum(1 for p in EXCLUDE_PHRASES if p.lower() in text)
    personal = contains_any(text, ["i want", "i'm looking", "i am looking", "we want", "we're looking", "my budget", "our budget", "ben", "biz", "хочу", "ищу"])
    if seller_hits >= 2 and not personal:
        return False
    if "for rent" in text or "kiralık" in text or "сдам" in text:
        return False
    return contains_any(text, INTENT_PHRASES)


def queries_for(markets):
    phrases = {
        "north_cyprus": "North Cyprus Northern Cyprus",
        "turkey": "Turkey Türkiye",
        "montenegro": "Montenegro Karadağ Черногория",
        "greece": "Greece Greek Golden Visa",
        "portugal": "Portugal property Golden Visa",
        "spain": "Spain property",
        "italy": "Italy property investor",
        "cyprus": "Cyprus property",
        "germany": "Germany property expat",
        "netherlands": "Netherlands property expat",
        "belgium": "Belgium property expat",
        "france": "France property expat",
        "lithuania": "Lithuania property",
        "russia": "Russian buyer property abroad",
        "kazakhstan": "Kazakhstan buyer property abroad",
        "uk": "UK buyer property abroad",
        "poland": "Poland property abroad",
        "czech_republic": "Czech property abroad",
        "austria": "Austria property abroad",
    }
    queries = []
    intent_groups = [
        '"looking to buy" property budget',
        '"looking for apartment" property',
        '"moving to" property buy',
        '"property viewing" buyer',
        '"investment property" budget',
        '"golden visa" property budget',
        '"residency by investment" property',
        '"хочу купить" недвижимость',
        '"ищу квартиру" бюджет',
        '"недвижимость за рубежом" инвестиции',
        '"ev almak istiyorum" bütçe',
        '"daire arıyorum" yatırım',
    ]
    for market in markets:
        phrase = phrases.get(market, market)
        for intent in intent_groups:
            queries.append(f"{phrase} {intent}")
    return queries


def exa_priority_queries(markets):
    # PAID SEARCH is deliberately much smaller than the free-source query matrix.
    phrases = {
        "north_cyprus": "North Cyprus property buyer looking to buy apartment budget forum expat Reddit Telegram",
        "turkey": "Turkey property buyer looking to buy apartment budget Turkish expat forum Reddit",
        "montenegro": "Montenegro property buyer looking to buy apartment budget expat forum Reddit Russian",
        "greece": "Greece Golden Visa property buyer budget expat forum Reddit",
        "portugal": "Portugal Golden Visa property buyer budget expat forum Reddit",
        "spain": "Spain property buyer relocation budget expat forum Reddit",
        "italy": "Italy property buyer relocation budget expat forum Reddit",
        "cyprus": "Cyprus property buyer relocation budget expat forum Reddit",
        "germany": "Germany property buyer expat budget forum Reddit",
        "netherlands": "Netherlands property buyer expat budget forum Reddit",
        "belgium": "Belgium property buyer expat budget forum Reddit",
        "france": "France property buyer expat budget forum Reddit",
        "lithuania": "Lithuania property buyer expat budget forum Reddit",
        "russia": "Russian buyer property abroad budget Cyprus Greece Montenegro Europe forum Telegram",
        "kazakhstan": "Kazakhstan buyer property abroad budget Europe Cyprus Montenegro forum Telegram",
        "uk": "UK buyer property abroad budget Cyprus Spain Portugal Montenegro expat forum Reddit",
        "poland": "Poland property buyer abroad budget expat forum Reddit",
        "czech_republic": "Czech buyer property abroad budget expat forum Reddit",
        "austria": "Austria buyer property abroad budget expat forum Reddit",
    }
    return [phrases[m] for m in markets if m in phrases][:EXA_MAX_CALLS]


def firestore_client():
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(info)
    return firestore.Client(credentials=creds, project=info.get("project_id"))


def notify_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": message[:3900]}, timeout=15)
    except Exception as exc:
        print("TELEGRAM_NOTIFY_ERROR", exc)


def run():
    started = now_utc()
    markets = list(MARKETS.keys())
    seen = set()
    leads = []
    queries = queries_for(markets)
    cutoff = started - timedelta(hours=LOOKBACK_HOURS)

    # PHASE 1: free/low-cost discovery only.
    for i, query in enumerate(queries, 1):
        print(f"FREE [{i}/{len(queries)}] {query}")
        batches = []
        try:
            batches.extend(reddit_search(query))
        except Exception as exc:
            print("REDDIT_ERROR", exc)
        try:
            batches.extend(google_news(query))
        except Exception as exc:
            print("NEWS_ERROR", exc)

        for item in batches:
            key = dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            published = parse_dt(item.get("published"))
            if published and published < cutoff:
                continue
            if not keep_candidate(item):
                continue
            market = market_for(text_of(item))
            intent, credibility, fit, label = buyer_scores(item)
            if label not in ("HOT", "WARM"):
                continue
            item.update({"market": market, "intent_score": intent, "credibility_score": credibility,
                         "market_fit_score": fit, "classification": label, "route_to": route_for(market),
                         "scanned_at": started.isoformat()})
            leads.append(item)
        time.sleep(0.2)

    # PHASE 2: paid Exa discovery with a hard per-run cap.
    exa_queries = exa_priority_queries(markets)
    print(f"EXA_BUDGET_GUARD max_calls={EXA_MAX_CALLS} scheduled={len(exa_queries)}")
    exa_calls = 0
    for query in exa_queries:
        if exa_calls >= EXA_MAX_CALLS:
            print("EXA_BUDGET_GUARD reached; no more paid calls.")
            break
        exa_calls += 1
        print(f"EXA [{exa_calls}/{len(exa_queries)}] {query}")
        try:
            batches = exa_search(query)
        except Exception as exc:
            print("EXA_ERROR", exc)
            continue
        for item in batches:
            key = dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            published = parse_dt(item.get("published"))
            if published and published < cutoff:
                continue
            if not keep_candidate(item):
                continue
            market = market_for(text_of(item))
            intent, credibility, fit, label = buyer_scores(item)
            if label not in ("HOT", "WARM"):
                continue
            item.update({"market": market, "intent_score": intent, "credibility_score": credibility,
                         "market_fit_score": fit, "classification": label, "route_to": route_for(market),
                         "scanned_at": started.isoformat()})
            leads.append(item)

    leads.sort(key=lambda x: (x["classification"] == "HOT", x["intent_score"], x["credibility_score"], x["market_fit_score"]), reverse=True)

    db = firestore_client()
    if db:
        batch = db.batch()
        for lead in leads[:100]:
            ref = db.collection(COLLECTION).document(hashlib.sha1((lead.get("url") or lead.get("title", "")).encode()).hexdigest())
            batch.set(ref, lead, merge=True)
        scan_ref = db.collection(SCAN_LOG_COLLECTION).document(started.strftime("%Y%m%d%H%M%S"))
        batch.set(scan_ref, {"started_at": started.isoformat(), "finished_at": now_utc().isoformat(),
                             "free_queries": len(queries), "exa_calls": exa_calls,
                             "unique_candidates": len(seen), "hot_warm": len(leads)})
        batch.commit()

    if leads:
        lines = [f"BAY-S WORLD RADAR — {len(leads)} HOT/WARM buyer(s) | Exa calls: {exa_calls}"]
        for lead in leads[:10]:
            lines.append(f"{lead['classification']} | {lead['market']} | I:{lead['intent_score']} C:{lead['credibility_score']} F:{lead['market_fit_score']} | {lead.get('title','')[:140]} | {lead.get('url','')}")
        notify_telegram("\n".join(lines))
        print("HOT/WARM:", len(leads))
    else:
        print("No HOT/WARM leads found in the selected 24h window.")


if __name__ == "__main__":
    run()
