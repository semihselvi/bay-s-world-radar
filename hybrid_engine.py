import os
import json
import html
import hashlib
from datetime import timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import main
import world_engine
from source_registry import (
    REDDIT_SUBREDDITS,
    TELEGRAM_PUBLIC_CHANNELS,
    DIRECT_INDEX_SOURCES,
    DIRECT_TOPIC_SOURCES,
    EXA_GAPFILL_DOMAINS,
)

DIRECT_LINK_LIMIT = int(os.getenv("WORLD_DIRECT_LINK_LIMIT", "12"))
EXA_FALLBACK_CALLS = min(int(os.getenv("WORLD_EXA_FALLBACK_CALLS", "2")), 2)

SKIP_URL_PARTS = (
    "upload.php", "/members/", "/member/", "email-protection", "/login", "/register",
    "/profile", "/search", "/privacy", "/terms", "/contact", "javascript:", "mailto:"
)


def clean_text(value):
    return BeautifulSoup(html.unescape(str(value or "")), "html.parser").get_text(" ", strip=True)


def reddit_direct():
    # GitHub Actions receives 403 from Reddit RSS. Do not waste requests here.
    # Reddit is covered by the Exa gap-fill using only the researched subreddits/topics.
    print(f"REDDIT_DIRECT_DISABLED use_exa_gapfill subs={len(REDDIT_SUBREDDITS)}")
    return []


def extract_page_item(url, source_name, title="", source_bucket="direct_topic", forced_market=""):
    try:
        response = main.SESSION.get(url, timeout=20, allow_redirects=True)
        if response.status_code != 200:
            print(f"DIRECT_ERROR {source_name} {response.status_code} {url}")
            return None
        soup = BeautifulSoup(response.text, "html.parser")
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
        author = ""
        for selector, attr in [('meta[name="author"]', "content"), ('meta[property="article:author"]', "content")]:
            node = soup.select_one(selector)
            if node and node.get(attr):
                author = clean_text(node.get(attr))
                break
        body = soup.select_one("article") or soup.select_one("main") or soup.body or soup
        text = clean_text(body.get_text(" ", strip=True))[:12000]
        return {
            "source": source_name,
            "url": response.url,
            "title": title or clean_text(soup.title.string if soup.title else ""),
            "text": text,
            "published": published,
            "author": author,
            "source_bucket": source_bucket,
            "forced_market": forced_market,
        }
    except Exception as exc:
        print(f"DIRECT_EXCEPTION {source_name} {url} {exc}")
        return None


def _looks_like_discussion_link(source_name, href, title):
    low = href.lower()
    t = title.lower()
    if any(part in low for part in SKIP_URL_PARTS):
        return False
    if len(title) < 8:
        return False
    if source_name == "MoneySavingExpert":
        return "/discussion/" in low
    if source_name.startswith("Expat.com"):
        return "/forum/" in low and any(ch.isdigit() for ch in low)
    if source_name == "PIM.be":
        return "topic-" in low
    if source_name == "Forum AWD Overseas Property":
        return "viewtopic.php" in low
    if source_name == "Forum-EU":
        return "/topic/" in low
    if source_name == "Investisseurs Heureux":
        return "/t" in low or "topic" in low
    if source_name == "MontenegroExpats":
        return any(k in t for k in ("property", "real estate", "buy", "invest", "resid", "expat"))
    return True


def scrape_index_source(source):
    if source.get("discovery_only"):
        print(f"DISCOVERY_ONLY {source['name']} {source['url']}")
        return []

    items = []
    try:
        response = main.SESSION.get(source["url"], timeout=20, allow_redirects=True)
        if response.status_code != 200:
            print(f"DIRECT_ERROR {source['name']} {response.status_code} {source['url']}")
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        links = []
        for anchor in soup.find_all("a", href=True):
            href = urljoin(response.url, anchor["href"])
            host = urlparse(href).netloc.lower().replace("www.", "")
            title = clean_text(anchor.get_text(" ", strip=True))
            if source["domain"].replace("www.", "") not in host:
                continue
            if href == response.url or not _looks_like_discussion_link(source["name"], href, title):
                continue
            if href not in [x[0] for x in links]:
                links.append((href, title))
            if len(links) >= DIRECT_LINK_LIMIT:
                break

        for href, title in links:
            item = extract_page_item(href, source["name"], title, "direct_index", source.get("market", ""))
            if item:
                items.append(item)
    except Exception as exc:
        print(f"DIRECT_EXCEPTION {source['name']} {exc}")
    return items


def direct_topics():
    items = []
    for source in DIRECT_TOPIC_SOURCES:
        item = extract_page_item(source["url"], source["name"], "", "direct_topic", source.get("market", ""))
        if item:
            items.append(item)
    return items


def telegram_public_channels():
    items = []
    extra = [x.strip().lstrip("@") for x in os.getenv("WORLD_TELEGRAM_CHANNELS", "").split(",") if x.strip()]
    channels = list(dict.fromkeys(TELEGRAM_PUBLIC_CHANNELS + extra))
    for channel in channels:
        try:
            response = main.SESSION.get(f"https://t.me/s/{channel}", timeout=20)
            if response.status_code != 200:
                print(f"DIRECT_ERROR Telegram {response.status_code} @{channel}")
                continue
            soup = BeautifulSoup(response.text, "html.parser")
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
                    "source_bucket": "direct_telegram_researched",
                })
        except Exception as exc:
            print(f"DIRECT_EXCEPTION Telegram @{channel} {exc}")
    return items


def direct_discovery():
    all_items = []
    counts = {}

    reddit = reddit_direct()
    all_items.extend(reddit)
    counts["Reddit direct"] = len(reddit)

    for source in DIRECT_INDEX_SOURCES:
        found = scrape_index_source(source)
        all_items.extend(found)
        counts[source["name"]] = len(found)

    topics = direct_topics()
    all_items.extend(topics)
    counts["Fixed researched topics"] = len(topics)

    telegram = telegram_public_channels()
    all_items.extend(telegram)
    counts["Telegram public"] = len(telegram)

    print("DIRECT_COUNTS", json.dumps(counts, ensure_ascii=False))
    return all_items, counts


def exa_gapfill():
    if EXA_FALLBACK_CALLS <= 0:
        return [], 0
    researched_reddit = " ".join(f"r/{x}" for x in REDDIT_SUBREDDITS)
    queries = [
        f"past 7 days real person first-person property buyer or Golden Visa discussion; prioritize Reddit {researched_reddit}; North Cyprus Turkey Montenegro Greece Portugal Spain Italy Cyprus UK Germany France Netherlands Belgium Austria Poland Czechia; budget deposit mortgage viewing offer relocation; exclude listings agents developers guides news",
        "past 7 days Russian or Kazakh person wants to buy property abroad: хочу купить ищу квартиру ищу дом недвижимость за рубежом бюджет ипотека взнос просмотр переезд ВНЖ; Северный Кипр Черногория Greece Turkey Portugal Spain Italy Germany France; exclude ads agents developers",
    ]
    items = []
    calls = 0
    for query in queries[:EXA_FALLBACK_CALLS]:
        calls += 1
        print(f"EXA_FALLBACK [{calls}/{EXA_FALLBACK_CALLS}]")
        for item in world_engine.exa_search(query, EXA_GAPFILL_DOMAINS):
            item["source_bucket"] = "exa_gapfill_researched"
            items.append(item)
    return items, calls


def run():
    started = main.now_utc()
    cutoff = started - timedelta(hours=main.LOOKBACK_HOURS)
    stats = {}
    direct_items, direct_counts = direct_discovery()
    exa_items, exa_calls = exa_gapfill()
    seen = set()
    leads = []

    for item in direct_items + exa_items:
        key = main.dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        published = world_engine.resolved_published(item)
        item["verified_published"] = published.isoformat() if published else ""
        keep, reason = main.keep_candidate(item, cutoff)
        if not keep:
            stats[reason] = stats.get(reason, 0) + 1
            continue
        market = item.get("forced_market") or main.market_for(main.text_of(item), item.get("source_bucket", ""), item.get("url", ""), item.get("title", ""))
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
            "scanned_at": started.isoformat(),
            "source_domain": main.domain_of(item.get("url", "")),
        })
        leads.append(item)

    leads = list({main.dedupe_key(x): x for x in leads}.values())
    leads.sort(key=lambda x: (x["classification"] == "HOT", x["intent_score"], x["credibility_score"], x["market_fit_score"]), reverse=True)

    db = main.firestore_client()
    scan_id = started.strftime("%Y%m%d%H%M%S")
    if db:
        ref = db.collection(main.SCAN_LOG_COLLECTION).document(scan_id)
        batch = db.batch()
        for lead in leads[:100]:
            docid = hashlib.sha1((lead.get("url") or lead.get("title", "")).encode()).hexdigest()
            batch.set(ref.collection("leads").document(docid), lead, merge=True)
        batch.set(ref, {
            "engine": "hybrid_researched_sources_v2",
            "started_at": started.isoformat(),
            "finished_at": main.now_utc().isoformat(),
            "direct_counts": direct_counts,
            "exa_calls": exa_calls,
            "unique_candidates": len(seen),
            "hot_warm": len(leads),
            "filter_stats": stats,
        }, merge=True)
        batch.commit()

    print(f"SCAN_COMPLETE engine=hybrid_researched_sources_v2 candidates={len(seen)} hot_warm={len(leads)} exa_calls={exa_calls}")
    print("FILTER_STATS", json.dumps(stats, ensure_ascii=False))

    if leads:
        lines = [f"BAY-S WORLD RADAR | {len(leads)} HOT/WARM | Aday: {len(seen)} | Exa: {exa_calls}"]
        for lead in leads[:10]:
            lines.append(f"{lead['classification']} | {lead['market']} | {lead.get('source','')} | I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']} | {lead.get('title','')[:100]} | {lead.get('url','')}")
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(
            f"BAY-S WORLD RADAR tamamlandı.\nYeni HOT/WARM lead yok.\nİncelenen aday: {len(seen)}\nDoğrudan kaynaklar: {sum(direct_counts.values())}\nExa çağrısı: {exa_calls}\nTarama: son {main.LOOKBACK_HOURS} saat"
        )


if __name__ == "__main__":
    run()
