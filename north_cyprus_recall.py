import os

import main
import shard_runner
import north_cyprus_hunter  # configures the dedicated NC shard + notifications
import north_cyprus_focus as nf

# Maximum-recall lane for a slow market. This lane is intentionally more permissive
# than the normal Hunter, but still requires a fresh public/community post and
# rejects obvious rentals/seller spam. No extra Exa call is required by default.

# Project/development names matter because buyers often write only:
# "Caesar 2+1 var mı?" or "Grand Sapphire resale?" without saying North Cyprus.
PROJECT_CONTEXT_PATTERNS = [
    r"\bcaesar resort\b", r"\bcaesar blue\b", r"\bcaesar cliff\b", r"\bcaesar palm\b",
    r"\bgrand sapphire\b", r"\bgrand sapphire blu\b", r"\broyal sun\b",
    r"\briverside life\b", r"\bfour seasons life\b", r"\bcourtyard long beach\b",
    r"\bmaldives homes\b", r"\bk'?saba\b", r"\blagoon verde\b",
    r"\bhabitat\b", r"\be[- ]?volve\b",

    # Isatis Construction - official project family. Buyers often mention only
    # the project name, phase or developer in Telegram/Reddit requests.
    r"\bisatis\b", r"\bisatis construction\b", r"\bisatis in[şs]aat\b",
    r"\bisatis elysium\b", r"\belysium\s*2\b", r"\belysium ii\b", r"\belysium\b",
    r"\bisatis hillside\b", r"\bhillside isatis\b",
    r"\bisatis infinity\b", r"\binfinity isatis\b",
    r"\bisatis fiora\b", r"\bfiora isatis\b", r"\bfiora\b",
    r"\bisatis orchard\b", r"\borchard isatis\b", r"\bisatis orchard complex\b",

    r"\bnorthernland\b", r"\bdovec\b", r"\bdöveç\b", r"\bnoyanlar\b",
    r"\blong beach club resort\b", r"\bpark residence\b",
]

EXTRA_REQUEST_PATTERNS = [
    # Turkish short buyer requests
    r"\bar[ıi]yorum\b", r"\bar[ıi]yoruz\b", r"\blaz[ıi]m\b", r"\bihtiyac[ıi]m var\b",
    r"\bsahibinden ar[ıi]yorum\b", r"\bdevir ar[ıi]yorum\b", r"\bresale ar[ıi]yorum\b",
    r"\bacil ar[ıi]yorum\b", r"\bvarsa yaz(?:ın|in)\b", r"\bolan var m[ıi]\b",
    r"\bhangi projeyi öner", r"\bhangi projeyi oner", r"\bhangi firma güvenilir\b",
    r"\bhangi firma guvenilir\b", r"\bkaç para\b", r"\bkac para\b",
    r"\bsterline ne al", r"\bsterlin[e]? kadar\b", r"\bpe[şs]inatla ne al",
    r"\bisatis(?:te|'te|’te)? .*var m[ıi]\b", r"\belysium\s*2 .*var m[ıi]\b",
    r"\bfiora .*var m[ıi]\b", r"\bisatis .*fiyat\b", r"\belysium .*fiyat\b",
    # English terse requests
    r"\bneed (?:a |an )?(?:studio|flat|apartment|house|villa|1\+1|2\+1|3\+1)\b",
    r"\bwanted[: ]+(?:studio|flat|apartment|house|villa|1\+1|2\+1|3\+1)\b",
    r"\banyone selling\b", r"\bany owner selling\b", r"\bowner sale\b",
    r"\blooking for resale\b", r"\bany resale\b", r"\bwhat(?:'s| is) available\b",
    r"\banything (?:available|around|under)\b", r"\boptions? under\b",
    r"\bany isatis resale\b", r"\bisatis .*available\b", r"\belysium\s*2 .*available\b",
    # Russian terse requests
    r"\bнужна квартир", r"\bнужен апартамент", r"\bнужна вилл", r"\bкто продает\b",
    r"\bот собственника\b", r"\bищу вторичк", r"\bесть варианты\b",
    r"\bкакие варианты\b", r"\bчто есть до\b", r"\bчто есть за\b",
    r"\bisatis .*есть\b", r"\belysium\s*2 .*есть\b",
    # Arabic buyer intent
    r"أريد شراء", r"ابحث عن شقة", r"أبحث عن شقة", r"ابحث عن عقار", r"أبحث عن عقار",
    r"أبحث عن فيلا", r"اريد شقة", r"أريد شقة", r"ميزانيتي",
]

EXTRA_STRONG_PATTERNS = [
    r"\bsat[ıi]n alaca[ğg][ıi]m\b", r"\balmay[ıi] düşünüyorum\b", r"\balmayi dusunuyorum\b",
    r"\byat[ıi]r[ıi]ml[ıi]k bak[ıi]yorum\b", r"\byatirimlik bakiyorum\b",
    r"\bproperty hunting\b", r"\bready to purchase\b", r"\bwant a resale\b",
    r"\bхотел бы купить\b", r"\bхотела бы купить\b", r"\bхотим приобрести\b",
]

EXTRA_CONCRETE_PATTERNS = [
    r"\b\d{2,3}\s*(?:bin|thousand)\s*(?:sterlin|pound|gbp)?\b",
    r"\b(?:gbp|sterlin|pounds?)\s*\d", r"\b\d[\d,. ]*\s*(?:gbp|sterlin|pounds?)\b",
    r"\b\d{2,3}k\s*(?:gbp|pounds?|sterlin)?\b",
]

nf.NC_LOCATION_PATTERNS.extend(PROJECT_CONTEXT_PATTERNS)
nf.REQUEST_BUYER_PATTERNS.extend(EXTRA_REQUEST_PATTERNS)
nf.STRONG_BUYER_PATTERNS.extend(EXTRA_STRONG_PATTERNS)
nf.CONCRETE_PATTERNS.extend(EXTRA_CONCRETE_PATTERNS)

_base_keep = nf.keep_candidate
_base_score = nf.buyer_scores


def recall_keep_candidate(item, cutoff):
    keep, reason = _base_keep(item, cutoff)
    if keep:
        return True, reason

    # Rescue very terse but commercially useful requests such as:
    # "Long Beach £100k, anything?" / "Kıbrıs 80 bin sterlin ne alabilirim?"
    # They may not contain a literal property noun but are still real buyer requests.
    if reason not in ("no_buyer_intent", "not_enough_user_discussion_signal"):
        return False, reason

    if not item.get("url") or not nf._allowed_source(item):
        return False, reason
    published = nf.world_engine.resolved_published(item)
    if published is None or published < cutoff:
        return False, reason

    text = nf._text(item)
    if not nf._nc_context(item, text):
        return False, reason
    if nf._matches(text, nf.RENTAL_PATTERNS):
        return False, "negative_or_rental"

    seller_hits = sum(1 for phrase in nf.SELLER_PATTERNS if phrase.lower() in text.lower())
    request = nf._matches(text, nf.REQUEST_BUYER_PATTERNS)
    strong = nf._matches(text, nf.STRONG_BUYER_PATTERNS)
    early = nf._matches(text, nf.EARLY_BUYER_PATTERNS)
    concrete = nf._matches(text, nf.CONCRETE_PATTERNS)

    if seller_hits >= 2 and not strong:
        return False, "seller_agent"

    # High recall rescue: NC/project context + a real request + money/transaction signal.
    if concrete and (request or strong or early):
        return True, "candidate_recall_rescue"

    return False, reason


def recall_buyer_scores(item):
    intent, credibility, fit, label = _base_score(item)
    if label in ("HOT", "WARM"):
        return intent, credibility, fit, label

    text = nf._text(item)
    if not nf._nc_context(item, text):
        return intent, credibility, fit, label

    request = nf._matches(text, nf.REQUEST_BUYER_PATTERNS)
    strong = nf._matches(text, nf.STRONG_BUYER_PATTERNS)
    early = nf._matches(text, nf.EARLY_BUYER_PATTERNS)
    concrete = nf._matches(text, nf.CONCRETE_PATTERNS)

    if concrete and (request or strong or early):
        # Surface it to Telegram rather than silently discarding it.
        return max(intent, 68), max(credibility, 62), max(fit, 90), "WARM"

    return intent, credibility, fit, label


main.keep_candidate = recall_keep_candidate
main.buyer_scores = recall_buyer_scores

if __name__ == "__main__":
    os.environ["WORLD_RADAR_SHARD"] = "north_cyprus_hunter"
    shard_runner.SHARD = "north_cyprus_hunter"
    shard_runner.run()
