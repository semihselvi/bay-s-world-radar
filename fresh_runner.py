import os
from datetime import datetime, timedelta, timezone
import main

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
    response = main.SESSION.post(main.EXA_URL, json=payload, headers={"x-api-key": api_key, "Content-Type": "application/json"}, timeout=35)
    if response.status_code != 200:
        print("EXA_ERROR", response.status_code, response.text[:350])
        return []
    return [{"source":"Exa","url":x.get("url",""),"title":x.get("title",""),"text":x.get("text",""),"published":x.get("publishedDate",""),"author":""} for x in response.json().get("results", [])]

main.exa_search = fresh_exa_search
main.verified_published = fresh_verified_published

main.SOURCE_BUCKETS = [
    {"name":"fresh_north_cyprus_turkey","domains":["reddit.com","facebook.com","t.me","tlgrm.ru","telegid.me","telega.io","expat.com","expatforum.com","nomadgate.com","cyprusliving.org"],"query":"past 24 hours newly posted user discussion, real person, active buyer intent: looking to buy property, apartment, villa, house or investment property in North Cyprus Northern Cyprus Kuzey Kıbrıs İskele Iskele Long Beach Girne Kyrenia Esentepe Gazimağusa Famagusta Bafra Tatlısu or Turkey Antalya Alanya Mersin Istanbul Izmir; English Turkish Russian; require personal first-person language, budget, property requirements, viewing trip, offer, deposit, mortgage, payment plan or legal/title question; prioritize newly posted forum/reddit/public facebook/telegram discussions; exclude listings, agents, developers, guides and news"},
    {"name":"fresh_montenegro_greece","domains":["reddit.com","facebook.com","t.me","telegid.me","expat.com","expatforum.com","montenegroexpats.com","internations.org","meetup.com","forum-eu.com"],"query":"new discussion posted today or within the last 24 hours by a real person actively considering buying property, second home, investment property or relocating with purchase intention in Montenegro Budva Kotor Tivat Podgorica Bar or Greece Athens Thessaloniki Crete Rhodes Piraeus; include Golden Visa questions; look for first-person budget, area choice, property type, planned viewing, offer, deposit, financing, lawyer or purchase-process questions; English Russian Greek; exclude property adverts, agency pages, guides, articles and news"},
    {"name":"fresh_portugal_spain_italy_cyprus","domains":["reddit.com","facebook.com","t.me","expat.com","expatforum.com","forum-eu.com","nomadgate.com","bogleheads.org"],"query":"fresh user-generated posts from the past 24 hours: real person saying they want to buy, are looking to buy, are planning to buy, are comparing areas or are planning a property viewing in Portugal Spain Italy Republic of Cyprus; include Golden Visa or residency-by-investment only when tied to concrete property or investment intent; require personal circumstances, budget, target area, property type, timing or transaction question; English Portuguese Spanish Italian Greek Russian; exclude evergreen guides, market reports, SEO articles, agents and listings"},
    {"name":"fresh_western_europe_uk","domains":["reddit.com","facebook.com","expat.com","expatforum.com","property118.com","housepricecrash.co.uk","moneysavingexpert.com","completefrance.com","finary.com","pim.be"],"query":"new user discussion in the last 24 hours about an actual property purchase in Germany France Netherlands Belgium UK England Poland Czechia or Austria; real person, first-person buyer intent, concrete budget or financing, specific property or area, viewing, mortgage, deposit, offer, relocation with purchase intention; English German French Dutch Polish Czech; do not treat UK as Golden Visa; exclude news, articles, buyer guides, agencies and property listings"},
    {"name":"fresh_golden_visa_residency","domains":["nomadgate.com","bogleheads.org","expatforum.com","expat.com","reddit.com","facebook.com","forum-eu.com","t.me","tlgrm.ru","telega.io"],"query":"newly posted discussion within the last 24 hours by a real investor or family actively considering Golden Visa, residency by investment or an EU property-linked residency route; focus Greece Portugal Italy Cyprus Malta Montenegro and other valid programmes; require a real purchase or investment decision, budget, family, target market, planned trip, lawyer, payment or eligibility question; distinguish Italy non-real-estate investor route; do not count UK Germany France Netherlands Belgium as classic property Golden Visa; exclude advisors, consultancy content, guides and news"},
    {"name":"fresh_russian_cis","domains":["reddit.com","forum.awd.ru","prian.ru","realting.com","t.me","tlgrm.ru","telega.io","facebook.com","expat.com","forum-eu.com","internations.org"],"query":"пост или обсуждение за последние 24 часа, реальный человек хочет купить недвижимость, ищет квартиру, ищет виллу, хочет дом, планирует покупку или переезд с покупкой; Russian or Kazakh buyers looking abroad in Montenegro Северный Кипр Kuzey Kıbrıs, Greece, Turkey, Portugal, Spain, Italy, Germany, France or EU; include хочу купить, ищу квартиру, ищу недвижимость, куплю недвижимость, готов купить, планирую купить, бюджет, переезд, ВНЖ, плюс Алматы Астана; require first-person concrete budget/location/property/timing/transaction signal; exclude advertisements, agents, developers, portals and articles"},
]

if __name__ == "__main__":
    main.run()
