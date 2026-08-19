import os
import re
from datetime import datetime, timedelta, timezone
import main
import world_hard_filters

# Clean production engine.
# Discovery is broad (7 days); freshness is resolved from page timestamps and
# then the final 24h buyer filter is applied. The engine deliberately accepts
# short but genuine first-person buyer posts: forum pages do not all expose
# "member/reply" metadata in Exa's extracted text.


def resolved_published(item):
    now = datetime.now(timezone.utc)
    raw = str(item.get("text", ""))
    low = raw.lower()
    direct = main.parse_dt(item.get("published", ""))

    if re.search(r"\bjust now\b|\b\d+\s+minutes?\s+ago\b|\b\d+\s+hours?\s+ago\b", low, re.I):
        return now
    if re.search(r"\b(?:posted|published)\s+(?:today|this morning|this afternoon|this evening)\b", low, re.I):
        return now
    if re.search(r"\btoday\b", low, re.I) and not re.search(r"\b(?:report|news|article|analysis|guide)\b", low[:800], re.I):
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
        "author": "",
    } for x in response.json().get("results", [])]


main.SOURCE_BUCKETS = [
    {"name":"north_cyprus_turkey","domains":["reddit.com","expat.com","expatforum.com","nomadgate.com","t.me","tlgrm.ru","telega.io"],"query":"past 7 days real person first-person buyer discussion in North Cyprus Northern Cyprus Kuzey Kıbrıs Iskele Long Beach Girne Kyrenia Esentepe Gazimağusa Famagusta Bafra Tatlısu or Turkey Antalya Alanya Mersin Istanbul Izmir; wants to buy property apartment villa or investment property; budget property type target area viewing offer deposit mortgage payment legal/title question; English Turkish Russian; prioritize Reddit expat forums Telegram communities; exclude listings agents developers guides news company posts"},
    {"name":"montenegro_greece","domains":["reddit.com","expat.com","expatforum.com","montenegroexpats.com","internations.org","meetup.com","nomadgate.com","forum-eu.com"],"query":"past 7 days real person actively considering buying property second home investment property or relocating with purchase intention in Montenegro Budva Kotor Tivat Podgorica Bar or Greece Athens Thessaloniki Crete Rhodes Piraeus; first-person budget area property type viewing offer deposit financing lawyer purchase question; include Golden Visa and Russian English Greek discussions; exclude adverts guides articles news professionals"},
    {"name":"portugal_spain_italy_cyprus","domains":["reddit.com","expat.com","expatforum.com","forum-eu.com","nomadgate.com","bogleheads.org","t.me","tlgrm.ru"],"query":"past 7 days real person wanting to buy or compare property in Portugal Spain Italy or Republic of Cyprus; first-person budget target area property type timing or transaction question; Golden Visa/residency only when tied to a real purchase decision; English Portuguese Spanish Italian Greek Russian; exclude guides reports advisors agents listings"},
    {"name":"western_europe_uk","domains":["reddit.com","expat.com","expatforum.com","completefrance.com","pim.be","forum-eu.com","bogleheads.org","auswandererforum.de"],"query":"past 7 days real person discussing actual property purchase in Germany France Netherlands Belgium UK England Poland Czechia or Austria; first-person buyer intent with budget financing property/area viewing mortgage deposit offer or relocation with purchase intention; English German French Dutch Polish Czech; exclude news articles guides agencies listings"},
    {"name":"golden_visa_residency","domains":["nomadgate.com","bogleheads.org","expatforum.com","expat.com","reddit.com","forum-eu.com","t.me","tlgrm.ru","telega.io"],"query":"past 7 days real investor or family considering Golden Visa residency by investment or EU property-linked residency; Greece Portugal Italy Cyprus Malta Montenegro; real purchase/investment decision budget family target market trip lawyer payment eligibility; Italy non-real-estate investor route; exclude advisors guides news"},
    {"name":"russian_cis","domains":["reddit.com","forum.awd.ru","t.me","tlgrm.ru","telega.io","expat.com","forum-eu.com","internations.org"],"query":"past 7 days real Russian or Kazakh buyer looking to buy property abroad; include хочу купить ищу квартиру ищу недвижимость куплю недвижимость готов купить планирую купить бюджет переезд ВНЖ; Montenegro North Cyprus Greece Turkey Portugal Spain Italy Germany France EU; first-person budget location property timing transaction; exclude ads agents developers portals articles"},
]

main.exa_search = exa_search
main.verified_published = resolved_published

# Replace only the overly strict discussion gate. A genuine user post may have
# no visible reply/member metadata in Exa extraction, so buyer intent itself is
# the required gate; editorial, seller and rental filters remain intact.
def keep_candidate(item, cutoff):
    url = item.get("url", "")
    text = main.text_of(item)
    if not url or not main.source_is_user_generated(url):
        return False, "non_user_source"

    published = resolved_published(item)
    if published is None:
        return False, "date_unverified"
    if published < cutoff:
        return False, "older_than_24h"

    if main.editorial_likelihood(item) >= 3:
        return False, "editorial_or_article"

    discussion = main.discussion_likelihood(item)
    has_first_person = bool(re.search(r"\b(i|we|my|our|i'm|we're|i am|we are|ben|biz|benim|bizim|хочу|ищу|мы|мой|наш)\b", text, re.I))
    if discussion < 2 and not has_first_person:
        return False, "not_enough_user_discussion_signal"

    if main.contains_any(text, main.NEGATIVE_PHRASES) or main.contains_any(text, ["for rent", "kiralık", "сдам", "сдается"]):
        return False, "negative_or_rental"

    seller_hits = sum(1 for p in main.EXCLUDE_PHRASES if p.lower() in text)
    if seller_hits >= 2 and not has_first_person:
        return False, "seller_agent"

    if not main.contains_any(text, main.INTENT_PHRASES):
        return False, "no_buyer_intent"

    return True, "candidate"


main.keep_candidate = keep_candidate

if __name__ == "__main__":
    main.run()
