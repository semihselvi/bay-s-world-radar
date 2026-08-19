import os
from datetime import datetime, timedelta, timezone
import main
import world_hard_filters

# World Radar freshness policy: only Exa's explicit publishedDate is accepted.
def fresh_verified_published(item):
    value = item.get("published", "")
    if not value:
        return None
    return main.parse_dt(value)


def fresh_exa_search(query, domains):
    api_key = os.getenv("EXA_API_KEY", "").strip()
    if not api_key:
        print("EXA_DISABLED missing EXA_API_KEY")
        return []
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=int(os.getenv("WORLD_LOOKBACK_HOURS", "24")))
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
    return [
        {
            "source": "Exa",
            "url": x.get("url", ""),
            "title": x.get("title", ""),
            "text": x.get("text", ""),
            "published": x.get("publishedDate", ""),
            "author": "",
        }
        for x in response.json().get("results", [])
    ]


main.exa_search = fresh_exa_search
main.verified_published = fresh_verified_published

# Six market buckets. Editorial-heavy portals are deliberately kept OUT of direct discovery
# because Exa otherwise fills the bucket with their news/articles instead of user discussions.
main.SOURCE_BUCKETS = [
    {
        "name": "fresh_north_cyprus_turkey",
        "domains": ["reddit.com","expat.com","expatforum.com","nomadgate.com","t.me","tlgrm.ru","telegid.me","telega.io"],
        "query": "past 24 hours newly posted forum or community discussion by a real person with first-person buyer intent for North Cyprus Northern Cyprus Kuzey Kıbrıs Iskele Long Beach Girne Kyrenia Esentepe Gazimağusa Famagusta Bafra Tatlısu or Turkey Antalya Alanya Mersin Istanbul Izmir; wants to buy property, apartment, villa or investment property; include English Turkish Russian; require budget, property type, target area, viewing trip, offer, deposit, mortgage, payment or legal/title question; prioritize Reddit, expat forums and Telegram community discussions; exclude listings, agents, developers, guides, news and company posts"
    },
    {
        "name": "fresh_montenegro_greece",
        "domains": ["reddit.com","expat.com","expatforum.com","montenegroexpats.com","internations.org","meetup.com","nomadgate.com","forum-eu.com"],
        "query": "new discussion within last 24 hours by a real person actively considering buying property, second home, investment property or relocating with purchase intention in Montenegro Budva Kotor Tivat Podgorica Bar or Greece Athens Thessaloniki Crete Rhodes Piraeus; first-person budget, area choice, property type, viewing, offer, deposit, financing, lawyer or purchase-process question; include Golden Visa questions and Russian English Greek discussions; exclude property adverts, guides, articles, news and professionals"
    },
    {
        "name": "fresh_portugal_spain_italy_cyprus",
        "domains": ["reddit.com","expat.com","expatforum.com","forum-eu.com","nomadgate.com","bogleheads.org","t.me","tlgrm.ru"],
        "query": "fresh user-generated posts from the past 24 hours by a real person saying they want to buy, are looking to buy, are planning to buy, are comparing areas or are planning a property viewing in Portugal Spain Italy or Republic of Cyprus; concrete budget, target area, property type, timing or transaction question; Golden Visa or residency only when tied to a real purchase decision; English Portuguese Spanish Italian Greek Russian; exclude evergreen guides, market reports, advisors, agents and listings"
    },
    {
        "name": "fresh_western_europe_uk",
        "domains": ["reddit.com","expat.com","expatforum.com","completefrance.com","pim.be","forum-eu.com","bogleheads.org","auswandererforum.de"],
        "query": "new user discussion in the last 24 hours about an actual property purchase in Germany France Netherlands Belgium UK England Poland Czechia or Austria; real person, first-person buyer intent, concrete budget or financing, specific property or area, viewing, mortgage, deposit, offer or relocation with purchase intention; English German French Dutch Polish Czech; do not treat UK as Golden Visa; exclude news, articles, buyer guides, agencies and property listings"
    },
    {
        "name": "fresh_golden_visa_residency",
        "domains": ["nomadgate.com","bogleheads.org","expatforum.com","expat.com","reddit.com","forum-eu.com","t.me","tlgrm.ru","telega.io"],
        "query": "newly posted discussion within the last 24 hours by a real investor or family actively considering Golden Visa, residency by investment or an EU property-linked residency route; focus Greece Portugal Italy Cyprus Malta Montenegro and other valid programmes; require a real purchase or investment decision, budget, family, target market, planned trip, lawyer, payment or eligibility question; distinguish Italy non-real-estate investor route; do not count UK Germany France Netherlands Belgium as classic property Golden Visa; exclude advisors, consultancy content, guides and news"
    },
    {
        "name": "fresh_russian_cis",
        "domains": ["reddit.com","forum.awd.ru","t.me","tlgrm.ru","telega.io","expat.com","forum-eu.com","internations.org"],
        "query": "discussion from last 24 hours by a real Russian or Kazakh buyer looking to buy property abroad; include хочу купить, ищу квартиру, ищу недвижимость, куплю недвижимость, готов купить, планирую купить, бюджет, переезд, ВНЖ; target Montenegro North Cyprus Greece Turkey Portugal Spain Italy Germany France or EU; require first-person concrete budget, location, property, timing or transaction signal; exclude ads, agents, developers, property portals and articles"
    },
]


if __name__ == "__main__":
    main.run()
