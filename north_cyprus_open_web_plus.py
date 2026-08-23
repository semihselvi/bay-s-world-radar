from urllib.parse import quote_plus

import north_cyprus_open_web as base

# Fresh research found real buyer discussions outside the usual expat/Telegram
# ecosystem, especially DonanimHaber (TR) and gutefrage (DE). Search-engine
# indexed Facebook-group posts are also useful without logging into Facebook.
EXTRA_DOMAINS = {
    "forum.donanimhaber.com",
    "gutefrage.net",
}
base.OPEN_WEB_ALLOWED_DOMAINS.update(EXTRA_DOMAINS)

EXTRA_BUYER_HINTS = [
    r"ev almak mant[ıi]kl[ıi] m[ıi]",
    r"k[ıi]br[ıi]s.*ev almak",
    r"yat[ıi]r[ıi]m ama[çc]l[ıi].*(?:konut|daire|ev)",
    r"haus kaufen",
    r"hauskauf",
    r"ich m[öo]chte.*haus kaufen",
    r"ich m[öo]chte.*immobilie kaufen",
    r"im ausland.*haus kaufen",
    r"nordzypern.*(?:haus|wohnung|immobilie).*kaufen",
    r"je souhaite acheter.*(?:bien|maison|appartement)",
    r"chypre du nord.*acheter",
    r"chc[ęe].*kupi[ćc].*(?:dom|mieszkanie|nieruchomo)",
]
for _pattern in EXTRA_BUYER_HINTS:
    if _pattern not in base.BUYER_HINT_PATTERNS:
        base.BUYER_HINT_PATTERNS.append(_pattern)

EXTRA_BING_QUERIES = [
    # Turkish investor forums. DonanimHaber has live 2026 property-investment threads.
    'site:forum.donanimhaber.com "Kuzey Kıbrıs" "ev almak"',
    'site:forum.donanimhaber.com "Kıbrıs" "ev almak mantıklı mı"',
    'site:forum.donanimhaber.com "Kıbrıs" "yatırım amaçlı konut"',
    'site:forum.donanimhaber.com "Kuzey Kıbrıs" "daire" yatırım',
    'site:forum.donanimhaber.com "Kıbrıs" "1+1" "yatırım"',
    # German Q&A/forum users can be very early-stage but reachable buyer prospects.
    'site:gutefrage.net Nordzypern "Haus kaufen"',
    'site:gutefrage.net Nordzypern Immobilie kaufen',
    'site:gutefrage.net Nordzypern Hauskauf',
    'site:gutefrage.net Ausland Haus kaufen Nordzypern',
    # Indexed public Facebook communities identified by TRNC expat directories.
    'site:facebook.com/groups/Cyprus.Expats "North Cyprus" "looking to buy"',
    'site:facebook.com/groups/442056586732126 "North Cyprus" property buy',
    'site:facebook.com/groups/592222764524379 "North Cyprus" property buy',
    'site:facebook.com/groups/1476173132433149 "property" "North Cyprus"',
    'site:facebook.com/groups/norzypfans Nordzypern Immobilie kaufen',
    'site:facebook.com/groups/1374986462651084 Nordzypern Immobilie',
    'site:facebook.com/groups/1666413366945901 Nordzypern Immobilie kaufen',
    'site:facebook.com/groups/702793716956237 "Cypr Północny" nieruchomości',
    '"North Cyprus Expats Group" "looking to buy" property',
    '"Deutsche auf Nord Zypern" Immobilie kaufen',
    '"Północny Cypr po polsku" nieruchomości kupić',
]
for _query in EXTRA_BING_QUERIES:
    if _query not in base.BING_QUERIES:
        base.BING_QUERIES.append(_query)


def _reddit_search(name, query, subreddit="", horizon="year"):
    q = quote_plus(query)
    if subreddit:
        url = f"https://www.reddit.com/r/{subreddit}/search.rss?q={q}&restrict_sr=on&sort=new&t={horizon}"
    else:
        url = f"https://www.reddit.com/search.rss?q={q}&sort=new&t={horizon}"
    return (name, url)


EXTRA_REDDIT_FEEDS = [
    _reddit_search("r/Finanzen Nordzypern", 'Nordzypern Immobilie', "Finanzen"),
    _reddit_search("Reddit global Nordzypern", 'Nordzypern Immobilie kaufen'),
    _reddit_search("Reddit global Chypre du Nord", '"Chypre du Nord" immobilier'),
    _reddit_search("Reddit global Cypr Polnocny", '"Cypr Północny" nieruchomości'),
    _reddit_search("Reddit global Severny Kipr", '"Северный Кипр" недвижимость'),
    _reddit_search("r/AskTurkey Kuzey Kibris", '"Kuzey Kıbrıs" ev', "AskTurkey"),
    ("r/KKTC new", "https://www.reddit.com/r/KKTC/new/.rss?limit=100"),
    ("r/KKTC comments", "https://www.reddit.com/r/KKTC/comments/.rss?limit=100"),
]

# Put new language/geography surfaces at the front so even a reduced pulse feed
# budget covers them. Dedupe by feed URL.
_seen = set()
_combined = []
for _item in EXTRA_REDDIT_FEEDS + list(base.REDDIT_FEEDS):
    if _item[1] in _seen:
        continue
    _seen.add(_item[1])
    _combined.append(_item)
base.REDDIT_FEEDS = _combined

# Re-export the live mutated objects expected by catcher_expanded.
OPEN_WEB_ALLOWED_DOMAINS = base.OPEN_WEB_ALLOWED_DOMAINS
BING_QUERIES = base.BING_QUERIES
BUYER_HINT_PATTERNS = base.BUYER_HINT_PATTERNS
REDDIT_FEEDS = base.REDDIT_FEEDS
collect_open_web = base.collect_open_web
