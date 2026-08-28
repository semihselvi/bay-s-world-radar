from __future__ import annotations

import re
from typing import Any, Callable


PROPERTY = re.compile(
    r"\b(?:property|apartment|apartments|flat|flats|villa|villas|house|houses|studio|studios|"
    r"immobilie|immobilien|wohnung|wohnungen|haus|haeuser|häuser|"
    r"daire|daireler|ev|evler|villa|villalar|st[üu]dyo|konut|"
    r"квартир\w*|апартамент\w*|вилл\w*|дом\w*|студи\w*)\b|\b[0-6]\s*\+\s*[0-3]\b",
    re.I,
)

BUY_DEMAND = [
    # English direct purchase intent. Facebook posts frequently say "looking to buy"
    # rather than "looking for ... to buy", so keep both directions explicit.
    re.compile(
        r"\b(?:looking|hoping|want(?:ing)?|would\s+like|interested|considering|thinking|planning|ready)\b"
        r".{0,35}\b(?:to\s+buy|to\s+purchase|buying|purchasing)\b"
        r".{0,160}\b(?:property|apartment|flat|villa|house|studio)s?\b",
        re.I | re.S,
    ),
    re.compile(
        r"\b(?:property|apartment|flat|villa|house|studio)s?\b"
        r".{0,160}\b(?:looking|hoping|want(?:ing)?|would\s+like|interested|considering|thinking|planning|ready)\b"
        r".{0,35}\b(?:to\s+buy|to\s+purchase|buying|purchasing)\b",
        re.I | re.S,
    ),
    re.compile(r"\bcash\s+buyer\b.{0,160}\b(?:property|apartment|flat|villa|house|studio)s?\b", re.I | re.S),
    re.compile(r"\blooking\s+for\b.{0,100}\b(?:to\s+buy|for\s+sale)\b", re.I | re.S),
    re.compile(r"\b(?:want|wants|wanted|planning|plan|ready|hoping)\s+(?:to\s+)?buy\b.{0,140}\b(?:property|apartment|flat|villa|house|studio)s?\b", re.I | re.S),
    re.compile(r"\b(?:property|apartment|flat|villa|house|studio)s?\b.{0,80}\b(?:wanted\s+to\s+buy|wanted\s+for\s+purchase)\b", re.I | re.S),
    re.compile(r"\b(?:any|does\s+anyone\s+know\s+(?:of\s+)?)\b.{0,80}\b(?:property|apartment|flat|villa|house|studio)s?\b.{0,80}\bfor\s+sale\b", re.I | re.S),
    re.compile(r"\bsat[ıi]l[ıi]k\b.{0,80}\b(?:daire|ev|villa|st[üu]dyo|konut)\b.{0,80}\bar[ıi]yorum\b", re.I | re.S),
    re.compile(r"\b(?:daire|ev|villa|st[üu]dyo|konut)\b.{0,80}\bsat[ıi]l[ıi]k\b.{0,80}\bar[ıi]yorum\b", re.I | re.S),
    re.compile(r"\bal[ıi]c[ıi]y[ıi]m\b.{0,100}\b(?:daire|ev|villa|st[üu]dyo|konut)\b", re.I | re.S),
    re.compile(r"\bищу\b.{0,100}\b(?:купить|на\s+покупку|для\s+покупки)\b", re.I | re.S),
    re.compile(r"\b(?:хочу|планирую|готов\w*)\b.{0,100}\bкупить\b.{0,120}\b(?:недвижимост\w*|квартир\w*|апартамент\w*|вилл\w*|дом\w*)\b", re.I | re.S),
    re.compile(r"\b(?:ich\s+)?(?:möchte|moechte|will|plane|suche)\b.{0,120}\b(?:immobilie|wohnung|haus|villa|apartment)\w*\b.{0,100}\b(?:kaufen|erwerben)\b", re.I | re.S),
    re.compile(r"\b(?:immobilie|wohnung|haus|villa|apartment)\w*\b.{0,100}\b(?:kaufen|zum\s+kauf\s+gesucht|zu\s+kaufen\s+gesucht)\b", re.I | re.S),
    re.compile(r"\bsuche\b.{0,120}\b(?:immobilie|wohnung|haus|villa|apartment)\w*\b.{0,80}\b(?:zum\s+kauf|zu\s+kaufen)\b", re.I | re.S),
]

RENT_DEMAND = [
    re.compile(r"\blooking\s+for\b.{0,120}\b(?:to\s+rent|for\s+rent|rental|long[-\s]?term|short[-\s]?term)\b", re.I | re.S),
    re.compile(r"\b(?:does\s+anyone\s+know|anyone\s+know|need|wanted)\b.{0,120}\b(?:apartment|flat|villa|house|studio)s?\b.{0,100}\b(?:for\s+rent|to\s+rent|rental|long[-\s]?term|short[-\s]?term)\b", re.I | re.S),
    re.compile(r"\b(?:apartment|flat|villa|house|studio)s?\b.{0,100}\b(?:for\s+rent|to\s+rent|rental)\b.{0,100}\b(?:looking|need|wanted|any\s+available)\b", re.I | re.S),
    re.compile(r"\bkiral[ıi]k\b.{0,100}\b(?:daire|ev|villa|st[üu]dyo|konut)\b.{0,100}\bar[ıi]yorum\b", re.I | re.S),
    re.compile(r"\b(?:daire|ev|villa|st[üu]dyo|konut)\b.{0,100}\bkiral[ıi]k\b.{0,100}\bar[ıi]yorum\b", re.I | re.S),
    re.compile(r"\b(?:uzun|k[ıi]sa)\s+d[öo]nem\b.{0,120}\b(?:daire|ev|villa|st[üu]dyo|konut)\b.{0,100}\bar[ıi]yorum\b", re.I | re.S),
    re.compile(r"\bищу\b.{0,120}\b(?:снять|в\s+аренду|на\s+долгосрок|долгосроч)\b", re.I | re.S),
]

# Facebook groups often contain agents/property finders posting requirements on
# behalf of clients. Those are useful market signals, but they are not direct
# buyer/tenant leads for Buyer Catcher and should not be promoted as TENANT/BUYER.
INTERMEDIARY_PATTERNS = [
    re.compile(r"\b(?:my|our)\s+client(?:s)?\b", re.I),
    re.compile(r"\bfor\s+(?:a|one|two|three|four|five|\d+)\s+clients?\b", re.I),
    re.compile(r"\bfor\s+clients?\b", re.I),
    re.compile(r"\bdear\s+property\s+owners\b", re.I),
    re.compile(r"\bproperty\s+owners\b.{0,180}\b(?:send|dm|message|contact)\b", re.I | re.S),
    re.compile(r"\bm[üu][şs]terim\s+i[çc]in\b", re.I),
    re.compile(r"\bm[üu][şs]terilerim\s+i[çc]in\b", re.I),
    re.compile(r"\bдля\s+(?:моего|нашего|своего)\s+клиент\w*\b", re.I),
    re.compile(r"\b(?:für|fuer)\s+(?:meinen|unseren|einen)\s+kunden\b", re.I),
]

SUPPLY_GUARD = re.compile(
    r"\b(?:for\s+sale|for\s+rent|available\s+now|sat[ıi]l[ıi]k|kiral[ıi]k|прода[её]тся|сда[её]тся|"
    r"zu\s+verkaufen|zum\s+verkauf|zu\s+vermieten)\b",
    re.I,
)
DEMAND_WORD = re.compile(
    r"\b(?:looking|need|wanted|want|planning|ready|interested|considering|thinking|purchase|buying|"
    r"ar[ıi]yorum|istiyorum|al[ıi]c[ıi]y[ıi]m|ищу|хочу|нужн\w*|möchte|moechte|suche|kaufen|erwerben)\b",
    re.I,
)


def _matched(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(p.search(text) for p in patterns)


def _agent_result(result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    out["intent_class"] = "AGENT"
    out["intent_confidence"] = max(92, int(out.get("intent_confidence") or 0))
    out["intent_reasons"] = ["facebook_intermediary_for_client"]
    return out


def classify_facebook_intent(item: dict[str, Any], base_classifier: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    """Add conservative Facebook-specific phrasing without weakening the core classifier."""
    result = base_classifier(item)
    text = str(item.get("text") or "")

    # This override intentionally also applies when the core classifier returned a
    # demand class: explicit client language means the poster is an intermediary,
    # not the end buyer/tenant. Phrases such as "no agents please" do not match.
    if _matched(text, INTERMEDIARY_PATTERNS):
        return _agent_result(result)

    if str(result.get("intent_class") or "UNKNOWN") != "UNKNOWN":
        return result

    if not PROPERTY.search(text):
        return result

    # Only override when the text itself contains clear demand direction.
    # This prevents ordinary property advertisements from becoming leads.
    if _matched(text, RENT_DEMAND):
        out = dict(result)
        out["intent_class"] = "TENANT"
        out["intent_confidence"] = max(78, int(out.get("intent_confidence") or 0))
        out["intent_reasons"] = ["facebook_explicit_rental_demand", "property_context", "north_cyprus_group_context"]
        return out

    if _matched(text, BUY_DEMAND):
        out = dict(result)
        out["intent_class"] = "BUYER"
        out["intent_confidence"] = max(78, int(out.get("intent_confidence") or 0))
        out["intent_reasons"] = ["facebook_explicit_purchase_demand", "property_context", "north_cyprus_group_context"]
        return out

    # A generic supply phrase alone must never be upgraded. Keep ambiguous cases UNKNOWN.
    if SUPPLY_GUARD.search(text) and not DEMAND_WORD.search(text):
        return result

    return result
