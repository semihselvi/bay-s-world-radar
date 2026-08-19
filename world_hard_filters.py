import re
import main

HYBRID_ARTICLE_DOMAINS = {"property118.com", "housepricecrash.co.uk", "moneysavingexpert.com", "finary.com"}
ARTICLE_URL_MARKERS = ("/article", "/articles/", "/news/", "/blog/", "/analysis/", "/insights/", "/press/", "/opinion/", "/commentary/")


def _domain(url):
    return main.domain_of(url)


def _forum_path_ok(item):
    url = (item.get("url") or "").lower()
    d = _domain(url)
    if d == "property118.com":
        return "/forum" in url or "/forums" in url
    if d == "housepricecrash.co.uk":
        return "/forum" in url or "/forums" in url
    if d == "moneysavingexpert.com":
        return "/forum" in url or "/categories/" in url
    if d == "finary.com":
        return "/community/" in url
    return True


def looks_like_editorial(item):
    url = (item.get("url") or "").lower()
    title = str(item.get("title") or "").lower()
    text = main.text_of(item)

    if _domain(url) in HYBRID_ARTICLE_DOMAINS and not _forum_path_ok(item):
        return True
    if any(marker in url for marker in ARTICLE_URL_MARKERS):
        return True

    editorial_terms = (
        "guide", "requirements", "cheatsheet", "market report", "investor visa",
        "residence by investment", "property market", "analysis", "overview",
        "explained", "editorial", "non-dom", "non dom"
    )
    score = sum(1 for term in editorial_terms if term in text or term in title)
    forum_ui = any(x in text for x in ("post new topic", "member since", "reply", "replies"))
    if len(str(item.get("text") or "")) > 2500 and not forum_ui:
        score += 2
    return score >= 2


def market_for(text, bucket_name="", url="", title=""):
    u = (url or "").lower()
    t = (title or "").lower()
    combined = f"{t} {text.lower()}"
    explicit = {
        "greece": ("/greece/", "greece forum", "greek real estate", "greek golden visa", "athens", "thessaloniki"),
        "montenegro": ("/montenegro/", "montenegro forum", "budva", "kotor", "tivat"),
        "portugal": ("/portugal/", "portugal golden visa", "lisbon", "algarve"),
        "spain": ("/spain/", "spain property", "malaga", "marbella", "alicante"),
        "italy": ("/italy/", "italy property", "italian golden visa", "rome", "milan"),
        "cyprus": ("/cyprus/", "republic of cyprus", "paphos", "limassol", "larnaca"),
        "north_cyprus": ("north cyprus", "northern cyprus", "kuzey kibris", "trnc", "iskele", "long beach", "girne", "kyrenia", "gazimagusa", "famagusta"),
        "turkey": ("/turkey/", "turkey property", "antalya", "alanya", "mersin", "istanbul", "izmir"),
        "germany": ("/germany/", "german property", "deutschland", "berlin", "munich", "frankfurt"),
        "netherlands": ("/netherlands/", "dutch property", "amsterdam", "rotterdam", "utrecht"),
        "belgium": ("/belgium/", "belgian property", "brussels", "antwerp", "ghent"),
        "france": ("/france/", "french property", "paris", "nice", "cannes"),
        "lithuania": ("/lithuania/", "lithuanian property", "vilnius", "kaunas", "klaipeda"),
        "kazakhstan": ("/kazakhstan/", "kazakhstan", "almaty", "астана", "astana"),
        "russia": ("/russia/", "россия", "москва", "санкт-петербург"),
        "uk": ("/united-kingdom/", "/uk/", "united kingdom", "london", "manchester", "birmingham", "leeds"),
        "poland": ("/poland/", "poland", "warsaw", "krakow", "gdansk"),
        "czech_republic": ("/czech-republic/", "czechia", "prague", "brno"),
        "austria": ("/austria/", "austria", "vienna", "salzburg", "innsbruck"),
    }
    for market, markers in explicit.items():
        if any(marker in u or marker in t for marker in markers):
            return market

    scores = {m: 0 for m in main.MARKETS}
    for market, terms in main.MARKETS.items():
        for term in terms:
            if term.lower() in combined:
                scores[market] += 1
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked or ranked[0][1] == 0:
        return "unknown"
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return "unknown"
    return ranked[0][0]


def keep_candidate(item, cutoff):
    url = item.get("url", "")
    text = main.text_of(item)
    if not url or not main.source_is_user_generated(url):
        return False, "non_user_source"

    published = main.verified_published(item)
    if published is None:
        return False, "date_unverified"
    if published < cutoff:
        return False, "older_than_24h"
    if looks_like_editorial(item):
        return False, "editorial_or_article"

    # Require a real discussion structure, not just article-like buyer wording.
    discussion = main.discussion_likelihood(item)
    first_person = any(p in text for p in (
        "i want", "i'm looking", "i am looking", "we want", "we're looking", "we are looking",
        "my budget", "our budget", "ben", "biz", "хочу", "ищу", "бюджет"
    ))
    if discussion < 4 or not first_person:
        return False, "not_enough_user_discussion_signal"

    if main.contains_any(text, main.NEGATIVE_PHRASES) or main.contains_any(text, ["for rent", "kiralık", "сдам", "сдается"]):
        return False, "negative_or_rental"

    seller_hits = sum(1 for p in main.EXCLUDE_PHRASES if p.lower() in text)
    if seller_hits >= 2 and not first_person:
        return False, "seller_agent"
    if not main.contains_any(text, main.INTENT_PHRASES):
        return False, "no_buyer_intent"
    return True, "candidate"


main.looks_like_editorial = looks_like_editorial
main.market_for = market_for
main.keep_candidate = keep_candidate
