import os
import re
from datetime import datetime, timedelta, timezone
import main
import world_hard_filters

# BAY-S World Radar production engine.
# Exa is discovery only. Final lead acceptance is based on:
# freshness + user-generated source + first-person buyer intent + concrete purchase evidence.

BUYER_PATTERNS = [
    r"\blooking to buy\b", r"\bwant(?:ing)? to buy\b", r"\bplanning to buy\b",
    r"\bready to buy\b", r"\btrying to buy\b", r"\bconsidering buying\b",
    r"\bthinking (?:about|of) buying\b", r"\bhouse hunting\b", r"\bhomebuying\b",
    r"\blooking for (?:a |an )?(?:house|home|flat|apartment|villa|property)\b",
    r"\bmake an offer\b", r"\bput in an offer\b", r"\bmortgage pre[- ]?approved\b",
    r"\bdeposit (?:ready|saved)\b", r"\bcash buyer\b",
    r"\bev almak\b", r"\bev arıyorum\b", r"\bdaire arıyorum\b", r"\bsatın almak\b",
    r"\bgayrimenkul almak\b", r"\byatırım için (?:ev|daire|gayrimenkul)\b",
    r"\bхочу купить\b", r"\bищу квартиру\b", r"\bищу дом\b", r"\bищу виллу\b",
    r"\bищу недвижимость\b", r"\bкуплю недвижимость\b", r"\bпланирую купить\b",
    r"\bготов(?:а|ы)? купить\b",
]

PERSONAL_PATTERNS = [
    r"\bI\b", r"\bI'm\b", r"\bI am\b", r"\bmy\b", r"\bwe\b", r"\bwe're\b",
    r"\bwe are\b", r"\bour\b", r"\bben\b", r"\bbiz\b", r"\bbenim\b", r"\bbizim\b",
    r"\bхочу\b", r"\bищу\b", r"\bмой\b", r"\bнаш\b", r"\bмы\b",
]

CONCRETE_PATTERNS = [
    r"(?:€|£|\$|₺|₽|AED\s*)\s?\d[\d,.\s]*(?:k|m)?",
    r"\b\d{2,3}\s?[km]\b", r"\bbudget\b", r"\bbütçe\b", r"\bбюджет\b",
    r"\bdeposit\b", r"\bmortgage\b", r"\bpre[- ]?approv", r"\bviewing\b",
    r"\boffer\b", r"\blawyer\b", r"\btitle deed\b", r"\bpayment plan\b",
    r"\bcompletion\b", r"\bclosing costs?\b", r"\bипотек", r"\bвзнос\b",
    r"\bкапитал\b", r"\bnakit\b", r"\bcash\b",
]

PROPERTY_PATTERNS = [
    r"\bproperty\b", r"\bhouse\b", r"\bhome\b", r"\bflat\b", r"\bapartment\b",
    r"\bvilla\b", r"\btownhouse\b", r"\bland\b", r"\be[vı]\b", r"\bdaire\b",
    r"\bgayrimenkul\b", r"\bквартир", r"\bдом\b", r"\bвилл", r"\bнедвижимост",
]


def resolved_published(item):
    now = datetime.now(timezone.utc)
    raw = str(item.get("text", ""))
    low = raw.lower()
    direct = main.parse_dt(item.get("published", ""))

    # Relative timestamps embedded in a genuine post are stronger than Exa's day-level timestamp.
    rel = re.search(r"\bjust now\b|\b(\d+)\s+minutes?\s+ago\b|\b(\d+)\s+hours?\s+ago\b", low, re.I)
    if rel:
        return now
    if re.search(r"\b(?:posted|published)\s+(?:today|this morning|this afternoon|this evening)\b", low, re.I):
        return now
    if re.search(r"\btoday\b", low, re.I) and not re.search(r"\b(?:report|news|article|analysis|guide)\b", low[:900], re.I):
        return now

    dates = main.extract_dates_from_text(raw)
    if dates:
        latest = max(dates)
        if latest <= now and latest >= now - timedelta(days=7):
            if direct is None or latest > direct:
                return latest
    return direct


def exa_search(query, domains):
    api_key = os.getenv("EXA_API_KEY", "").strip()
    if not api_key:
        print("EXA_DISABLED missing EXA_API_KEY")
        return []

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    payload = {
        "query": query,
        "type": "auto",
        "numResults": min(main.EXA_NUM_RESULTS, 15),
        "includeDomains": domains,
        "startPublishedDate": start.isoformat().replace("+00:00", "Z"),
        "endPublishedDate": now.isoformat().replace("+00:00", "Z"),
        "contents": {"text": True},
    }
    response = main.SESSION.post(
        main.EXA_URL,
        json=payload,
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        timeout=35,
    )
    if response.status_code != 200:
        print("EXA_ERROR", response.status_code, response.text[:350])
        return []

    return [{
        "source": "Exa",
        "url": x.get("url", ""),
        "title": x.get("title", ""),
        "text": x.get("text", ""),
        "published": x.get("publishedDate", ""),
        "author": x.get("author", "") or "",
    } for x in response.json().get("results", [])]


main.SOURCE_BUCKETS = [
    {"name":"north_cyprus_turkey","domains":["reddit.com","expat.com","expatforum.com","nomadgate.com","t.me","tlgrm.ru","telega.io"],"query":"past 7 days real person first-person buyer discussion in North Cyprus Northern Cyprus Kuzey Kıbrıs Iskele Long Beach Girne Kyrenia Esentepe Gazimağusa Famagusta Bafra Tatlısu or Turkey Antalya Alanya Mersin Istanbul Izmir; wants to buy property apartment villa or investment property; budget property type target area viewing offer deposit mortgage payment legal/title question; English Turkish Russian; prioritize Reddit expat forums Telegram communities; exclude listings agents developers guides news company posts"},
    {"name":"montenegro_greece","domains":["reddit.com","expat.com","expatforum.com","montenegroexpats.com","internations.org","meetup.com","nomadgate.com","forum-eu.com"],"query":"past 7 days real person actively considering buying property second home investment property or relocating with purchase intention in Montenegro Budva Kotor Tivat Podgorica Bar or Greece Athens Thessaloniki Crete Rhodes Piraeus; first-person budget area property type viewing offer deposit financing lawyer purchase question; include Golden Visa and Russian English Greek discussions; exclude adverts guides articles news professionals"},
    {"name":"portugal_spain_italy_cyprus","domains":["reddit.com","expat.com","expatforum.com","forum-eu.com","nomadgate.com","bogleheads.org","t.me","tlgrm.ru"],"query":"past 7 days real person wanting to buy or compare property in Portugal Spain Italy or Republic of Cyprus; first-person budget target area property type timing or transaction question; Golden Visa residency only when tied to a real purchase decision; English Portuguese Spanish Italian Greek Russian; exclude guides reports advisors agents listings"},
    {"name":"western_europe_uk","domains":["reddit.com","expat.com","expatforum.com","completefrance.com","pim.be","forum-eu.com","bogleheads.org","auswandererforum.de"],"query":"past 7 days real person discussing actual property purchase in Germany France Netherlands Belgium UK England Poland Czechia or Austria; first-person buyer intent with budget financing property area viewing mortgage deposit offer or relocation with purchase intention; English German French Dutch Polish Czech; exclude news articles guides agencies listings"},
    {"name":"golden_visa_residency","domains":["nomadgate.com","bogleheads.org","expatforum.com","expat.com","reddit.com","forum-eu.com","t.me","tlgrm.ru","telega.io"],"query":"past 7 days real investor or family considering Golden Visa residency by investment or EU property-linked residency; Greece Portugal Italy Cyprus Malta Montenegro; real purchase investment decision budget family target market trip lawyer payment eligibility; Italy non-real-estate investor route; exclude advisors guides news"},
    {"name":"russian_cis","domains":["reddit.com","forum.awd.ru","t.me","tlgrm.ru","telega.io","expat.com","forum-eu.com","internations.org"],"query":"past 7 days real Russian or Kazakh buyer looking to buy property abroad; include хочу купить ищу квартиру ищу недвижимость куплю недвижимость готов купить планирую купить бюджет переезд ВНЖ; Montenegro North Cyprus Greece Turkey Portugal Spain Italy Germany France EU; first-person budget location property timing transaction; exclude ads agents developers portals articles"},
]


def has_pattern(text, patterns):
    return any(re.search(p, text, flags=re.I) for p in patterns)


def count_patterns(text, patterns):
    return sum(1 for p in patterns if re.search(p, text, flags=re.I))


def buyer_evidence(item):
    text = main.text_of(item)
    personal = has_pattern(text, PERSONAL_PATTERNS)
    buyer = has_pattern(text, BUYER_PATTERNS)
    concrete = has_pattern(text, CONCRETE_PATTERNS)
    property_signal = has_pattern(text, PROPERTY_PATTERNS)
    discussion = main.discussion_likelihood(item)
    return text, personal, buyer, concrete, property_signal, discussion


def keep_candidate(item, cutoff):
    url = item.get("url", "")
    if not url or not main.source_is_user_generated(url):
        return False, "non_user_source"

    published = resolved_published(item)
    if published is None:
        return False, "date_unverified"
    if published < cutoff:
        return False, "older_than_24h"

    if main.editorial_likelihood(item) >= 3:
        return False, "editorial_or_article"

    text, personal, buyer, concrete, property_signal, discussion = buyer_evidence(item)

    if main.contains_any(text, main.NEGATIVE_PHRASES) or main.contains_any(text, ["for rent", "kiralık", "сдам", "сдается"]):
        return False, "negative_or_rental"

    seller_hits = sum(1 for p in main.EXCLUDE_PHRASES if p.lower() in text)
    if seller_hits >= 2 and not (personal and buyer):
        return False, "seller_agent"

    # Core rule: do not demand forum UI metadata. Demand a real person + actual buying language.
    if not personal:
        return False, "not_enough_user_discussion_signal"
    if not buyer:
        return False, "no_buyer_intent"
    if not property_signal:
        return False, "no_buyer_intent"

    # A short genuine buyer post is valid even without a visible budget. Concrete evidence improves scoring.
    return True, "candidate"


def buyer_scores(item):
    text, personal, buyer, concrete, property_signal, discussion = buyer_evidence(item)
    if not personal or not buyer or not property_signal:
        return 0, 0, 0, "COLD"

    buyer_hits = count_patterns(text, BUYER_PATTERNS)
    concrete_hits = count_patterns(text, CONCRETE_PATTERNS)
    property_hits = count_patterns(text, PROPERTY_PATTERNS)

    intent = 58 + min(24, buyer_hits * 8) + min(12, concrete_hits * 4) + min(6, property_hits * 2)
    credibility = 62 + min(16, discussion * 3) + (8 if concrete else 0) + (5 if item.get("author") else 0)
    fit = 62 if item.get("market", "unknown") != "unknown" else 52
    if concrete:
        fit += 8
    if property_hits >= 2:
        fit += 4

    intent = min(100, intent)
    credibility = min(100, credibility)
    fit = min(100, fit)

    # HOT requires stronger commercial evidence; WARM accepts a genuine fresh buyer post.
    if intent >= 82 and credibility >= 72 and fit >= 68 and concrete:
        label = "HOT"
    elif intent >= 68 and credibility >= 62 and fit >= 60:
        label = "WARM"
    else:
        label = "REVIEW"

    return intent, credibility, fit, label


main.exa_search = exa_search
main.verified_published = resolved_published
main.keep_candidate = keep_candidate
main.buyer_scores = buyer_scores

if __name__ == "__main__":
    main.run()
