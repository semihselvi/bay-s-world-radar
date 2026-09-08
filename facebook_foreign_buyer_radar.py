from __future__ import annotations

import json
import os
import random
import re
import time
from typing import Any

import requests
from playwright.sync_api import sync_playwright

import facebook_demand_search as demand
import facebook_group_scanner as base
import facebook_radar_v2 as v2
from facebook_graphql_link_resolver import resolve_from_graphql_payloads
from facebook_post_link_resolver import canonical_direct
from facebook_post_menu_resolver import _is_actionable_facebook_link


OUTPUT_PATH = base.ROOT / "facebook_foreign_buyer_leads_latest.json"
DEBUG_PATH = base.ROOT / "facebook_foreign_buyer_debug_latest.json"
SEEN_PATH = base.STATE_DIR / "facebook_foreign_buyer_seen.json"

# Intentionally small query set. One precise query per priority language keeps
# Facebook traffic low while targeting explicit purchase intent.
QUERY_SPECS = [
    {"query": "looking to buy", "language": "EN"},
    {"query": "купить недвижимость", "language": "RU"},
    {"query": "Immobilie kaufen", "language": "DE"},
]

CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
GERMAN_RE = re.compile(
    r"\b(?:immobilie|immobilien|wohnung|wohnungen|kaufen|erwerben|möchte|moechte|nordzypern|haus|häuser|haeuser)\b",
    re.I,
)
TURKISH_RE = re.compile(
    r"\b(?:satılık|satilik|alıcıyım|aliciyim|arıyorum|ariyorum|daire|kıbrıs|kibris|mağusa|magusa|girne|lefkoşa|lefkosa)\b",
    re.I,
)
ENGLISH_RE = re.compile(
    r"\b(?:looking|buy|purchase|property|apartment|flat|villa|house|budget|cash|north\s+cyprus|kyrenia|famagusta|iskele)\b",
    re.I,
)

BUDGET_RE = re.compile(
    r"(?:[£€$]\s?\d[\d,.]*(?:\s?[kK])?|\b\d[\d,.]*(?:\s?[kK])?\s?(?:GBP|EUR|USD|pounds?|euros?)\b)",
    re.I,
)
ROOM_RE = re.compile(r"\b[0-6]\s*\+\s*[0-3]\b|\b(?:studio|one|two|three|1|2|3)[-\s]?(?:bed|bedroom)s?\b", re.I)
REGION_RE = re.compile(
    r"\b(?:iskele|İskele|long\s+beach|famagusta|gazimağusa|gazimagusa|kyrenia|girne|nicosia|lefkoşa|lefkosa|"
    r"tatlısu|tatlisu|esentepe|alsancak|lapta|karşıyaka|karsiyaka|bahçeli|bahceli|bafra|yeniboğaziçi|yenibogazici)\b",
    re.I,
)
TIMING_RE = re.compile(
    r"\b(?:ready\s+to\s+buy|cash\s+buyer|this\s+month|next\s+month|soon|now|visiting|coming\s+to|"
    r"готов\w*\s+купить|в\s+этом\s+месяце|в\s+следующем\s+месяце|скоро|"
    r"sofort|diesen\s+monat|nächsten\s+monat|naechsten\s+monat|bald|barzahler|barzahlerin)\b",
    re.I,
)


def _load_seen() -> dict[str, float]:
    try:
        data = json.loads(SEEN_PATH.read_text(encoding="utf-8"))
        return {str(k): float(v) for k, v in data.items()}
    except Exception:
        return {}


def _save_seen(seen: dict[str, float]) -> None:
    base.STATE_DIR.mkdir(parents=True, exist_ok=True)
    compact = dict(sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:4000])
    SEEN_PATH.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")


def _language(text: str, query_language: str = "") -> str:
    value = base._clean_text(text)
    if CYRILLIC_RE.search(value):
        return "RU"
    if GERMAN_RE.search(value):
        return "DE"
    # Explicitly avoid treating Turkish-language demand as a foreign-buyer lead.
    if TURKISH_RE.search(value):
        return "TR"
    if ENGLISH_RE.search(value):
        return "EN"
    return query_language or "UNKNOWN"


def _specifics(text: str) -> dict[str, Any]:
    clean = base._clean_text(text)
    budget_match = BUDGET_RE.search(clean)
    region_match = REGION_RE.search(clean)
    return {
        "budget": budget_match.group(0) if budget_match else "",
        "region": region_match.group(0) if region_match else "",
        "has_room": bool(ROOM_RE.search(clean)),
        "has_timing": bool(TIMING_RE.search(clean)),
    }


def _capture_graphql(page, payloads: list[str], byte_state: dict[str, int]):
    def on_response(response):
        try:
            url = str(response.url or "").casefold()
            if "facebook.com" not in url or "graphql" not in url:
                return
            if len(payloads) >= 35 or byte_state["bytes"] >= 10 * 1024 * 1024:
                return
            body = response.text()
            if not body:
                return
            size = len(body.encode("utf-8", "ignore"))
            if byte_state["bytes"] + size > 10 * 1024 * 1024:
                return
            payloads.append(body)
            byte_state["bytes"] += size
        except Exception:
            return
    return on_response


def _scan_low_impact(page, group: dict[str, Any], spec: dict[str, str], max_posts: int = 8) -> list[dict[str, Any]]:
    query = spec["query"]
    query_language = spec["language"]
    search_url = demand._group_search_url(str(group.get("url") or ""), query)
    group_url = base._canonical_group_url(str(group.get("url") or ""))
    print(f"  Search [{query_language}]: {query}")

    payloads: list[str] = []
    byte_state = {"bytes": 0}
    listener = _capture_graphql(page, payloads, byte_state)
    page.on("response", listener)
    collected: dict[str, dict[str, Any]] = {}

    try:
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            print(f"    navigation warning: {type(exc).__name__}")
        page.wait_for_timeout(random.randint(3800, 5200))

        # Two rounds only. No three-dot menus, no comments, no DMs, no post clicks.
        for round_no in range(2):
            batch = v2._collect_posts_v2(page, group, max_posts)
            for raw in batch:
                post = dict(raw)
                post["search_query"] = query
                post["query_language"] = query_language
                post["search_url"] = search_url
                direct = demand._resolve_post_permalink(page, post, group)
                if direct:
                    post["url"] = direct
                    post["link_quality"] = "DIRECT"
                    post["link_source"] = "DOM"
                else:
                    post["url"] = search_url
                    post["link_quality"] = "SEARCH_FALLBACK"
                collected[demand._effective_post_key(post)] = post
                if len(collected) >= max_posts:
                    break
            print(f"    round {round_no + 1}/2 - candidates: {len(batch)} - unique: {len(collected)}")
            if len(collected) >= max_posts or round_no == 1:
                break
            page.mouse.wheel(0, random.randint(1800, 2400))
            page.wait_for_timeout(random.randint(2800, 4300))
    finally:
        try:
            page.remove_listener("response", listener)
        except Exception:
            pass

    posts = list(collected.values())[:max_posts]
    if payloads:
        resolved = 0
        for post in posts:
            if canonical_direct(str(post.get("url") or ""), group_url):
                continue
            direct = resolve_from_graphql_payloads(str(post.get("text") or ""), group_url, payloads)
            if direct:
                post["url"] = direct
                post["link_quality"] = "DIRECT"
                post["link_source"] = "GRAPHQL"
                resolved += 1
        print(f"    GraphQL direct links: {resolved}/{len(posts)}")
    return posts


def _classify_foreign_buyer(post: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    intent, generic_lead = demand._classify(post)
    intent_class = str(intent.get("intent_class") or "UNKNOWN")
    if intent_class != "BUYER" or generic_lead is None:
        return intent, None

    language = _language(str(post.get("text") or ""), str(post.get("query_language") or ""))
    if language not in {"EN", "RU", "DE"}:
        return intent, None

    lead = dict(generic_lead)
    details = _specifics(str(post.get("text") or ""))
    lead["language"] = language
    lead["buyer_budget"] = details["budget"]
    lead["buyer_region"] = details["region"]
    lead["buyer_has_room"] = details["has_room"]
    lead["buyer_has_timing"] = details["has_timing"]

    specificity = sum([
        bool(details["budget"]),
        bool(details["region"]),
        bool(details["has_room"]),
        bool(details["has_timing"]),
    ])
    confidence = int(lead.get("intent_score") or 0)
    credibility = int(lead.get("credibility_score") or 0)
    age = lead.get("age_hours")

    # Unknown-age results are never promoted to HOT; Facebook group search can
    # surface stale posts. They remain WARM until freshness is verified.
    is_hot = bool(
        isinstance(age, (int, float))
        and confidence >= 80
        and credibility >= 65
        and specificity >= 2
    )
    lead["classification"] = "HOT" if is_hot else "WARM"
    lead["foreign_buyer_specificity"] = specificity
    return intent, lead


def _exact_link(lead: dict[str, Any]) -> str:
    group_url = str(lead.get("group_url") or "")
    url = str(lead.get("url") or "")
    direct = canonical_direct(url, group_url)
    if direct:
        return direct
    return url if _is_actionable_facebook_link(url, group_url) else ""


def _notify(leads: list[dict[str, Any]]) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_DISABLED")
        return

    sent = 0
    for lead in leads[:10]:
        text = base._clean_text(lead.get("text"))
        if len(text) > 1000:
            text = text[:997] + "..."
        exact = _exact_link(lead)
        age = lead.get("age_hours")
        age_text = f"{age:.1f}h" if isinstance(age, (int, float)) else "UNKNOWN"
        lines = [
            f"🌍 BAY-S FOREIGN BUYER | {lead.get('classification','WARM')}",
            f"Dil: {lead.get('language','')} | Intent: BUYER | I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)} F{lead.get('market_fit_score',0)}",
            f"Grup: {lead.get('group','')}",
            f"Yaş: {age_text}",
        ]
        if lead.get("buyer_region"):
            lines.append(f"Bölge: {lead.get('buyer_region')}")
        if lead.get("buyer_budget"):
            lines.append(f"Bütçe: {lead.get('buyer_budget')}")
        if lead.get("contact_phone"):
            lines.append(f"Telefon: {lead.get('contact_phone')}")
        lines.extend(["", text, ""])
        if exact:
            lines.extend(["Facebook post:", exact])
        else:
            lines.extend(["Facebook post: DIRECT LINK YAKALANAMADI", str(lead.get("search_url") or "")])

        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": "\n".join(lines)[:3900], "disable_web_page_preview": True},
            timeout=20,
        )
        if response.status_code == 200:
            sent += 1
        else:
            print("TELEGRAM_ERROR", response.status_code, response.text[:180])
    print(f"TELEGRAM_SENT: {sent} foreign buyer lead(s)")


def main() -> int:
    config = base.load_config()
    groups = [
        g for g in config.get("groups", [])
        if g.get("enabled", True) and g.get("foreign_buyer_search", False)
    ]
    if not groups:
        print("No groups have foreign_buyer_search=true")
        return 0

    settings = config.get("settings", {})
    max_age = float(settings.get("max_age_hours", 72))
    retest = os.getenv("FACEBOOK_FOREIGN_BUYER_RETEST", "").strip() == "1"
    if retest:
        groups = groups[:1]
        query_specs = QUERY_SPECS[:1]
        print("SAFE RETEST: 1 group x 1 query | Telegram disabled | no menu/post clicks")
    else:
        query_specs = QUERY_SPECS
        print(f"FOREIGN BUYER RADAR: {len(groups)} groups x {len(query_specs)} language queries")

    seen = {} if retest else _load_seen()
    now = time.time()
    debug_rows: list[dict[str, Any]] = []
    leads_by_key: dict[str, dict[str, Any]] = {}

    with sync_playwright() as playwright:
        context = base._launch_context(playwright, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            base.ensure_facebook_login(page)
            for group in groups:
                print(f"\nSearching foreign buyers: {group.get('name','Facebook Group')}")
                group_posts: dict[str, dict[str, Any]] = {}
                for spec in query_specs:
                    for post in _scan_low_impact(page, group, spec):
                        group_posts[demand._effective_post_key(post)] = post
                    # Extra pause between search pages to keep the run conservative.
                    page.wait_for_timeout(random.randint(5000, 8000))

                for post in group_posts.values():
                    intent, lead = _classify_foreign_buyer(post)
                    row = dict(post)
                    row["debug_intent"] = str(intent.get("intent_class") or "UNKNOWN")
                    row["debug_confidence"] = int(intent.get("intent_confidence") or 0)
                    row["debug_language"] = _language(str(post.get("text") or ""), str(post.get("query_language") or ""))
                    debug_rows.append(row)

                    if lead is None:
                        continue
                    age = lead.get("age_hours")
                    if isinstance(age, (int, float)) and age > max_age:
                        continue
                    key = demand._effective_post_key(lead)
                    if key in seen:
                        continue
                    leads_by_key[key] = lead
        finally:
            context.close()

    leads = list(leads_by_key.values())
    leads.sort(
        key=lambda x: (
            x.get("classification") == "HOT",
            int(x.get("intent_score") or 0),
            int(x.get("foreign_buyer_specificity") or 0),
            int(x.get("credibility_score") or 0),
        ),
        reverse=True,
    )

    if not retest:
        for lead in leads:
            seen[demand._effective_post_key(lead)] = now
        _save_seen(seen)

    OUTPUT_PATH.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    DEBUG_PATH.write_text(json.dumps(debug_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"BAY-S FOREIGN BUYER RADAR COMPLETE | BUYER leads: {len(leads)}")
    print(f"Latest output: {OUTPUT_PATH}")
    for lead in leads[:10]:
        exact = _exact_link(lead)
        age = lead.get("age_hours")
        print("")
        print(
            f"{lead.get('classification')} | {lead.get('language')} | BUYER | "
            f"I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)}"
        )
        print(
            f"Group: {lead.get('group','')} | Budget: {lead.get('buyer_budget') or '-'} | "
            f"Region: {lead.get('buyer_region') or '-'}"
        )
        print(f"Age: {age:.1f}h" if isinstance(age, (int, float)) else "Age: UNKNOWN")
        print(base._clean_text(lead.get("text"))[:700])
        print(exact or "DIRECT LINK: UNRESOLVED")

    if retest:
        print("TELEGRAM_SKIPPED: safe retest mode")
    elif leads and settings.get("notify_telegram", True):
        _notify(leads)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nFACEBOOK_FOREIGN_BUYER_ERROR: {exc}")
        raise SystemExit(1)
