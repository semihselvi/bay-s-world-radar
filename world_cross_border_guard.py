from __future__ import annotations

import re

import main


VERSION = "1.1-west-europe-cross-border-only"

# WORLD west_europe is for people crossing borders / buying abroad. Domestic
# home-purchase conversations are handled by separate LOCAL buyer radars and
# must not be sent as WORLD opportunities.
WEST_EUROPE_BUCKET = "shard_west_europe_"

EXPLICIT_CROSS_BORDER_RE = re.compile(
    r"(?:\babroad\b|\boverseas\b|\bforeign\s+property\b|\bproperty\s+abroad\b|"
    r"\bbuy(?:ing)?\s+abroad\b|\bpurchase\s+abroad\b|\bin\s+another\s+country\b|"
    r"\boutside\s+(?:the\s+)?(?:uk|united\s+kingdom|germany|france|netherlands|belgium)\b|"
    r"\bim\s+ausland\b|\bauslandsimmobilie\w*\b|\bimmobilie\w*\s+im\s+ausland\b|"
    r"\b[àa]\s+l['’]étranger\b|\bimmobilier\s+[àa]\s+l['’]étranger\b|"
    r"\bin\s+het\s+buitenland\b|\bbuitenlands\s+vastgoed\b|"
    r"\bza\s+granic[ąa]\b)",
    re.I,
)

# High-value foreign destinations for the west-Europe audience. A destination
# by itself is not enough; it must be in the same sentence/phrase as a purchase,
# second-home or relocation action. That prevents unrelated navigation/footer
# country links from converting a domestic buyer into a WORLD lead.
DESTINATION_RE = (
    r"(?:north(?:ern)?\s+cyprus|cyprus|spain|portugal|italy|greece|malta|"
    r"montenegro|croatia|turkey|türkiye|dubai|uae|united\s+arab\s+emirates|"
    r"algarve|lisbon|madeira|mallorca|costa\s+del\s+sol|marbella|alicante|"
    r"athens|crete|girne|kyrenia|iskele|famagusta|gazimağusa)"
)

BUY_TO_DEST_RE = re.compile(
    rf"(?:buy(?:ing)?|purchase|purchasing|looking\s+to\s+buy|want(?:ing)?\s+to\s+buy|"
    rf"consider(?:ing)?\s+buying|second\s+home|holiday\s+home|investment\s+property|"
    rf"relocat(?:e|ing)|mov(?:e|ing)|emigrat(?:e|ing))"
    rf"[^.!?\n]{{0,120}}\b{DESTINATION_RE}\b",
    re.I,
)

DEST_TO_BUY_RE = re.compile(
    rf"\b{DESTINATION_RE}\b[^.!?\n]{{0,120}}(?:buy(?:ing)?|purchase|purchasing|"
    rf"second\s+home|holiday\s+home|investment\s+property|relocat(?:e|ing)|"
    rf"mov(?:e|ing)|emigrat(?:e|ing))",
    re.I,
)


def _primary_text(item: dict) -> str:
    """Use the post title + opening body only, not an unlimited forum page."""
    title = str(item.get("title") or "")
    body = str(item.get("text") or "")[:4500]
    return f"{title}. {body}".lower()


def cross_border_signal(item: dict) -> bool:
    text = _primary_text(item)
    if EXPLICIT_CROSS_BORDER_RE.search(text):
        return True
    if BUY_TO_DEST_RE.search(text) or DEST_TO_BUY_RE.search(text):
        return True
    return False


_original_keep_candidate = main.keep_candidate


def keep_candidate(item, cutoff):
    keep, reason = _original_keep_candidate(item, cutoff)
    if not keep:
        return keep, reason

    bucket = str(item.get("source_bucket") or "").lower()
    if WEST_EUROPE_BUCKET in bucket and not cross_border_signal(item):
        return False, "west_europe_domestic_purchase"
    return True, reason


# Patch only the shared candidate gate. The bucket check makes this a no-op for
# North Cyprus, Golden Visa and Telegram lanes.
main.keep_candidate = keep_candidate
