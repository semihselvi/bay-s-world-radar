from __future__ import annotations

import re
from typing import Any

SUPPLY_PATTERNS = [
    r"\bfor\s+sale\b", r"\bfor\s+rent\b", r"\bavailable\s+(?:unit|units|apartment|flat|villa|property)\b",
    r"\bstarting\s+from\b", r"\bnew\s+listing\b",
    r"\bsat[ıi]l[ıi]k\b", r"\bkiral[ıi]k\b", r"\bportf[öo]y\b",
    r"\bпродаю\b", r"\bпродам\b", r"\bпрода[её]тся\b", r"\bсдам\b", r"\bсдаю\b", r"\bсда[её]тся\b",
    r"\bв\s+продаже\b", r"\bдоступн\w*\b.{0,40}\b(?:квартир|вилл|апартамент)",
]
PORTFOLIO_PATTERNS = [
    r"\bесть\s+(?:квартиры|апартаменты|виллы|студии)\b",
    r"\b(?:1\+1|2\+1|3\+1)\b.{0,120}\b(?:1\+1|2\+1|3\+1)\b",
    r"\bavailable\s+units?\b", r"\bmultiple\s+(?:units?|apartments?|properties)\b",
    r"\bour\s+portfolio\b", r"\bportf[öo]y(?:ümüzde|de)?\b",
    r"\b(?:studio|1\+1|2\+1|3\+1)\b.{0,100}\b(?:starting\s+from|prices?\s+from|цена\s+от|стоимость)",
]
PROFESSIONAL_PATTERNS = [
    r"\brealtor\b", r"\breal\s+estate\s+agent\b", r"\bproperty\s+(?:consultant|advisor)\b", r"\bbroker\b",
    r"\bemlak[çc][ıi]\b", r"\bgayrimenkul\s+dan[ıi][şs]man", r"\bportf[öo]y\s+y[öo]netic",
    r"\bриелтор\b", r"\bриэлтор\b", r"\bагент\s+по\s+недвижимости\b", r"\bагентство\s+недвижимости\b",
]
BUYER_PATTERNS = [
    r"\blooking\s+to\s+buy\b", r"\bwant\s+to\s+buy\b", r"\blooking\s+to\s+rent\b",
    r"\bsat[ıi]n\s+almak\s+istiyorum\b", r"\bkiral[ıi]k\b.{0,60}\bar[ıi]yorum\b",
    r"\bхочу\s+купить\b", r"\bкуплю\b", r"\bхочу\s+снять\b", r"\bсниму\b", r"\bищу\s+на\s+покупку\b",
]
OWNER_FIRST_PERSON = [
    r"\bmy\s+(?:apartment|flat|villa|house|property)\b", r"\bi(?:'m| am)\s+(?:selling|renting\s+out)\b",
    r"\b(?:evimi|dairemi|villam[ıi])\b", r"\bbenim\s+(?:evim|dairem|villam)\b",
    r"\bмоя\s+(?:квартир\w*|вилл\w*|недвижимост\w*)\b", r"\bсобственник\b",
]


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _match(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.I | re.S) for p in patterns)


def identity_key(item: dict[str, Any]) -> str:
    uid = str(item.get("telegram_user_id") or "").strip()
    if uid.isdigit() and uid != "0":
        return "telegram_user:" + uid
    author = _norm(item.get("author"))
    if author.startswith("@") and len(author) > 2:
        return "telegram_username:" + author
    chat = _norm(item.get("telegram_chat"))
    return "local:" + chat + "|" + author if author and chat else ""


def annotate_publisher_types(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        key = identity_key(item)
        if key:
            groups.setdefault(key, []).append(item)

    counts = {"USER": 0, "OWNER": 0, "AGENT": 0}
    for rows in groups.values():
        seller_rows = 0
        portfolio_rows = 0
        buyer_rows = 0
        explicit_professional = False
        owner_first_person = False
        historical_agent = False
        for row in rows:
            text = _norm(" ".join([str(row.get("author") or ""), str(row.get("text") or "")]))
            own = _norm(row.get("text"))
            seller_rows += int(_match(own, SUPPLY_PATTERNS))
            portfolio_rows += int(_match(own, PORTFOLIO_PATTERNS))
            buyer_rows += int(_match(own, BUYER_PATTERNS))
            explicit_professional = explicit_professional or _match(text, PROFESSIONAL_PATTERNS)
            owner_first_person = owner_first_person or _match(own, OWNER_FIRST_PERSON)
            historical_agent = historical_agent or bool(row.get("suspected_agent")) or int(row.get("agent_risk_score") or 0) >= 82

        publisher_type = "USER"
        confidence = 55
        if historical_agent or explicit_professional:
            publisher_type = "AGENT"
            confidence = 98 if explicit_professional else 94
        elif (portfolio_rows >= 2 or seller_rows >= 2) and buyer_rows == 0:
            publisher_type = "AGENT"
            confidence = min(95, 84 + seller_rows * 3 + portfolio_rows * 4)
        elif seller_rows >= 1 and buyer_rows == 0:
            publisher_type = "OWNER"
            confidence = 88 if owner_first_person else 78

        counts[publisher_type] = counts.get(publisher_type, 0) + 1
        for row in rows:
            row["publisher_type"] = publisher_type
            row["publisher_confidence"] = confidence
            row["publisher_listing_count"] = seller_rows
            row["publisher_portfolio_count"] = portfolio_rows
            if publisher_type == "AGENT":
                row["suspected_agent"] = True
                row["agent_risk_score"] = max(int(row.get("agent_risk_score") or 0), confidence)

    print("NC_PUBLISHER_CLASSIFIER", counts)
    return items
