from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

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

PHONE_RE = re.compile(r"(?<!\d)(?:\+?90\s*)?0?5\d(?:[\s().-]*\d){8}(?!\d)")
ROOM_RE = re.compile(r"\b[0-6]\s*\+\s*[0-3]\b")


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


def _group_segment(group_url: str) -> str:
    match = re.search(r"/groups/([^/?#]+)/?", group_url or "", re.I)
    return match.group(1) if match else ""


def _canonical_direct_post_url(url: str, group_url: str) -> str:
    """Convert Facebook post/search link variants into a stable direct group-post URL."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        if "facebook.com" not in parts.netloc.casefold():
            return ""
        group_id = _group_segment(group_url)
        path = parts.path
        query = parse_qs(parts.query)

        post_match = re.search(r"/groups/([^/?#]+)/(?:posts|permalink)/(\d+)", path, re.I)
        if post_match:
            return f"https://www.facebook.com/groups/{post_match.group(1)}/posts/{post_match.group(2)}/"

        multi = (query.get("multi_permalinks") or [""])[0]
        if group_id and multi and str(multi).isdigit():
            return f"https://www.facebook.com/groups/{group_id}/posts/{multi}/"

        story = (query.get("story_fbid") or [""])[0]
        if group_id and story and str(story).isdigit():
            return f"https://www.facebook.com/groups/{group_id}/posts/{story}/"

        return ""
    except Exception:
        return ""


def _effective_post_key(post: dict[str, Any]) -> str:
    """Never dedupe multiple posts just because Facebook gave us the group homepage as fallback."""
    group_url = base._canonical_group_url(str(post.get("group_url") or ""))
    direct = _canonical_direct_post_url(str(post.get("url") or ""), group_url)
    if direct:
        basis = direct
    else:
        basis = f"{group_url}|{base._clean_text(post.get('text'))[:1600]}"
    return hashlib.sha256(basis.encode("utf-8", "ignore")).hexdigest()


def _extract_phone(text: str) -> str:
    match = PHONE_RE.search(text or "")
    return base._clean_text(match.group(0)) if match else ""


def _resolve_post_permalink(page, post: dict[str, Any], group: dict[str, Any]) -> str:
    """Locate the visible search-result card matching the post text and recover its direct permalink."""
    group_url = base._canonical_group_url(str(group.get("url") or ""))
    current = _canonical_direct_post_url(str(post.get("url") or ""), group_url)
    if current:
        return current

    needle = base._clean_text(post.get("text"))
    if not needle:
        return ""
    # A short visible prefix is enough to match truncated Facebook search results.
    needle = needle[:180]

    try:
        hrefs = page.evaluate(
            """({needle}) => {
                const norm = (s) => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
                const target = norm(needle);
                if (!target) return [];
                const msgSel = '[data-ad-rendering-role="story_message"], [data-ad-preview="message"], [data-ad-comet-preview="message"]';
                const postLinkSel = 'a[href*="/groups/"][href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid="], a[href*="multi_permalinks="]';
                const out = [];

                for (const msg of document.querySelectorAll(msgSel)) {
                    const txt = norm(msg.innerText || '');
                    const prefix = target.slice(0, Math.min(90, target.length));
                    if (!(txt.includes(prefix) || target.includes(txt.slice(0, Math.min(90, txt.length))))) continue;

                    let container = msg.closest('div[role="article"]');
                    if (!container) container = msg.parentElement;
                    let el = container;
                    for (let i = 0; i < 8 && el; i++, el = el.parentElement) {
                        if (el.querySelectorAll) {
                            for (const a of el.querySelectorAll(postLinkSel)) {
                                if (a.href) out.push(a.href);
                            }
                        }
                        if (out.length) break;
                    }
                    if (out.length) break;
                }
                return [...new Set(out)].slice(0, 20);
            }""",
            {"needle": needle},
        )
    except Exception:
        hrefs = []

    for href in hrefs or []:
        direct = _canonical_direct_post_url(str(href), group_url)
        if direct:
            return direct
    return ""


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
    text = base._clean_text(post.get("text"))
    req = intent.get("requirements") or {}
    phone = _extract_phone(text)
    has_specific_requirement = bool(
        req.get("regions")
        or req.get("property_type")
        or req.get("budget")
        or req.get("move_window")
        or ROOM_RE.search(text)
    )

    # Operational HOT: a clear buyer/tenant demand with direct contact info and at
    # least one concrete housing criterion deserves immediate attention, even when
    # the linguistic classifier confidence is below the generic 85 threshold.
    operational_hot = bool(phone and has_specific_requirement and confidence >= 78 and credibility >= 65)
    label = "HOT" if operational_hot or (confidence >= 85 and credibility >= 70) else "WARM"

    lead = dict(post)
    lead.update(intent)
    lead.update(
        {
            "classification": label,
            "intent_score": confidence,
            "credibility_score": credibility,
            "market_fit_score": 95,
            "display_intent": base.display_intent(intent),
            "contact_phone": phone,
            "operational_hot": operational_hot,
        }
    )
    return intent, lead


def _scan_search(page, group: dict[str, Any], query: str, max_posts: int = 15) -> list[dict[str, Any]]:
    search_url = _group_search_url(str(group.get("url") or ""), query)
    print(f"  Search: {query}")
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
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
        for raw_post in batch:
            post = dict(raw_post)
            post["search_query"] = query
            post["search_url"] = search_url

            direct = _resolve_post_permalink(page, post, group)
            if direct:
                post["url"] = direct
                post["link_quality"] = "DIRECT"
            else:
                post["link_quality"] = "SEARCH_FALLBACK"

            key = _effective_post_key(post)
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
                        group_posts[_effective_post_key(post)] = post

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
                    lead_key = _effective_post_key(lead)
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
        seen[_effective_post_key(lead)] = now
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
        print(f"Group: {lead.get('group','')} | Query: {lead.get('search_query','')} | Link: {lead.get('link_quality','')}")
        if lead.get("contact_phone"):
            print(f"Phone: {lead.get('contact_phone')}")
        print(base._clean_text(lead.get("text"))[:600])
        direct = _canonical_direct_post_url(str(lead.get("url") or ""), str(lead.get("group_url") or ""))
        print(direct or lead.get("search_url") or lead.get("url", ""))

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
