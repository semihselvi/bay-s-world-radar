import os
import re
import json
import html
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import main
import world_engine  # applies the production buyer/freshness/scoring policy to main


# Direct-source first. Exa is only the gap-filler.
REDDIT_FEEDS = [
    "https://www.reddit.com/r/RealEstate/new/.rss",
    "https://www.reddit.com/r/FirstTimeHomeBuyer/new/.rss",
    "https://www.reddit.com/r/FirstTimeHomeBuying/new/.rss",
    "https://www.reddit.com/r/HousingUK/new/.rss",
    "https://www.reddit.com/r/FirstTimeBuyersUK/new/.rss",
    "https://www.reddit.com/r/propertyinvesting/new/.rss",
    "https://www.reddit.com/r/dubairealestate/new/.rss",
    "https://www.reddit.com/r/AusPropertyChat/new/.rss",
    "https://www.reddit.com/r/orlando/new/.rss",
]

HTML_LATEST_SOURCES = [
    ("Expat.com", "https://www.expat.com/en/forum/", "expat.com"),
    ("ExpatForum", "https://www.expatforum.com/whats-new/posts/", "expatforum.com"),
]

DISCOURSE_LATEST = [
    ("Nomad Gate", "https://community.nomadgate.com/latest.json", "community.nomadgate.com"),
]

EXA_FALLBACKS = [
    {
        "name": "exa_global_gapfill",
        "domains": [
            "reddit.com", "expat.com", "expatforum.com", "nomadgate.com", "bogleheads.org",
            "montenegroexpats.com", "forum-eu.com", "completefrance.com", "pim.be",
            "internations.org", "t.me", "tlgrm.ru", "telega.io"
        ],
        "query": "past 7 days real person first-person property buyer discussion: wants to buy house apartment flat villa property, house hunting, mortgage deposit viewing offer budget relocation with purchase intent; North Cyprus Turkey Montenegro Greece Portugal Spain Italy Cyprus UK Germany France Netherlands Belgium Austria Poland Czechia Golden Visa; exclude listings agents developers guides news articles"
    },
    {
        "name": "exa_russian_cis_gapfill",
        "domains": ["reddit.com", "forum.awd.ru", "expat.com", "forum-eu.com", "internations.org", "t.me", "tlgrm.ru", "telega.io"],
        "query": "past 7 days реальный человек хочет купить недвижимость за рубежом: хочу купить ищу квартиру ищу дом ищу виллу планирую купить бюджет ипотека взнос просмотр переезд ВНЖ; Montenegro Северный Кипр Greece Turkey Portugal Spain Italy Germany France Europe Kazakhstan; exclude advertisements agents developers portals articles"
    },
]


def clean_text(value):
    if not value:
        return ""
    return BeautifulSoup(html.unescape(str(value)), "html.parser").get_text(" ", strip=True)


def parse_xml_feed(url, source_name):
    items = []
    try:
        r = main.SESSION.get(url, timeout=20, headers={"Accept": "application/atom+xml,application/rss+xml,text/xml;q=0.9,*/*;q=0.8"})
        if r.status_code != 200:
            print(f"DIRECT_ERROR {source_name} {r.status_code} {url}")
            return []
        root = ET.fromstring(r.content)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entries = root.findall("a:entry", ns)
        for entry in entries[:30]:
            title = clean_text(entry.findtext("a:title", default="", namespaces=ns))
            author = clean_text(entry.findtext("a:author/a:name", default="", namespaces=ns))
            published = entry.findtext("a:published", default="", namespaces=ns) or entry.findtext("a:updated", default="", namespaces=ns)
            content = entry.findtext("a:content", default="", namespaces=ns) or entry.findtext("a:summary", default="", namespaces=ns)
            link = ""
            for node in entry.findall("a:link", ns):
                href = node.attrib.get("href", "")
                if href and (node.attrib.get("rel", "alternate") in ("", "alternate")):
                    link = href
                    break
            if link:
                items.append({"source": source_name, "url": link, "title": title, "text": clean_text(content), "published": published, "author": author, "source_bucket": "direct_reddit"})
    except Exception as exc:
        print(f"DIRECT_EXCEPTION {source_name} {url} {exc}")
    return items


def extract_page_item(url, source_name, fallback_title="", source_bucket="direct_html"):
    try:
        r = main.SESSION.get(url, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, "html.parser")
        title = fallback_title or clean_text(soup.title.string if soup.title else "")
        author = ""
        published = ""
        for selector, attr in [
            ('meta[property="article:published_time"]', "content"),
            ('meta[name="date"]', "content"),
            ('meta[name="pubdate"]', "content"),
            ('time[datetime]', "datetime"),
        ]:
            node = soup.select_one(selector)
            if node and node.get(attr):
                published = node.get(attr)
                break
        for selector, attr in [
            ('meta[name="author"]', "content"),
            ('meta[property="article:author"]', "content"),
        ]:
            node = soup.select_one(selector)
            if node and node.get(attr):
                author = clean_text(node.get(attr))
                break
        # Keep enough page text for timestamp + buyer context, but not navigation megabytes.
        main_node = soup.select_one("article") or soup.select_one("main") or soup.body or soup
        text = clean_text(main_node.get_text(" ", strip=True))[:12000]
        if not published:
            # Preserve textual dates for world_engine.resolved_published.
            m = re.search(r"\b(?:just now|\d+\s+(?:minutes?|hours?)\s+ago|today|yesterday|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20\d{2})\b", text, re.I)
            if m:
                text = f"{m.group(0)} {text}"
        return {"source": source_name, "url": r.url, "title": title, "text": text, "published": published, "author": author, "source_bucket": source_bucket}
    except Exception as exc:
        print(f"DIRECT_PAGE_EXCEPTION {source_name} {url} {exc}")
        return None


def scrape_latest_links(source_name, index_url, allowed_domain):
    items = []
    try:
        r = main.SESSION.get(index_url, timeout=20)
        if r.status_code != 200:
            print(f"DIRECT_ERROR {source_name} {r.status_code} {index_url}")
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(r.url, a["href"])
            host = urlparse(href).netloc.lower().replace("www.", "")
            text = clean_text(a.get_text(" ", strip=True))
            if allowed_domain not in host or not text or len(text) < 8:
                continue
            low = href.lower()
            if source_name == "Expat.com" and "/forum/" not in low:
                continue
            if source_name == "ExpatForum" and not any(x in low for x in ("/threads/", "/posts/")):
                continue
            if href not in [x[0] for x in links]:
                links.append((href, text))
            if len(links) >= 15:
                break
        for href, title in links:
            item = extract_page_item(href, source_name, title, "direct_forum")
            if item:
                items.append(item)
    except Exception as exc:
        print(f"DIRECT_EXCEPTION {source_name} {index_url} {exc}")
    return items


def discourse_latest(source_name, api_url, host):
    items = []
    try:
        r = main.SESSION.get(api_url, timeout=20, headers={"Accept": "application/json"})
        if r.status_code != 200:
            print(f"DIRECT_ERROR {source_name} {r.status_code} {api_url}")
            return []
        data = r.json()
        for topic in data.get("topic_list", {}).get("topics", [])[:20]:
            slug = topic.get("slug")
            tid = topic.get("id")
            if not slug or not tid:
                continue
            page_url = f"https://{host}/t/{slug}/{tid}"
            item = extract_page_item(page_url, source_name, topic.get("title", ""), "direct_discourse")
            if item:
                item["published"] = topic.get("created_at", "") or item.get("published", "")
                items.append(item)
    except Exception as exc:
        print(f"DIRECT_EXCEPTION {source_name} {api_url} {exc}")
    return items


def telegram_public_channels():
    raw = os.getenv("WORLD_TELEGRAM_CHANNELS", "").strip()
    channels = [x.strip().lstrip("@") for x in raw.split(",") if x.strip()]
    items = []
    for channel in channels:
        url = f"https://t.me/s/{channel}"
        try:
            r = main.SESSION.get(url, timeout=20)
            if r.status_code != 200:
                print(f"DIRECT_ERROR Telegram {r.status_code} {channel}")
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for wrap in soup.select(".tgme_widget_message_wrap")[-30:]:
                link = wrap.select_one("a.tgme_widget_message_date")
                body = wrap.select_one(".tgme_widget_message_text")
                time_node = wrap.select_one("time[datetime]")
                if not link or not body:
                    continue
                items.append({
                    "source": "Telegram",
                    "url": link.get("href", ""),
                    "title": f"Telegram @{channel}",
                    "text": clean_text(body.get_text(" ", strip=True)),
                    "published": time_node.get("datetime", "") if time_node else "",
                    "author": f"@{channel}",
                    "source_bucket": "direct_telegram",
                })
        except Exception as exc:
            print(f"DIRECT_EXCEPTION Telegram {channel} {exc}")
    return items


def direct_discovery():
    all_items = []
    counts = {}
    for feed in REDDIT_FEEDS:
        found = parse_xml_feed(feed, "Reddit")
        all_items.extend(found)
        counts[feed] = len(found)
    for source_name, index_url, domain in HTML_LATEST_SOURCES:
        found = scrape_latest_links(source_name, index_url, domain)
        all_items.extend(found)
        counts[source_name] = len(found)
    for source_name, api_url, host in DISCOURSE_LATEST:
        found = discourse_latest(source_name, api_url, host)
        all_items.extend(found)
        counts[source_name] = len(found)
    tg = telegram_public_channels()
    all_items.extend(tg)
    counts["Telegram"] = len(tg)
    print("DIRECT_COUNTS", json.dumps(counts, ensure_ascii=False))
    return all_items, counts


def exa_gapfill():
    items = []
    calls = 0
    max_calls = min(int(os.getenv("WORLD_EXA_FALLBACK_CALLS", "2")), len(EXA_FALLBACKS))
    for bucket in EXA_FALLBACKS[:max_calls]:
        calls += 1
        print(f"EXA_FALLBACK [{calls}/{max_calls}] {bucket['name']}")
        for item in world_engine.exa_search(bucket["query"], bucket["domains"]):
            item["source_bucket"] = bucket["name"]
            items.append(item)
    return items, calls


def process_items(items, started, stats):
    cutoff = started - timedelta(hours=main.LOOKBACK_HOURS)
    seen = set()
    leads = []
    for item in items:
        key = main.dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        published = world_engine.resolved_published(item)
        item["verified_published"] = published.isoformat() if published else ""
        item["published_source"] = "direct_or_page" if item.get("source", "") != "Exa" else "exa_or_page"
        keep, reason = main.keep_candidate(item, cutoff)
        if not keep:
            stats[reason] = stats.get(reason, 0) + 1
            continue
        market = main.market_for(main.text_of(item), item.get("source_bucket", ""), item.get("url", ""), item.get("title", ""))
        item["market"] = market
        intent, credibility, fit, label = main.buyer_scores(item)
        if label not in ("HOT", "WARM"):
            stats["review_or_cold"] = stats.get("review_or_cold", 0) + 1
            continue
        item.update({
            "intent_score": intent,
            "credibility_score": credibility,
            "market_fit_score": fit,
            "classification": label,
            "route_to": main.route_for(market),
            "why": "Fresh public user discussion with personal purchase intent and concrete property/transaction evidence.",
            "suggested_reply": main.suggested_reply(market),
            "scanned_at": started.isoformat(),
            "source_domain": main.domain_of(item.get("url", "")),
        })
        leads.append(item)
    return seen, leads


def save_and_notify(started, seen, leads, stats, direct_counts, exa_calls):
    leads = list({main.dedupe_key(x): x for x in leads}.values())
    leads.sort(key=lambda x: (x["classification"] == "HOT", x["intent_score"], x["credibility_score"], x["market_fit_score"]), reverse=True)
    scan_id = started.strftime("%Y%m%d%H%M%S")
    db = main.firestore_client()
    if db:
        scan_ref = db.collection(main.SCAN_LOG_COLLECTION).document(scan_id)
        batch = db.batch()
        for lead in leads[:100]:
            docid = hashlib.sha1((lead.get("url") or lead.get("title", "")).encode("utf-8")).hexdigest()
            batch.set(scan_ref.collection("leads").document(docid), lead, merge=True)
        batch.set(scan_ref, {
            "engine": "hybrid_direct_first",
            "started_at": started.isoformat(),
            "finished_at": main.now_utc().isoformat(),
            "direct_counts": direct_counts,
            "exa_calls": exa_calls,
            "unique_candidates": len(seen),
            "hot_warm": len(leads),
            "lookback_hours": main.LOOKBACK_HOURS,
            "filter_stats": stats,
        }, merge=True)
        batch.commit()

    print(f"SCAN_COMPLETE engine=hybrid candidates={len(seen)} hot_warm={len(leads)} exa_calls={exa_calls}")
    print("FILTER_STATS", json.dumps(stats, ensure_ascii=False))

    if leads:
        lines = [f"BAY-S WORLD RADAR | {len(leads)} HOT/WARM | Aday: {len(seen)} | Exa: {exa_calls}"]
        for lead in leads[:10]:
            lines.append(f"{lead['classification']} | {lead['market']} | {lead.get('source','')} | I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']} | {lead.get('title','')[:100]} | {lead.get('url','')}")
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(
            f"BAY-S WORLD RADAR tamamlandı.\nYeni HOT/WARM lead yok.\nİncelenen aday: {len(seen)}\nDoğrudan kaynaklar tarandı.\nExa tamamlayıcı çağrı: {exa_calls}\nTarama: son {main.LOOKBACK_HOURS} saat"
        )


def run():
    started = main.now_utc()
    stats = {
        "non_user_source": 0, "date_unverified": 0, "older_than_24h": 0,
        "editorial_or_article": 0, "not_enough_user_discussion_signal": 0,
        "negative_or_rental": 0, "seller_agent": 0, "no_buyer_intent": 0,
        "review_or_cold": 0,
    }
    direct_items, direct_counts = direct_discovery()
    exa_items, exa_calls = exa_gapfill()
    seen, leads = process_items(direct_items + exa_items, started, stats)
    save_and_notify(started, seen, leads, stats, direct_counts, exa_calls)


if __name__ == "__main__":
    run()
