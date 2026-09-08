from __future__ import annotations

import re
from typing import Any

import facebook_foreign_buyer_radar_v3 as v3


# V4 tightens both search phrasing and final acceptance. The goal is a direct
# end-buyer, not educational posts, agents, sellers or people talking about buyers.
v3.QUERY_BY_LANGUAGE = {
    "EN": {"query": "looking to buy property", "language": "EN"},
    "RU": {"query": "хочу купить недвижимость", "language": "RU"},
    "DE": {"query": "suche Immobilie zum Kauf", "language": "DE"},
    "PL": {"query": "chcę kupić nieruchomość", "language": "PL"},
}

DIRECT_BUYER_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "EN": [
        re.compile(
            r"\b(?:i|we)\b.{0,25}\b(?:looking|want|would\s+like|planning|plan|ready|interested)\b"
            r".{0,80}\b(?:buy|purchase|buying|purchasing)\b.{0,160}\b(?:property|apartment|flat|villa|house|studio)s?\b",
            re.I | re.S,
        ),
        re.compile(
            r"\blooking\s+for\b.{0,140}\b(?:property|apartment|flat|villa|house|studio)s?\b"
            r".{0,100}\b(?:to\s+buy|to\s+purchase|for\s+purchase)\b",
            re.I | re.S,
        ),
        re.compile(r"\bcash\s+buyer\b.{0,160}\b(?:property|apartment|flat|villa|house|studio)s?\b", re.I | re.S),
    ],
    "DE": [
        re.compile(
            r"\b(?:ich|wir)\b.{0,25}\b(?:möchte|moechte|möchten|moechten|will|wollen|plane|planen|suche|suchen)\b"
            r".{0,180}\b(?:immobilie|wohnung|haus|villa|apartment)\w*\b.{0,120}\b(?:kaufen|erwerben|zum\s+kauf|zu\s+kaufen)\b",
            re.I | re.S,
        ),
        re.compile(
            r"\b(?:ich|wir)\b.{0,25}\b(?:möchte|moechte|möchten|moechten|will|wollen|plane|planen|suche|suchen)\b"
            r".{0,100}\b(?:kaufen|erwerben)\b.{0,180}\b(?:immobilie|wohnung|haus|villa|apartment)\w*\b",
            re.I | re.S,
        ),
        re.compile(
            r"\bsuche\b.{0,140}\b(?:immobilie|wohnung|haus|villa|apartment)\w*\b.{0,100}\b(?:zum\s+kauf|zu\s+kaufen)\b",
            re.I | re.S,
        ),
    ],
    "RU": [
        re.compile(
            r"\b(?:я|мы)\b.{0,25}\b(?:хочу|хотим|планирую|планируем|ищу|ищем|готов\w*)\b"
            r".{0,120}\b(?:купить|покупк\w*)\b.{0,180}\b(?:недвижимост\w*|квартир\w*|апартамент\w*|вилл\w*|дом\w*)\b",
            re.I | re.S,
        ),
        re.compile(
            r"\bищу\b.{0,140}\b(?:недвижимост\w*|квартир\w*|апартамент\w*|вилл\w*|дом\w*)\b"
            r".{0,100}\b(?:купить|покупк\w*)\b",
            re.I | re.S,
        ),
    ],
    "PL": [
        re.compile(
            r"\b(?:ja|my)\b.{0,25}\b(?:chcę|chcemy|szukam|szukamy|planuję|planujemy)\b"
            r".{0,120}\b(?:kupić|kupic|zakupić|zakupic)\b.{0,180}\b(?:nieruchomość|nieruchomosci|mieszkanie|apartament|willa|dom)\w*\b",
            re.I | re.S,
        ),
        re.compile(
            r"\bszukam\b.{0,140}\b(?:nieruchomość|nieruchomosci|mieszkanie|apartament|willa|dom)\w*\b"
            r".{0,100}\b(?:do\s+kupienia|na\s+zakup|kupić|kupic)\b",
            re.I | re.S,
        ),
    ],
}


def _has_direct_buyer_voice(text: str, language: str) -> bool:
    return any(pattern.search(text or "") for pattern in DIRECT_BUYER_PATTERNS.get(language, []))


_original_classify = v3._classify_foreign_buyer_v3


def classify_foreign_buyer_v4(
    post: dict[str, Any], group: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any] | None, str]:
    intent, lead, decision = _original_classify(post, group)
    if lead is None:
        return intent, None, decision

    text = str(post.get("text") or "")
    language = str(lead.get("language") or v3._language(text, str(post.get("query_language") or "")))
    if not _has_direct_buyer_voice(text, language):
        return intent, None, "missing_direct_buyer_voice"

    return intent, lead, "accepted"


# v3.main() resolves this global function at runtime, so patching it here keeps
# the stable scanner/rotation implementation while applying V4 acceptance rules.
v3._classify_foreign_buyer_v3 = classify_foreign_buyer_v4


def main() -> int:
    return v3.main()


if __name__ == "__main__":
    raise SystemExit(main())
