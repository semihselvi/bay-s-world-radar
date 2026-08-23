import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup

import main
import source_crawler_v2

OPEN_WEB_ALLOWED_DOMAINS = {
    "reddit.com", "old.reddit.com", "expat.com", "expatforum.com", "kibkomnorthcyprusforum.com",
    "forum.awd.ru", "britishexpats.com", "tripadvisor.com", "tripadvisor.co.uk", "turkishliving.com",
    "facebook.com", "t.me", "vk.com", "ok.ru", "dzen.ru", "pikabu.ru", "vc.ru", "quora.com",
    "threads.net", "x.com", "twitter.com",
    # Public web mirrors/directories of Telegram discussions. These expose dated
    # user messages and handles that normal search engines can index.
    "new.cy", "kiprinfo.ru", "ru.intelegram.one",
}

BING_QUERIES = [
    '"North Cyprus" "looking to buy" property', '"North Cyprus" "looking for" apartment property',
    '"Northern Cyprus" "want to buy" apartment', '"North Cyprus" resale "price" apartment',
    '"North Cyprus" "private owner" villa', '"North Cyprus" "owner direct" property',
    '"North Cyprus" "wanted" villa', '"North Cyprus" "cash buyer" property',
    '"Long Beach" Cyprus "looking for" apartment', '"Long Beach" Cyprus resale 1+1 2+1',
    '"Iskele" Cyprus "looking to buy"', '"Kuzey Kıbrıs" "daire arıyorum"',
    '"Kuzey Kıbrıs" "ev almak istiyorum"', '"İskele" "daire arıyorum"',
    '"Kuzey Kıbrıs" sahibinden arıyorum', '"İskele" sahibinden villa arıyorum',
    '"Boğaz" İskele villa arıyorum', '"Ötüken" villa arıyorum', '"Yeniboğaziçi" villa arıyorum',
    '"Северный Кипр" "ищу квартиру"', '"Северный Кипр" "хочу купить" недвижимость',
    '"Северный Кипр" "нужна квартира"', '"Северный Кипр" "ищу на покупку"',
    '"Северный Кипр" "срочно ищу" виллу', '"Северный Кипр" "только от собственника"',
    '"Искеле" "ищу виллу"', '"Искеле" "от собственника" вилла',
    '"Боаз" "ищу виллу"', '"Богаз" "ищу виллу"', '"Отюкен" "ищу виллу"',
    '"Йени Боазичи" "ищу виллу"', '"Северный Кипр" рассрочка квартира',
    '"Северный Кипр" вторичка недвижимость', '"Nordzypern" "Wohnung kaufen"',
    '"Nordzypern" "Immobilie kaufen"', '"Chypre du Nord" "acheter appartement"',
    '"Noord-Cyprus" "woning kopen"', '"Cypr Północny" "szukam mieszkania"',
    '"Cypr Północny" "chcę kupić" nieruchomość', '"Північний Кіпр" "шукаю квартиру"',
    '"Північний Кіпр" "хочу купити" нерухомість', '"شمال قبرص" "أبحث عن شقة"',
    '"شمال قبرص" "أريد شراء" عقار', '"צפון קפריסין" דירה לקנות',
    'site:reddit.com "North Cyprus" property buy', 'site:facebook.com/groups "North Cyprus" property wanted',
    'site:vk.com "Северный Кипр" "ищу квартиру"', 'site:ok.ru "Северный Кипр" "ищу квартиру"',
    'site:t.me "Северный Кипр" "ищу квартиру"', 'site:expat.com "North Cyprus" "looking for property"',
    # Search-engine indexed Telegram mirrors often preserve author + timestamp.
    'site:new.cy/tg "Северный Кипр" "ищу" недвижимость',
    'site:new.cy/tg Искеле "ищу" виллу',
    'site:kiprinfo.ru/tg "Северный Кипр" "ищу" недвижимость',
    'site:kiprinfo.ru/tg Искеле "от собственника"',
    'site:ru.intelegram.one "Северный Кипр" недвижимость чат',
    '"Caesar Resort" resale wanted', '"Grand Sapphire" resale buyer', '"Isatis" Cyprus resale available',
    '"Elysium 2" Cyprus resale', '"Royal Sun" Long Beach resale',
]

BUYER_HINT_PATTERNS = [
    r"looking to buy", r"want to buy", r"looking for", r"planning to buy", r"considering buying",
    r"cash buyer", r"private owner", r"owner direct", r"wanted", r"price", r"resale", r"available",
    r"budget", r"1\+1", r"2\+1", r"3\+1",
    r"daire ar[ıi]yorum", r"ev almak", r"sat[ıi]n almak", r"sahibinden", r"var m[ıi]", r"fiyat",
    r"s[ıi]k[ıi] ar[ıi]yorum", r"villa ar[ıi]yorum",
    r"срочно\s+ищу", r"ищу\s+на\s+покупку", r"ищу квартир", r"ищу вилл", r"хочу купить",
    r"нужна квартир", r"куплю вилл", r"только\s+от\s+собственника", r"от\s+собственника",
    r"отдельно\s*стоящ", r"отдельностоящ", r"цена", r"рассроч", r"вторичк",
    r"wohnung kaufen", r"immobilie kaufen", r"acheter appartement", r"woning kopen",
    r"szukam mieszkania", r"chc[ęe] kupi[ćc]", r"шукаю квартир", r"хочу купити",
    r"أبحث عن شقة", r"أريد شراء", r"לקנות", r"מחפש",
]

MARKETING_PATTERNS = [
    r"contact us", r"call us", r"book a viewing", r"our properties", r"our project", r"estate agency",
    r"real estate agency", r"developer", r"starting from", r"limited offer", r"whatsapp", r"dm us", r"free consultation",
]

REDDIT_FEEDS = [
    ("r/NorthCyprus new", "https://www.reddit.com/r/NorthCyprus/new/.rss?limit=100"),
    ("r/NorthCyprus comments", "https://www.reddit.com/r/NorthCyprus/comments/.rss?limit=100"),
    ("r/cyprus North Cyprus search", "https://www.reddit.com/r/cyprus/search.rss?q=%22North%20Cyprus%22&restrict_sr=on&sort=new&t=week"),
    ("r/expats North Cyprus search", "https://www.reddit.com/r/expats/search.rss?q=%22North%20Cyprus%22&restrict_sr=on&sort=new&t=week"),
    ("r/ExpatFIRE North Cyprus search", "https://www.reddit.com/r/ExpatFIRE/search.rss?q=%22North%20Cyprus%22&restrict_sr=on&sort=new&t=month"),
    ("r/realestateinvesting North Cyprus search", "https://www.reddit.com/r/realestateinvesting/search.rss?q=%22North%20Cyprus%22&restrict_sr=on&sort=new&t=month"),
    ("r/IWantOut North Cyprus search", "https://www.reddit.com/r/IWantOut/search.rss?q=%22North%20Cyprus%22&restrict_sr=on&sort=new&t=month"),
    ("Reddit global Northern Cyprus", "https://www.reddit.com/search.rss?q=%22Northern%20Cyprus%22%20property&sort=new&t=week"),
]


def _domain(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _allowed_domain(url):
    d = _domain(url)
    return any(d == x or d.endswith("." + x) for x in OPEN_WEB_ALLOWED_DOMAINS)


def _plain_html(value):
    return " ".join(BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True).split())


def _buyer_shaped(text):
    hits = sum(1 for p in BUYER_HINT_PATTERNS if re.search(p, text or "", re.I))
    marketing = sum(1 for p in MARKETING_PATTERNS if re.search(p, text or "", re.I))
    if marketing >= 3 and hits <= 1:
        return False
    return hits >= 1


def _rotating(values, limit):
    if not values:
        return []
    limit = max(1, min(limit, len(values)))
    if limit >= len(values):
        return values[:]
    now = datetime.now(timezone.utc)
    slot = now.timetuple().tm_yday * 8 + now.hour // 3
    start = (slot * limit) % len(values)
    return [values[(start + i) % len(values)] for i in range(limit)]


def _fetch(url, timeout=18):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "application/rss+xml,application/atom+xml,text/xml,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ru;q=0.8,tr;q=0.7",
    }
    try:
        return main.SESSION.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except Exception as exc:
        print("OPEN_WEB_FETCH_EXCEPTION", url, exc)
        return None


def _parse_atom_feed(name, url):
    response = _fetch(url)
    if not response or response.status_code != 200:
        code = response.status_code if response is not None else "ERR"
        print(f"REDDIT_RSS_ERROR feed={name!r} status={code}")
        return []
    items = []
    try:
        root = ET.fromstring(response.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("a:entry", ns):
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            content = entry.findtext("a:content", default="", namespaces=ns) or ""
            summary = entry.findtext("a:summary", default="", namespaces=ns) or ""
            published = entry.findtext("a:updated", default="", namespaces=ns) or entry.findtext("a:published", default="", namespaces=ns) or ""
            link = ""
            for node in entry.findall("a:link", ns):
                href = node.attrib.get("href", "")
                rel = node.attrib.get("rel", "alternate")
                if href and rel in ("alternate", ""):
                    link = href
                    break
            if not link:
                node = entry.find("a:link", ns)
                link = node.attrib.get("href", "") if node is not None else ""
            author = entry.findtext("a:author/a:name", default="", namespaces=ns) or ""
            text = _plain_html(content or summary)
            if not link or not text:
                continue
            items.append({"source":"Reddit RSS","url":link,"title":title,"text":text[:8000],"published":published,"author":author,"source_bucket":f"reddit_rss_north_cyprus_{name.lower().replace(' ', '_')}"})
    except Exception as exc:
        print(f"REDDIT_RSS_PARSE_ERROR feed={name!r} {exc}")
    print(f"REDDIT_RSS_COUNT feed={name!r} items={len(items)}")
    return items


def collect_reddit_rss():
    mode = os.getenv("NC_OPEN_WEB_MODE", "pulse").strip().lower()
    limit_default = 8 if mode == "full" else 4
    feed_limit = max(1, min(len(REDDIT_FEEDS), int(os.getenv("NC_REDDIT_RSS_FEED_LIMIT", str(limit_default)))))
    feeds = REDDIT_FEEDS[:feed_limit] if mode == "full" else _rotating(REDDIT_FEEDS, feed_limit)
    out = {}
    for name, url in feeds:
        for item in _parse_atom_feed(name, url):
            out[item["url"]] = item
    print(f"REDDIT_RSS_COMPLETE feeds={len(feeds)} unique={len(out)}")
    return list(out.values())


def _resolve_page_date(url):
    try:
        item = source_crawler_v2.extract_page_item(url, "Open Web Date Probe", "", "open_web_date_probe", "north_cyprus")
        return item.get("published", "") if item else ""
    except Exception:
        return ""


def _parse_bing_rss(query, date_probe_budget):
    url = f"https://www.bing.com/search?q={quote_plus(query)}&format=rss"
    response = _fetch(url)
    if not response or response.status_code != 200:
        code = response.status_code if response is not None else "ERR"
        print(f"BING_RSS_ERROR query={query!r} status={code}")
        return [], date_probe_budget
    items = []
    try:
        root = ET.fromstring(response.text)
        for node in root.findall(".//item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            description = _plain_html(node.findtext("description") or "")
            published = (node.findtext("pubDate") or "").strip()
            text = f"{title} {description}".strip()
            if not link or not _allowed_domain(link) or not _buyer_shaped(text):
                continue
            if not published and date_probe_budget > 0:
                published = _resolve_page_date(link)
                date_probe_budget -= 1
            items.append({"source":"Bing RSS Open Web","url":link,"title":title,"text":description[:6500],"published":published,"author":"","source_bucket":"bing_rss_north_cyprus_buyer_discovery","discovery_query":query})
    except Exception as exc:
        print(f"BING_RSS_PARSE_ERROR query={query!r} {exc}")
    print(f"BING_RSS_COUNT query={query!r} items={len(items)}")
    return items, date_probe_budget


def collect_bing_rss():
    mode = os.getenv("NC_OPEN_WEB_MODE", "pulse").strip().lower()
    default_limit = 12 if mode == "full" else 5
    query_limit = max(1, min(20, int(os.getenv("NC_BING_RSS_QUERY_LIMIT", str(default_limit)))))
    queries = _rotating(BING_QUERIES, query_limit)
    date_probe_budget = 8 if mode == "full" else 3
    out = {}
    for query in queries:
        found, date_probe_budget = _parse_bing_rss(query, date_probe_budget)
        for item in found:
            out[item["url"]] = item
    print(f"BING_RSS_COMPLETE queries={len(queries)} unique={len(out)}")
    return list(out.values())


def collect_dynamic_community_pages():
    if os.getenv("NC_OPEN_WEB_MODE", "pulse").strip().lower() != "full":
        return []
    db = main.firestore_client()
    if not db:
        return []
    limit = max(1, min(50, int(os.getenv("NC_DYNAMIC_COMMUNITY_LIMIT", "24"))))
    out = []
    try:
        for doc in db.collection("bay_s_dynamic_sources").limit(100).stream():
            data = doc.to_dict() or {}
            if data.get("market") != "north_cyprus" or data.get("type") != "community_candidate":
                continue
            url = str(data.get("url", "")).strip()
            if not url or not _allowed_domain(url):
                continue
            item = source_crawler_v2.extract_page_item(url, "Dynamic North Cyprus Community", str(data.get("title", "")), "dynamic_community_replay", "north_cyprus")
            if item:
                out.append(item)
            if len(out) >= limit:
                break
    except Exception as exc:
        print("DYNAMIC_COMMUNITY_REPLAY_ERROR", exc)
    print(f"DYNAMIC_COMMUNITY_REPLAY count={len(out)}")
    return out


def collect_open_web():
    if os.getenv("NC_OPEN_WEB_ENABLED", "1").strip() != "1":
        return []
    items = []
    items.extend(collect_reddit_rss())
    items.extend(collect_bing_rss())
    items.extend(collect_dynamic_community_pages())
    unique = {}
    for item in items:
        key = item.get("url") or main.dedupe_key(item)
        unique[key] = item
    out = list(unique.values())
    print(f"OPEN_WEB_COMPLETE unique_items={len(out)}")
    return out
