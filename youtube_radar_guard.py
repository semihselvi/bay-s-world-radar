import re

import youtube_radar_expanded as expanded

# youtube_radar_expanded already installs reply expansion, watchlist ranking and
# the first precision layer. This final guard only allows an alert when the
# COMMENT ITSELF contains a genuine commercial/buyer request. Video titles are
# never allowed to create intent on their own.
yr = expanded.yr
yce = expanded.yce
_base_classify = yr.classify_comment

# These base patterns are useful in context but too broad on their own. In
# particular, Turkish "ne kadar" can mean "how ugly / how much ..." in normal
# conversation and previously created a false WARM lead.
BROAD_REQUEST_PATTERNS = {r"ne kadar", r"var m[ıi]"}
SAFE_REQUEST_PATTERNS = [p for p in yr.REQUEST_PATTERNS if p not in BROAD_REQUEST_PATTERNS]

# A one/two-word price ping on a sales video is engagement, not enough evidence
# that the commenter is a real buyer. Keep it out of Telegram alerts unless the
# comment also names the property/unit or asks a fuller transactional question.
BARE_PRICE_ONLY_RE = re.compile(
    r"^\s*(?:"
    r"fiyat(?:ı|i)?|price|how\s+much|ne\s+kadar|"
    r"цена|какая\s+цена|сколько|сколько\s+стоит|"
    r"preis|prix|prezzo|precio|prijs|cena"
    r")\s*[?!.]*\s*$",
    re.I,
)

TURKISH_PRICE_REQUEST_RE = re.compile(
    r"(?:"
    r"\b(?:fiyat|fiyatı|fiyati|ücret|ucret)\b.{0,30}\bne kadar\b|"
    r"\b(?:daire|ev|villa|arsa|stüdyo|studyo|1\s*\+\s*[01]|2\s*\+\s*[01]|3\s*\+\s*[01])\b.{0,35}\bne kadar\b"
    r")",
    re.I,
)

TURKISH_AVAILABILITY_RE = re.compile(
    r"\b(?:daire|ev|villa|arsa|stüdyo|studyo|1\s*\+\s*[01]|2\s*\+\s*[01]|3\s*\+\s*[01]|satılık|satilik|müsait|musait|mevcut)\b.{0,35}\bvar m[ıi]\b",
    re.I,
)

# Existing owners / buyers asking whether a property they already bought or are
# still paying off can be used for residency are after-sale / residency leads,
# not fresh property buyers. Keep this narrow: residency context plus explicit
# existing-purchase evidence must both be present.
RESIDENCY_CONTEXT_RE = re.compile(
    r"(?:\bвнж\b|\bвид\s+на\s+жительство\b|\bоформлени\w*\s+внж\b|"
    r"\bresidence\s+permit\b|\bresidency\b|\boturma\s+izn\w*\b)",
    re.I,
)

EXISTING_PURCHASE_RE = re.compile(
    r"(?:"
    r"\b(?:купил(?:а|и)?|приобр[её]л(?:а|и)?|у\s+меня\s+есть|у\s+нас\s+есть)\b.{0,120}"
    r"(?:квартир\w*|апартамент\w*|студи\w*|дом\w*|вилл\w*)|"
    r"(?:квартир\w*|апартамент\w*|студи\w*|дом\w*|вилл\w*).{0,120}"
    r"(?:\bв\s+рассрочк\w*\b|\bещ[её]\s+в\s+рассрочк\w*\b|\bпока\s+ещ[её]\s+в\s+рассрочк\w*\b)|"
    r"\balready\s+(?:bought|purchased|own)\b.{0,120}(?:apartment|property|home|house|villa)|"
    r"\b(?:my|our)\s+(?:apartment|property|home|house|villa)\b.{0,120}\b(?:installments?|mortgage|residence\s+permit|residency)\b|"
    r"\b(?:ald[ıi]m|sat[ıi]n\s+ald[ıi]k|sahibim)\b.{0,120}(?:daire|ev|villa|m[üu]lk)|"
    r"(?:daire|ev|villa|m[üu]lk).{0,120}\b(?:taksit(?:leri)?\s+devam|taksitte|taksitli)\b"
    r")",
    re.I | re.S,
)


def _is_post_purchase_residency(text: str) -> bool:
    text = " ".join(str(text or "").split())
    return bool(RESIDENCY_CONTEXT_RE.search(text) and EXISTING_PURCHASE_RE.search(text))


def _reply_chain_is_after_sale(item: dict) -> bool:
    # Replies inherit the top-level comment via youtube_comment_expansion. This is
    # essential for follow-ups such as "does a studio work for 4 people / what
    # about titles?" where the parent already says the Caesar studio is on
    # installments and the question is about residency.
    combined = " ".join(
        str(x or "") for x in (item.get("reply_context"), item.get("text"))
    )
    return _is_post_purchase_residency(combined)


def _safe_actionable(text: str) -> bool:
    text = " ".join(str(text or "").split())
    if not text:
        return False
    if _is_post_purchase_residency(text):
        return False
    if BARE_PRICE_ONLY_RE.fullmatch(text):
        return False
    if yr._matches(text, yr.STRONG_BUYER_PATTERNS):
        return True
    if yr._matches(text, SAFE_REQUEST_PATTERNS):
        return True
    if TURKISH_PRICE_REQUEST_RE.search(text) or TURKISH_AVAILABILITY_RE.search(text):
        return True
    if any(re.search(pattern, text, re.I) for pattern in yce.ENGAGEMENT):
        return True
    return False


def classify_comment_guarded(item):
    comment = " ".join(str(item.get("text", "")).split())
    if _reply_chain_is_after_sale(item):
        return None
    if not _safe_actionable(comment):
        return None
    return _base_classify(item)


yr.classify_comment = classify_comment_guarded


def run():
    return yr.run()


if __name__ == "__main__":
    run()
