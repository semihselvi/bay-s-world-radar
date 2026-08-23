import re

import main
import north_cyprus_catcher as base
import north_cyprus_focus as nf


# Very short buyer reactions under a property post often carry no property noun.
# The parent/replied-to post supplies the object; the user's own message supplies
# intent. Never mix the parent's seller CTA into spam/seller checks.
ENGAGEMENT_PATTERNS = [
    # English
    r"\binterested\b", r"\bdetails please\b", r"\bmore details\b", r"\bsend (?:me )?(?:details|info|information|price)\b",
    r"\bprice please\b", r"\bhow much\??$", r"\bstill available\b", r"\bis this available\b", r"\bcan i view\b",
    # Turkish
    r"\bilgileniyorum\b", r"\bdetay alabilir miyim\b", r"\bbilgi alabilir miyim\b", r"\bfiyat alabilir miyim\b",
    r"\bfiyat nedir\b", r"\bhala mevcut mu\b", r"\bhalen mevcut mu\b", r"\bg[öo]rebilir miyim\b",
    # Russian
    r"\bинтересует\b", r"\bинтересно\b", r"\bможно подробнее\b", r"\bподробнее пожалуйста\b", r"\bкакая цена\b",
    r"\bсколько\??$", r"\bактуально\??$", r"\bещ[её] актуально\b", r"\bможно посмотреть\b", r"\bпришлите подробности\b",
    # German / French / Polish / Ukrainian
    r"\binteressiert\b", r"\bmehr details\b", r"\bnoch verfügbar\b", r"\bwie viel\??$",
    r"\bje suis intéress[ée]\b", r"\bplus de d[ée]tails\b", r"\btoujours disponible\b", r"\bquel prix\b",
    r"\bjestem zainteresowan", r"\bwięcej szczegółów\b", r"\bczy aktualne\b", r"\bjaka cena\b",
    r"\bзацікав", r"\bможна детальніше\b", r"\bяка ціна\b", r"\bще актуально\b",
]

STRONG_ENGAGEMENT_PATTERNS = [
    r"\binterested\b", r"\bstill available\b", r"\bis this available\b", r"\bcan i view\b",
    r"\bilgileniyorum\b", r"\bhala mevcut mu\b", r"\bg[öo]rebilir miyim\b",
    r"\bинтересует\b", r"\bактуально\??$", r"\bещ[её] актуально\b", r"\bможно посмотреть\b",
    r"\binteressiert\b", r"\bnoch verfügbar\b", r"\bje suis intéress[ée]\b", r"\btoujours disponible\b",
    r"\bjestem zainteresowan", r"\bczy aktualne\b", r"\bзацікав", r"\bще актуально\b",
]

_original_classify = base._classify


def _matches(text, patterns):
    return any(re.search(p, text or "", re.I) for p in patterns)


def classify_with_reply_context(item, cutoff):
    lead, reason = _original_classify(item, cutoff)
    if lead:
        return lead, reason

    # Hard rejections must remain hard rejections.
    if reason in {
        "non_user_source", "date_unverified", "older_than_window", "empty",
        "promotional_or_seller", "rental",
    }:
        return None, reason

    parent = " ".join(str(item.get("reply_context", "")).split())
    if not parent:
        return None, reason

    user_text = str(item.get("text", "")).strip()
    if not user_text or not _matches(user_text, ENGAGEMENT_PATTERNS):
        return None, reason

    combined = f"{user_text} {parent}"
    # Parent must establish a North-Cyprus property/project context. The parent
    # may be an agent/listing; that is fine because only the human reply is scored.
    if not nf._nc_context(item, combined):
        return None, reason
    property_or_project = nf._matches(combined, nf.PROPERTY_PATTERNS) or base._project_signal(combined)
    if not property_or_project:
        return None, reason
    if nf._matches(combined, nf.RENTAL_PATTERNS) and not re.search(r"\b(?:sale|sat[ıi]l[ıi]k|продаж|resale|buy|sat[ıi]n|куп)\b", parent, re.I):
        return None, "reply_context_rental"

    strong = _matches(user_text, STRONG_ENGAGEMENT_PATTERNS)
    label = "WARM" if strong else "POTENTIAL"
    lead = dict(item)
    lead.update({
        "classification": label,
        "intent_score": 72 if strong else 61,
        "credibility_score": 74 if item.get("author") else 64,
        "market_fit_score": 96,
        "market": "north_cyprus",
        "scanned_at": main.now_utc().isoformat(),
        "catcher_reason": "reply_context_buyer_engagement",
        "reply_context_used": parent[:1200],
    })
    return lead, "accepted_reply_context"


base._classify = classify_with_reply_context
