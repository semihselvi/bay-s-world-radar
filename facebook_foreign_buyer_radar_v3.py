from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from playwright.sync_api import sync_playwright

import facebook_demand_search as demand
import facebook_foreign_buyer_radar as radar


QUERY_BY_LANGUAGE = {
    "EN": {"query": "buy property", "language": "EN"},
    "RU": {"query": "купить недвижимость", "language": "RU"},
    "DE": {"query": "Immobilie kaufen", "language": "DE"},
    "PL": {"query": "kupić nieruchomość", "language": "PL"},
}

PL_RE = re.compile(
    r"\b(?:nieruchomość|nieruchomości|mieszkanie|mieszkania|apartament|willa|dom|"
    r"kupić|kupię|szukam|chcę|cypr\s+północny|północnym\s+cyprze)\b",
    re.I,
)

# Used only for groups that cover the whole island. North-Cyprus-specific groups
# already provide location context in the group itself and do not need this check.
NORTH_SIGNAL_RE = re.compile(
    r"\b(?:north(?:ern)?\s+cyprus|trnc|kktc|north\s+cyprus|"
    r"kyrenia|girne|iskele|İskele|long\s+beach|famagusta|gazimağusa|gazimagusa|"
    r"tatlisu|tatlısu|esentepe|bafra|yenibogazici|yeniboğaziçi|"
    r"северн(?:ый|ом)\s+кипр(?:е)?|гирне|кирени[яи]|искеле|фамагуст[ае]?|"
    r"nordzypern|nord\s*zypern|kyrenia|iskele|famagusta|"
    r"cypr\s+północny|cyprze\s+północnym|północnym\s+cyprze)\b",
    re.I,
)

ROTATION_PATH = radar.base.STATE_DIR / "facebook_foreign_buyer_rotation.json"
PENDING_PLAN_PATH = radar.base.STATE_DIR / "facebook_foreign_buyer_pending_plan.json"


def _load_rotation() -> int:
    try:
        data = json.loads(ROTATION_PATH.read_text(encoding="utf-8"))
        return max(0, int(data.get("next_index", 0)))
    except Exception:
        return 0


def _save_rotation(next_index: int) -> None:
    radar.base.STATE_DIR.mkdir(parents=True, exist_ok=True)
    ROTATION_PATH.write_text(
        json.dumps({"next_index": max(0, int(next_index))}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _select_rotating_groups(groups: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], int]:
    if not groups:
        return [], 0
    limit = max(1, min(int(limit), len(groups)))
    start = _load_rotation() % len(groups)
    selected = [groups[(start + offset) % len(groups)] for offset in range(limit)]
    return selected, (start + limit) % len(groups)


def _group_key(group: dict[str, Any]) -> str:
    return str(group.get("url") or group.get("name") or "").strip()


def _save_pending_plan(selected: list[dict[str, Any]], next_index: int) -> None:
    radar.base.STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "group_keys": [_group_key(group) for group in selected],
        "next_index": int(next_index),
        "created_at": time.time(),
    }
    PENDING_PLAN_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_pending_plan(groups: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int] | None:
    try:
        data = json.loads(PENDING_PLAN_PATH.read_text(encoding="utf-8"))
        keys = [str(x) for x in (data.get("group_keys") or []) if str(x).strip()]
        if not keys:
            return None
        by_key = {_group_key(group): group for group in groups}
        selected = [by_key[key] for key in keys if key in by_key]
        if len(selected) != len(keys):
            return None
        next_index = max(0, int(data.get("next_index", _load_rotation())))
        return selected, next_index
    except Exception:
        return None


def _clear_pending_plan() -> None:
    try:
        PENDING_PLAN_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _language(text: str, query_language: str) -> str:
    if PL_RE.search(str(text or "")):
        return "PL"
    detected = radar._language(str(text or ""), query_language)
    return detected if detected in {"EN", "RU", "DE"} else query_language


def _group_specs(group: dict[str, Any]) -> list[dict[str, str]]:
    languages = [str(x).upper() for x in (group.get("buyer_languages") or [])]
    if not languages:
        languages = ["EN"]
    specs: list[dict[str, str]] = []
    for language in languages:
        spec = QUERY_BY_LANGUAGE.get(language)
        if spec:
            specs.append(dict(spec))
    return specs[:1]  # one precise query per group keeps Facebook traffic low


def _classify_foreign_buyer_v3(
    post: dict[str, Any], group: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    intent, generic_lead = demand._classify(post)
    intent_class = str(intent.get("intent_class") or "UNKNOWN")
    if intent_class != "BUYER" or generic_lead is None:
        return intent, None, "not_buyer"

    text = str(post.get("text") or "")
    language = _language(text, str(post.get("query_language") or ""))
    if language not in {"EN", "RU", "DE", "PL"}:
        return intent, None, "unsupported_language"

    if bool(group.get("require_north_signal")) and not NORTH_SIGNAL_RE.search(text):
        return intent, None, "missing_north_cyprus_signal"

    lead = dict(generic_lead)
    details = radar._specifics(text)
    lead["language"] = language
    lead["buyer_budget"] = details["budget"]
    lead["buyer_region"] = details["region"]
    lead["buyer_has_room"] = details["has_room"]
    lead["buyer_has_timing"] = details["has_timing"]
    lead["buyer_priority"] = str(group.get("buyer_priority") or "")

    specificity = sum(
        [
            bool(details["budget"]),
            bool(details["region"]),
            bool(details["has_room"]),
            bool(details["has_timing"]),
        ]
    )
    confidence = int(lead.get("intent_score") or 0)
    credibility = int(lead.get("credibility_score") or 0)
    age = lead.get("age_hours")

    # Unknown-age results stay WARM. Facebook search can surface old posts.
    is_hot = bool(
        isinstance(age, (int, float))
        and confidence >= 80
        and credibility >= 65
        and specificity >= 2
    )
    lead["classification"] = "HOT" if is_hot else "WARM"
    lead["foreign_buyer_specificity"] = specificity
    return intent, lead, "accepted"


def _plan_only(groups: list[dict[str, Any]], max_groups: int) -> int:
    selected, next_index = _select_rotating_groups(groups, max_groups)
    _save_pending_plan(selected, next_index)
    print("BAY-S FOREIGN BUYER RADAR PLAN - Facebook/browser access: NONE")
    print(f"Whitelist groups: {len(groups)} | This run: {len(selected)} | Next rotation index: {next_index}")
    print("PLAN LOCKED: the next real scan will use exactly these groups")
    for idx, group in enumerate(selected, 1):
        specs = _group_specs(group)
        query = specs[0]["query"] if specs else "-"
        language = specs[0]["language"] if specs else "-"
        north = "required" if group.get("require_north_signal") else "group-context"
        print(f"{idx}. [{group.get('buyer_priority','')}] {group.get('name','')} | {language} | {query} | North: {north}")
    return 0


def main() -> int:
    config = radar.base.load_config()
    groups = [
        g
        for g in config.get("groups", [])
        if g.get("enabled", True) and g.get("foreign_buyer_search", False)
    ]
    if not groups:
        print("No groups have foreign_buyer_search=true")
        return 0

    settings = config.get("settings", {})
    max_age = float(settings.get("max_age_hours", 72))
    max_groups = int(settings.get("foreign_buyer_max_groups_per_run", 4))
    max_posts = int(settings.get("foreign_buyer_max_posts_per_search", 8))

    if os.getenv("FACEBOOK_FOREIGN_BUYER_PLAN", "").strip() == "1":
        return _plan_only(groups, max_groups)

    retest = os.getenv("FACEBOOK_FOREIGN_BUYER_RETEST", "").strip() == "1"
    if retest:
        selected_groups = groups[:1]
        next_rotation = _load_rotation()
        print("SAFE RETEST: 1 group x 1 language query | Telegram disabled | no menu/post clicks")
    else:
        pending = _load_pending_plan(groups)
        if pending is not None:
            selected_groups, next_rotation = pending
            print("USING LOCKED PLAN: exact groups from the latest offline plan")
        else:
            selected_groups, next_rotation = _select_rotating_groups(groups, max_groups)
        print(
            f"FOREIGN BUYER RADAR: whitelist={len(groups)} | "
            f"this run={len(selected_groups)} | max {max_posts} posts/search"
        )

    seen = {} if retest else radar._load_seen()
    now = time.time()
    debug_rows: list[dict[str, Any]] = []
    leads_by_key: dict[str, dict[str, Any]] = {}

    with sync_playwright() as playwright:
        context = radar.base._launch_context(playwright, headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            radar.base.ensure_facebook_login(page)

            for group in selected_groups:
                print(
                    f"\nSearching foreign buyers: {group.get('name','Facebook Group')} "
                    f"[{group.get('buyer_priority','')}]"
                )
                group_posts: dict[str, dict[str, Any]] = {}
                for spec in _group_specs(group):
                    for post in radar._scan_low_impact(page, group, spec, max_posts=max_posts):
                        group_posts[demand._effective_post_key(post)] = post
                    # Conservative pause between group searches.
                    page.wait_for_timeout(radar.random.randint(5000, 8000))

                for post in group_posts.values():
                    intent, lead, decision = _classify_foreign_buyer_v3(post, group)
                    row = dict(post)
                    row["debug_intent"] = str(intent.get("intent_class") or "UNKNOWN")
                    row["debug_confidence"] = int(intent.get("intent_confidence") or 0)
                    row["debug_language"] = _language(
                        str(post.get("text") or ""), str(post.get("query_language") or "")
                    )
                    row["debug_decision"] = decision
                    row["buyer_priority"] = str(group.get("buyer_priority") or "")
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
            x.get("buyer_priority") == "A+",
            int(x.get("intent_score") or 0),
            int(x.get("foreign_buyer_specificity") or 0),
            int(x.get("credibility_score") or 0),
        ),
        reverse=True,
    )

    if not retest:
        for lead in leads:
            seen[demand._effective_post_key(lead)] = now
        radar._save_seen(seen)
        _save_rotation(next_rotation)
        _clear_pending_plan()

    radar.OUTPUT_PATH.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    radar.DEBUG_PATH.write_text(json.dumps(debug_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print(f"BAY-S FOREIGN BUYER RADAR COMPLETE | BUYER leads: {len(leads)}")
    print(f"Groups scanned this run: {len(selected_groups)}/{len(groups)}")
    print(f"Latest output: {radar.OUTPUT_PATH}")

    for lead in leads[:10]:
        exact = radar._exact_link(lead)
        age = lead.get("age_hours")
        print("")
        print(
            f"{lead.get('classification')} | {lead.get('language')} | BUYER | "
            f"I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)} | "
            f"Priority {lead.get('buyer_priority','')}"
        )
        print(
            f"Group: {lead.get('group','')} | Budget: {lead.get('buyer_budget') or '-'} | "
            f"Region: {lead.get('buyer_region') or '-'}"
        )
        print(f"Age: {age:.1f}h" if isinstance(age, (int, float)) else "Age: UNKNOWN")
        print(radar.base._clean_text(lead.get("text"))[:700])
        print(exact or "DIRECT LINK: UNRESOLVED")

    if retest:
        print("TELEGRAM_SKIPPED: safe retest mode")
    elif leads and settings.get("notify_telegram", True):
        radar._notify(leads)
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
