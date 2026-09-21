from __future__ import annotations

import json
from collections import Counter

import facebook_foreign_buyer_radar_v3 as v3
import facebook_foreign_buyer_radar_v4 as v4
import facebook_group_scanner as base


DEBUG_PATH = base.ROOT / "facebook_foreign_buyer_debug_latest.json"


def _group_lookup() -> tuple[dict[str, dict], dict[str, dict]]:
    config = base.load_config()
    by_url: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for group in config.get("groups", []):
        url = base._canonical_group_url(str(group.get("url") or ""))
        name = str(group.get("name") or "")
        if url:
            by_url[url] = group
        if name:
            by_name[name] = group
    return by_url, by_name


def main() -> int:
    if not DEBUG_PATH.exists():
        print(f"DEBUG FILE NOT FOUND: {DEBUG_PATH}")
        return 1

    rows = json.loads(DEBUG_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        print("DEBUG FILE FORMAT ERROR")
        return 1

    by_url, by_name = _group_lookup()

    print("OFFLINE FOREIGN BUYER DEBUG V4")
    print(f"Rows: {len(rows)}")
    print("Facebook/browser access: NONE")
    print("=" * 72)

    intents = Counter()
    langs = Counter()
    decisions = Counter()
    exact = 0

    for index, row in enumerate(rows, start=1):
        row = dict(row)
        canonical_url = base._canonical_group_url(str(row.get("group_url") or ""))
        group = by_url.get(canonical_url) or by_name.get(str(row.get("group") or ""))
        if group is None:
            group = {
                "name": str(row.get("group") or "Unknown group"),
                "url": canonical_url,
                "require_north_signal": False,
                "buyer_priority": "",
            }

        intent, lead, decision = v4.classify_foreign_buyer_v4(row, group)
        intent_class = str(intent.get("intent_class") or "UNKNOWN")
        confidence = int(intent.get("intent_confidence") or 0)
        language = v3._language(str(row.get("text") or ""), str(row.get("query_language") or ""))
        intents[intent_class] += 1
        langs[language] += 1
        decisions[decision] += 1

        exact_url = v3.radar._exact_link(row)
        if exact_url:
            exact += 1

        text = base._clean_text(row.get("text"))
        query = str(row.get("search_query") or "")
        link_quality = str(row.get("link_quality") or "")
        source = str(row.get("link_source") or "")

        reason = "ACCEPTED_AS_FOREIGN_BUYER" if lead is not None else f"REJECT_{decision.upper()}"

        print(f"#{index:02d} | {reason}")
        print(f"Intent: {intent_class} | Confidence: {confidence} | Language: {language}")
        print(
            f"Query: {query} | Link: {link_quality or '-'} | Source: {source or '-'} | "
            f"Exact: {'YES' if exact_url else 'NO'}"
        )
        print(f"Decision: {decision} | North required: {'YES' if group.get('require_north_signal') else 'NO'}")
        print(text[:900])
        print("-" * 72)

    print("SUMMARY")
    print("Intent: " + " | ".join(f"{k}={v}" for k, v in intents.most_common()))
    print("Language: " + " | ".join(f"{k}={v}" for k, v in langs.most_common()))
    print("Decision: " + " | ".join(f"{k}={v}" for k, v in decisions.most_common()))
    print(f"Exact links already captured: {exact}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
