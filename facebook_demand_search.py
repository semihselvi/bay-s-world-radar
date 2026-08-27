from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from playwright.sync_api import sync_playwright

import facebook_group_scanner as base
import facebook_radar_v2 as v2
from facebook_intent_adapter import classify_facebook_intent
from north_cyprus_intent_classifier import classify_intent as core_classify_intent


OUTPUT_PATH = base.ROOT / "facebook_demand_leads_latest.json"
DEBUG_PATH = base.ROOT / "facebook_demand_posts_debug_latest.json"
SEEN_PATH = base.STATE_DIR / "facebook_demand_seen.json"

SEARCH_QUERIES = [
    "looking for",
    "need apartment",
    "arıyorum",
    "ищу",
]


def _load_seen() -> dict[str, float]:
    try:
        data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in data.items()}
    except Exception:
        return {}


def _save_seen(seen: dict[str, float]) -> None:
    base.STATE_DIR.mkdir(parents=True, exist_ok=True)
    compact = dict(sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:5000])
    SEEN_PATH.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")


def _group_search_url(group_url: str, query: str) -> str:
    canonical = base._canonical_group_url(group_url)
    return f"{canonical}search/?q={quote(query)}"


def _classify(post: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    item = {
        "text": post.get("text", ""),
        "title": f"{post.get('group', '')} | North Cyprus Facebook group",
        "author": post.get("author", ""),
        "source": "Facebook",
        "url": post.get("url", ""),
    }
    intent = classify_facebook_intent(item, core_classify_intent)
    intent_class = str(intent.get("intent_class") or "UNKNOWN")
    confidence = int(intent.get("intent_confidence") or 0)
    if intent_class not in {"BUYER", "TENANT"} or confidence < 70:
        return intent, None

    credibility = base._credibility_score(intent, post)
    label = "HOT" if confidence >= 85 and credibility >= 70 else "WARM"
    lead = dict(post)
    lead.update(intent)
    lead.update(
        {
            "classification": label,
            "intent_score": confidence,
            "credibility_score": credibility,
            "market_fit_score": 95,
            "display_intent": base.display_intent(intent),
        }
    )
    return intent, lead


def _scan_search(page, group: dict[str, Any], query: str, max_posts: int = 15) -> list[dict[str, Any]]:
    url = _group_search_url(str(group.get("url") or ""), query)
    print(f"  Search: {query}")
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as exc:
        print(f"    navigation warning: {type(exc).__name__}")
    page.wait_for_timeout(3200)

    try:
        text = base._clean_text(page.locator("body").inner_text(timeout=2500)).casefold()
    except Exception:
        text = ""
    unavailable = (
        "this content isn't available",
        "bu içeriğe şu anda ulaşılamıyor",
        "content isn't available right now",
    )
    if any(x in text for x in unavailable):
        print("    inaccessible")
        return []

    collected: dict[str, dict[str, Any]] = {}
    for round_no in range(3):
        batch = v2._collect_posts_v2(page, group, max_posts)
        for post in batch:
            post = dict(post)
            post["search_query"] = query
            key = post.get("url") or hashlib.sha1(post.get("text", "").encode("utf-8", "ignore")).hexdigest()
            collected[key] = post
            if len(collected) >= max_posts:
                break
        print(f"    round {round_no + 1}/3 - candidates: {len(batch)} - unique posts: {len(collected)}")
        if len(collected) >= max_posts:
            break
        page.mouse.wheel(0, 2800)
        page.wait_for_timeout(1800)
    return list(collected.values())[:max_posts]


def main() -> int:
    config = base.load_config()
    groups = [g for g in config.get("groups", []) if g.get("enabled", True) and g.get("demand_search", False)]
    if not groups:
        print("No groups have demand_search=true in facebook_groups.json")
        return 0

    settings = config.get("settings", {})
    max_age = float(settings.get("max_age_hours", 72))
    debug_rows: list[dict[str, Any]] = []
    leads_by_key: dict[str, dict[str, Any]] = {}
    seen = _load_seen()
    now = time.time()

    with sync_playwright() as playwright:
        context = base._launch_context(playwright, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            base.ensure_facebook_login(page)

            print(f"Targeted demand search | groups={len(groups)} | queries={len(SEARCH_QUERIES)}")
            for group in groups:
                print(f"\nSearching group: {group.get('name','Facebook Group')}")
                group_posts: dict[str, dict[str, Any]] = {}
                for query in SEARCH_QUERIES:
                    for post in _scan_search(page, group, query):
                        key = post.get("url") or hashlib.sha1(post.get("text", "").encode("utf-8", "ignore")).hexdigest()
                        group_posts[key] = post

                print(f"  Unique search-result posts: {len(group_posts)}")
                for post in group_posts.values():
                    intent, lead = _classify(post)
                    row = dict(post)
                    row["debug_intent"] = intent.get("intent_class") or "UNKNOWN"
                    row["debug_confidence"] = int(intent.get("intent_confidence") or 0)
                    row["debug_requirements"] = intent.get("requirements") or {}
                    debug_rows.append(row)

                    age = post.get("age_hours")
                    if age is not None and age > max_age:
                        continue
                    if lead is None:
                        continue
                    lead_key = base._post_key(lead)
                    if lead_key in seen:
                        continue
                    leads_by_key[lead_key] = lead

        finally:
            context.close()

    leads = list(leads_by_key.values())
    leads.sort(
        key=lambda x: (
            x.get("classification") == "HOT",
            int(x.get("intent_score") or 0),
            int(x.get("credibility_score") or 0),
        ),
        reverse=True,
    )

    for lead in leads:
        seen[base._post_key(lead)] = now
    _save_seen(seen)

    OUTPUT_PATH.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_PATH.write_text(json.dumps(debug_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for row in debug_rows:
        label = str(row.get("debug_intent") or "UNKNOWN")
        counts[label] = counts.get(label, 0) + 1

    print("\n" + "=" * 72)
    print(f"BAY-S FACEBOOK DEMAND SEARCH COMPLETE | New HOT/WARM: {len(leads)}")
    print(f"Latest output: {OUTPUT_PATH}")
    print(f"Debug output: {DEBUG_PATH}")
    print("Intent summary: " + " | ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)))

    for lead in leads[:10]:
        print("")
        print(
            f"{lead['classification']} | {lead.get('display_intent','')} | "
            f"I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)} F{lead.get('market_fit_score',0)}"
        )
        print(f"Group: {lead.get('group','')} | Query: {lead.get('search_query','')}")
        print(base._clean_text(lead.get("text"))[:600])
        print(lead.get("url", ""))

    if settings.get("notify_telegram", True) and leads:
        base.notify_telegram(leads)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nFACEBOOK_DEMAND_SEARCH_ERROR: {exc}")
        raise SystemExit(1)
