from __future__ import annotations

import json
from collections import Counter

import facebook_foreign_buyer_radar as radar
import facebook_group_scanner as base
import facebook_demand_search as demand


DEBUG_PATH = base.ROOT / "facebook_foreign_buyer_debug_latest.json"


def main() -> int:
    if not DEBUG_PATH.exists():
        print(f"DEBUG FILE NOT FOUND: {DEBUG_PATH}")
        return 1

    rows = json.loads(DEBUG_PATH.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        print("DEBUG FILE FORMAT ERROR")
        return 1

    print("OFFLINE FOREIGN BUYER DEBUG")
    print(f"Rows: {len(rows)}")
    print("Facebook/browser access: NONE")
    print("=" * 72)

    intents = Counter()
    langs = Counter()
    exact = 0

    for index, row in enumerate(rows, start=1):
        # Re-run classification using the current local code only. No web access.
        intent, lead = radar._classify_foreign_buyer(dict(row))
        intent_class = str(intent.get("intent_class") or "UNKNOWN")
        confidence = int(intent.get("intent_confidence") or 0)
        language = radar._language(str(row.get("text") or ""), str(row.get("query_language") or ""))
        intents[intent_class] += 1
        langs[language] += 1

        group_url = str(row.get("group_url") or "")
        exact_url = radar._exact_link(dict(row))
        if exact_url:
            exact += 1

        text = base._clean_text(row.get("text"))
        query = str(row.get("search_query") or "")
        link_quality = str(row.get("link_quality") or "")
        source = str(row.get("link_source") or "")

        if lead is not None:
            reason = "ACCEPTED_AS_FOREIGN_BUYER"
        elif intent_class != "BUYER":
            reason = f"REJECT_INTENT_{intent_class}"
        elif language not in {"EN", "RU", "DE"}:
            reason = f"REJECT_LANGUAGE_{language}"
        else:
            reason = "REJECT_OTHER"

        print(f"#{index:02d} | {reason}")
        print(f"Intent: {intent_class} | Confidence: {confidence} | Language: {language}")
        print(f"Query: {query} | Link: {link_quality or '-'} | Source: {source or '-'} | Exact: {'YES' if exact_url else 'NO'}")
        print(text[:900])
        print("-" * 72)

    print("SUMMARY")
    print("Intent: " + " | ".join(f"{k}={v}" for k, v in intents.most_common()))
    print("Language: " + " | ".join(f"{k}={v}" for k, v in langs.most_common()))
    print(f"Exact links already captured: {exact}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
