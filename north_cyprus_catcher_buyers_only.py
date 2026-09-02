from __future__ import annotations

import re

import north_cyprus_catcher_expanded as expanded

# The North Cyprus Buyer Catcher is BUYER-only. Tenant / rental demand belongs to
# a separate rental lane and must never be presented as a "GERÇEK ADAY" buyer.
_ORIGINAL_CLASSIFY = expanded.base._classify

RENTAL_ONLY_RE = re.compile(
    r"(?:"
    r"\bfor\s+rent\b|\blooking\s+to\s+rent\b|\brental\b|\broommate\b|\broom\s+to\s+rent\b|"
    r"\bаренд\w*\b|\bсниму\b|\bснять\b|\bподселени\w*\b|\bкомнат\w*.{0,40}\bподселени\w*\b|"
    r"\bkiralık\b|\bkiralam\w*\b|"
    r"\bmiete\b|\bmieten\b|\bzu\s+mieten\b|"
    r"\bhuur\b|\bhuren\b|\bte\s+huur\b|"
    r"\bwynajem\w*\b|\bwynająć\b|"
    r"\bà\s+louer\b|\ba\s+louer\b|\blocation\b"
    r")",
    re.I | re.S,
)

PURCHASE_RE = re.compile(
    r"(?:"
    r"\b(?:buy|purchase|buying|purchasing|for\s+purchase)\b|"
    r"\b(?:купить|покупк\w*|приобрест\w*|для\s+покупк\w*)\b|"
    r"\b(?:satın\s+al|almak|satılık)\b|"
    r"\b(?:kaufen|zum\s+kauf|erwerben)\b|"
    r"\b(?:kopen|koopwoning)\b|"
    r"\b(?:acheter|achat)\b|"
    r"\b(?:kupić|kupic|zakupić|zakupic)\b"
    r")",
    re.I | re.S,
)


def buyer_only_classify(item, cutoff):
    # Direction-first classifier is the strongest signal. TENANT is never a buyer.
    intent = expanded.classify_intent(item)
    expanded._decorate_intent(item, intent)
    intent_class = str(intent.get("intent_class") or "UNKNOWN")
    subtypes = set(intent.get("intent_subtypes") or [])
    text = " ".join(str(item.get(k) or "") for k in ("title", "text", "message"))

    if intent_class == "TENANT" or "SHARED_RENTAL" in subtypes:
        expanded.observe_source(item, None, "buyer_only_reject_tenant")
        expanded.observe_query(item, None, "buyer_only_reject_tenant")
        return None, "buyer_only_reject_tenant"

    # Belt-and-suspenders protection: if the text is explicitly rental demand and
    # contains no purchase signal, reject it even if upstream intent was uncertain.
    if RENTAL_ONLY_RE.search(text) and not PURCHASE_RE.search(text):
        expanded.observe_source(item, None, "buyer_only_reject_rental_text")
        expanded.observe_query(item, None, "buyer_only_reject_rental_text")
        return None, "buyer_only_reject_rental_text"

    lead, reason = _ORIGINAL_CLASSIFY(item, cutoff)
    if lead and str(lead.get("intent_class") or "") != "BUYER":
        return None, "buyer_only_nonbuyer_guard"
    return lead, reason


expanded.base._classify = buyer_only_classify


def run():
    return expanded.run()


if __name__ == "__main__":
    run()
