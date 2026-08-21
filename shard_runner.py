import os
import json
import hashlib
from datetime import timedelta, datetime, timezone

import main
import world_engine
import hybrid_engine
import source_crawler_v2
from telegram_member_reader import collect_member_telegram
from source_registry import DIRECT_INDEX_SOURCES, DIRECT_TOPIC_SOURCES, REDDIT_SUBREDDITS

SHARD = os.getenv("WORLD_RADAR_SHARD", "telegram_member").strip().lower()

SHARDS = {
    "north_cyprus_cis": {
        "index_names": {
            "Expat.com Turkey",
            "Forum AWD Overseas Property",
            "Forum-EU",
        },
        "topic_names": set(),
        "telegram": {
            "cyprusy", "velesproperty", "btinvestnorthcyprus", "sadeceemlakoto",
            "prian_property", "hayatestate_online", "astonspassport",
        },
        "catalogs": {"TeleGid Cyprus"},
        "member": False,
        "exa_calls": 0,
        "exa_query": "",
        "exa_domains": [],
        "reddit_focus": [],
    },
    "golden_south": {
        "index_names": {
            "Expat.com Greece", "Expat.com Portugal", "Expat.com Spain",
            "Expat.com Italy", "Expat.com Cyprus", "Expat.com Montenegro",
        },
        "topic_names": set(),
        "telegram": {"VillaEdelweissMontenegro", "Montenegrosupreme", "indemochat"},
        "catalogs": {"TeleGid Montenegro", "MontenegroExpats Communities"},
        "member": False,
        "exa_calls": 1,
        "exa_query": (
            "past 7 days real person first-person Golden Visa, residency-by-investment, "
            "relocation with purchase intent, or actual property purchase discussion in "
            "Greece Portugal Spain Italy Montenegro Cyprus or North Cyprus; wants to buy "
            "house apartment flat villa or investment property; budget deposit mortgage "
            "lawyer viewing offer payment timing; exclude listings agents developers guides news"
        ),
        "exa_domains": [
            "reddit.com", "expatforum.com", "facebook.com", "internations.org",
            "meetup.com", "telegid.me", "tlgrm.ru", "forum.finanzaonline.com", "propit.it",
        ],
        "reddit_focus": [
            "goldenvisa", "ExpatFIRE", "CitizenshipInvestment", "PortugalExpats",
            "ItalyExpat", "montenegro", "cyprus", "greece", "askspain",
        ],
    },
    "west_europe": {
        "index_names": {
            "MoneySavingExpert", "Expat.com Germany", "Expat.com France",
            "Expat.com Netherlands", "Expat.com Belgium", "Investisseurs Heureux",
            "Finary Immobilier", "PIM.be",
        },
        "topic_names": set(),
        "telegram": set(),
        "catalogs": set(),
        "member": False,
        "exa_calls": 1,
        "exa_query": (
            "past 7 days real person first-person discussion about buying property abroad, "
            "investment property, second home or relocation with purchase intent from or in "
            "UK Germany France Netherlands Belgium; budget deposit mortgage viewing offer "
            "target area property type; Europe only; exclude US Australia property markets, "
            "listings agents developers guides news"
        ),
        "exa_domains": [
            "reddit.com", "expatforum.com", "auswandererforum.de", "wiwi-treff.de",
            "tweakers.net", "wertpapier-forum.de", "forum.allesamerika.com", "investeerders.nl",
        ],
        "reddit_focus": ["expats", "AmerExit", "beleggen", "germany", "eupersonalfinance", "ExpatFIRE"],
    },
    "central_europe": {
        "index_names": {
            "Expat.com Austria", "Expat.com Switzerland", "Expat.com Poland",
            "Expat.com Czech Republic", "Expat.com Lithuania",
        },
        "topic_names": set(),
        "telegram": set(),
        "catalogs": set(),
        "member": False,
        "exa_calls": 0,
        "exa_query": "",
        "exa_domains": [],
        "reddit_focus": [],
    },
    "telegram_member": {
        "index_names": set(),
        "topic_names": set(),
        "telegram": set(),
        "catalogs": set(),
        "member": True,
        "exa_calls": 0,
        "exa_query": "",
        "exa_domains": [],
        "reddit_focus": [],
    },
}


def public_telegram_selected(channels):
    items = []
    for channel in sorted(set(channels)):
        try:
            response = main.SESSION.get(f"https://t.me/s/{channel}", timeout=20)
            if response.status_code != 200:
                print(f"DIRECT_ERROR Telegram {response.status_code} @{channel}")
                continue
            from bs4 import BeautifulSoup
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
                    "text": hybrid_engine.clean_text(body.get_text(" ", strip=True)),
                    "published": time_node.get("datetime", "") if time_node else "",
                    "author": f"@{channel}",
                    "source_bucket": f"shard_{SHARD}_telegram",
                })
        except Exception as exc:
            print(f"DIRECT_EXCEPTION Telegram @{channel} {exc}")
    return items


def collect_direct(spec):
    items = []
    counts = {}

    for source in DIRECT_INDEX_SOURCES:
        if source["name"] not in spec["index_names"]:
            continue
        found = source_crawler_v2.scrape_index_source(source)
        items.extend(found)
        counts[source["name"]] = len(found)

    for source in DIRECT_TOPIC_SOURCES:
        if source["name"] not in spec["topic_names"]:
            continue
        item = source_crawler_v2.extract_page_item(
            source["url"], source["name"], "", f"shard_{SHARD}_topic", source.get("market", "")
        )
        if item:
            items.append(item)
            counts[source["name"]] = 1
        else:
            counts[source["name"]] = 0

    discovered_channels = source_crawler_v2.discover_public_telegram_channels(spec.get("catalogs", set()))
    all_channels = set(spec["telegram"]) | set(discovered_channels)
    tg = public_telegram_selected(all_channels)
    items.extend(tg)
    counts["Telegram Public"] = len(tg)
    counts["Telegram Catalog Channels"] = len(discovered_channels)

    if spec["member"]:
        member = collect_member_telegram()
        items.extend(member)
        counts["Telegram Member"] = len(member)

    print("SHARD_DIRECT_COUNTS", SHARD, json.dumps(counts, ensure_ascii=False))
    return items, counts


def collect_exa(spec):
    override = os.getenv("WORLD_SHARD_EXA_CALLS", "").strip()
    calls = int(override) if override else int(spec["exa_calls"])
    calls = max(0, min(calls, 1))
    if not calls or not spec["exa_query"]:
        return [], 0

    reddit_focus = spec.get("reddit_focus", [])
    reddit_hint = ""
    if reddit_focus:
        allowed = [x for x in reddit_focus if x in REDDIT_SUBREDDITS]
        if allowed:
            reddit_hint = " Prioritize discussions in Reddit communities: " + ", ".join(f"r/{x}" for x in allowed) + "."

    query = spec["exa_query"] + reddit_hint
    print(f"EXA_SHARD [{SHARD}] call=1")
    items = world_engine.exa_search(query, spec["exa_domains"])
    for item in items:
        item["source_bucket"] = f"shard_{SHARD}_exa"
    return items, 1


def already_notified(db, lead_key, hours=72):
    if not db:
        return False
    try:
        snap = db.collection("bay_s_notified_leads").document(lead_key).get()
        if not snap.exists:
            return False
        data = snap.to_dict() or {}
        raw = data.get("notified_at", "")
        if not raw:
            return True
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt >= main.now_utc() - timedelta(hours=hours)
    except Exception as exc:
        print("NOTIFIED_CHECK_ERROR", exc)
        return False


def mark_notified(db, lead_key, lead):
    if not db:
        return
    try:
        db.collection("bay_s_notified_leads").document(lead_key).set({
            "notified_at": main.now_utc().isoformat(),
            "url": lead.get("url", ""),
            "title": lead.get("title", ""),
            "classification": lead.get("classification", ""),
            "shard": SHARD,
        }, merge=True)
    except Exception as exc:
        print("NOTIFIED_MARK_ERROR", exc)


def run():
    if SHARD not in SHARDS:
        raise SystemExit(f"Unknown WORLD_RADAR_SHARD={SHARD}")

    spec = SHARDS[SHARD]
    started = main.now_utc()
    cutoff = started - timedelta(hours=main.LOOKBACK_HOURS)
    stats = {}
    direct_items, direct_counts = collect_direct(spec)
    exa_items, exa_calls = collect_exa(spec)
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

        market = item.get("forced_market") or main.market_for(
            main.text_of(item), item.get("source_bucket", ""), item.get("url", ""), item.get("title", "")
        )
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
            "radar_shard": SHARD,
        })
        leads.append(item)

    leads = list({main.dedupe_key(x): x for x in leads}.values())
    leads.sort(
        key=lambda x: (x["classification"] == "HOT", x["intent_score"], x["credibility_score"], x["market_fit_score"]),
        reverse=True,
    )

    db = main.firestore_client()
    scan_id = f"{started.strftime('%Y%m%d%H%M%S')}_{SHARD}"
    if db:
        ref = db.collection(main.SCAN_LOG_COLLECTION).document(scan_id)
        batch = db.batch()
        for lead in leads[:100]:
            docid = hashlib.sha1((lead.get("url") or lead.get("title", "")).encode()).hexdigest()
            batch.set(ref.collection("leads").document(docid), lead, merge=True)
        batch.set(ref, {
            "engine": "world_radar_sharded_v2_expanded",
            "shard": SHARD,
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

    new_leads = []
    for lead in leads:
        lead_key = main.dedupe_key(lead)
        if already_notified(db, lead_key):
            print("DUPLICATE_NOTIFICATION_SKIPPED", lead.get("url", ""))
            continue
        new_leads.append(lead)
        mark_notified(db, lead_key, lead)

    print(
        f"SHARD_COMPLETE shard={SHARD} candidates={len(seen)} hot_warm={len(leads)} "
        f"new_to_notify={len(new_leads)} exa_calls={exa_calls}"
    )
    print("FILTER_STATS", json.dumps(stats, ensure_ascii=False))

    if new_leads:
        lines = [
            f"BAY-S WORLD RADAR [{SHARD}] | {len(new_leads)} YENİ HOT/WARM | "
            f"Aday: {len(seen)} | Exa: {exa_calls}"
        ]
        for lead in new_leads[:10]:
            lines.append(
                f"{lead['classification']} | {lead['market']} | {lead.get('source','')} | "
                f"I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']} | "
                f"{lead.get('title','')[:100]} | {lead.get('url','')}"
            )
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(
            f"BAY-S WORLD RADAR [{SHARD}] tamamlandı.\n"
            f"Yeni HOT/WARM lead yok.\n"
            f"İncelenen aday: {len(seen)}\n"
            f"Exa çağrısı: {exa_calls}\n"
            f"Tarama: son {main.LOOKBACK_HOURS} saat"
        )


if __name__ == "__main__":
    run()
