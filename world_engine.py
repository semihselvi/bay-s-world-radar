import os
import re
from datetime import datetime, timedelta, timezone
import main
import world_hard_filters

# World Radar clean engine:
# Exa discovers broadly; page text resolves coarse/misleading timestamps;
# main.py remains responsible for the final 24h buyer filtering/scoring.


def resolved_published(item):
    now = datetime.now(timezone.utc)
    raw = str(item.get("text", ""))
    low = raw.lower()
    direct = main.parse_dt(item.get("published", ""))

    # Prefer explicit relative timestamps embedded in the fetched page.
    if re.search(r"\bjust now\b|\b\d+\s+minutes?\s+ago\b|\b\d+\s+hours?\s+ago\b", low, re.I):
        return now
    if re.search(r"\b(?:posted|published)\s+(?:today|this morning|this afternoon|this evening)\b", low, re.I):
        return now

    # A plain "today" is useful when the page is clearly a post, but do not
    # turn an editorial article mentioning the word today into a fresh lead.
    if re.search(r"\btoday\b", low, re.I) and not re.search(r"\b(?:report|news|article|analysis|guide)\b", low[:800], re.I):
        return now

    # Explicit calendar date in page text can correct Exa's midnight stamp.
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


# Keep the six market buckets, but remove editorial-heavy discovery portals.
main.SOURCE_BUCKETS = [
    {"name":"north_cyprus_turkey","domains":["reddit.com","expat.com","expatforum.com","nomadgate.com","t.me","tlgrm.ru","telegid.me","telega.io"],"query":"past 7 days user discussion by a real person with first-person buyer intent for North Cyprus Northern Cyprus Kuzey Kıbrıs Iskele Long Beach Girne Kyrenia Esentepe Gazimağusa Famagusta Bafra Tatlısu or Turkey Antalya Alanya Mersin Istanbul Izmir; wants to buy property apartment villa or investment property; English Turkish Russian; budget property type target area viewing trip offer deposit mortgage payment or legal/title question; prioritize Reddit expat forums and Telegram communities; exclude listings agents developers guides news company posts"},
    {"name":"montenegro_greece","domains":["reddit.com","expat.com","expatforum.com","montenegroexpats.com","internations.org","meetup.com","nomadgate.com","forum-eu.com"],"query":"past 7 days real person actively considering buying property second home investment property or relocating with purchase intention in Montenegro Budva Kotor Tivat Podgorica Bar or Greece Athens Thessaloniki Crete Rhodes Piraeus; first-person budget area property type viewing offer deposit financing lawyer purchase-process question; include Golden Visa and Russian English Greek discussions; exclude adverts guides articles news professionals"},
    {"name":"portugal_spain_italy_cyprus","domains":["reddit.com","expat.com","expatforum.com","forum-eu.com","nomadgate.com","bogleheads.org","t.me","tlgrm.ru"],"query":"past 7 days user-generated discussion by a real person wanting to buy or compare property in Portugal Spain Italy or Republic of Cyprus; concrete budget target area property type timing or transaction question; Golden Visa or residency only when tied to a real purchase decision; English Portuguese Spanish Italian Greek Russian; exclude guides market reports advisors agents listings"},
    {"name":"western_europe_uk","domains":["reddit.com","expat.com","expatforum.com","completefrance.com","pim.be","forum-eu.com","bogleheads.org","auswandererforum.de"],"query":"past 7 days user discussion about an actual property purchase in Germany France Netherlands Belgium UK England Poland Czechia or Austria; real person first-person buyer intent concrete budget financing specific property or area viewing mortgage deposit offer or relocation with purchase intention; English German French Dutch Polish Czech; do not treat UK as Golden Visa; exclude news articles buyer guides agencies listings"},
    {"name":"golden_visa_residency","domains":["nomadgate.com","bogleheads.org","expatforum.com","expat.com","reddit.com","forum-eu.com","t.me","tlgrm.ru","telega.io"],"query":"past 7 days real investor or family considering Golden Visa residency by investment or EU property-linked residency; focus Greece Portugal Italy Cyprus Malta Montenegro; real purchase or investment decision budget family target market planned trip lawyer payment or eligibility; distinguish Italy non-real-estate investor route; do not count UK Germany France Netherlands Belgium as classic property Golden Visa; exclude advisors consultancy guides news"},
    {"name":"russian_cis","domains":["reddit.com","forum.awd.ru","t.me","tlgrm.ru","telega.io","expat.com","forum-eu.com","internations.org"],"query":"past 7 days real Russian or Kazakh buyer looking to buy property abroad; include хочу купить ищу квартиру ищу недвижимость куплю недвижимость готов купить планирую купить бюджет переезд ВНЖ; target Montenegro North Cyprus Greece Turkey Portugal Spain Italy Germany France or EU; first-person concrete budget location property timing transaction signal; exclude ads agents developers property portals articles"},
]

main.exa_search = exa_search
main.verified_published = resolved_published

if __name__ == "__main__":
    main.run()
