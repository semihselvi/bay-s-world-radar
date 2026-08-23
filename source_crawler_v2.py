import os
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import main
import hybrid_engine
from source_registry import DISCOVERY_CATALOGS

# Additional live directories found during source research. These pages contain
# public t.me links and can grow the source universe without Exa/API cost.
EXTRA_DISCOVERY_CATALOGS = [
    {"name":"Emigrants 360 Cyprus", "url":"https://t.me/s/slavianskiy_forum", "market":"north_cyprus"},
    {"name":"NewCY Cyprus Chat Directory", "url":"https://new.cy/tg/1481055633/382446", "market":"north_cyprus"},
    {"name":"KiprInfo Cyprus Chat Mirror", "url":"https://kiprinfo.ru/tg/1481055633", "market":"north_cyprus"},
]
for _catalog in EXTRA_DISCOVERY_CATALOGS:
    if not any(x.get("name") == _catalog["name"] for x in DISCOVERY_CATALOGS):
        DISCOVERY_CATALOGS.append(_catalog)

DIRECT_LINK_LIMIT = int(os.getenv("WORLD_DIRECT_LINK_LIMIT", "16"))
CATALOG_CHANNEL_LIMIT = int(os.getenv("WORLD_CATALOG_CHANNEL_LIMIT", "10"))

BAD_PATH_BITS = (
    "/members/", "/member/", "/login", "/register", "/signup", "/account",
    "upload.php", "email-protection", "/privacy", "/terms", "/contact",
    "/search", "/tags/", "/users/", "javascript:", "mailto:",
)


def clean_text(value):
    return hybrid_engine.clean_text(value)


def _best_published(soup):
    candidates = []

    for selector, attr in [
        ('meta[property="article:published_time"]', "content"),
        ('meta[property="article:modified_time"]', "content"),
        ('meta[name="date"]', "content"),
        ('meta[name="pubdate"]', "content"),
    ]:
        for node in soup.select(selector):
            raw = node.get(attr, "")
            dt = main.parse_dt(raw)
            if dt:
                candidates.append((dt, raw))

    for node in soup.select("time[datetime]"):
        raw = node.get("datetime", "")
        dt = main.parse_dt(raw)
        if dt:
            candidates.append((dt, raw))

    if not candidates:
        return ""

    now = datetime.now(timezone.utc)
    valid = [(dt, raw) for dt, raw in candidates if dt <= now]
    if not valid:
        valid = candidates
    return max(valid, key=lambda x: x[0])[1]


def extract_page_item(url, source_name, title="", source_bucket="direct_topic", forced_market=""):
    try:
        response = main.SESSION.get(url, timeout=20, allow_redirects=True)
        if response.status_code != 200:
            print(f"DIRECT_ERROR {source_name} {response.status_code} {url}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        published = _best_published(soup)

        author = ""
        for selector, attr in [
            ('meta[name="author"]', "content"),
            ('meta[property="article:author"]', "content"),
        ]:
            node = soup.select_one(selector)
            if node and node.get(attr):
                author = clean_text(node.get(attr))
                break

        body = soup.select_one("article") or soup.select_one("main") or soup.body or soup
        text = clean_text(body.get_text(" ", strip=True))[:14000]

        return {
            "source": source_name,
            "url": response.url,
            "title": title or clean_text(soup.title.string if soup.title else ""),
            "text": text,
            "published": published,
            "author": author,
            "source_bucket": source_bucket,
            "forced_market": forced_market,
        }
    except Exception as exc:
        print(f"DIRECT_EXCEPTION {source_name} {url} {exc}")
        return None


def _allowed_link(source, href):
    low = href.lower()
    if any(bit in low for bit in BAD_PATH_BITS):
        return False

    include = [str(x).lower() for x in source.get("include_path", []) if str(x).strip()]
    if include and not any(bit in low for bit in include):
        return False

    exclude = [str(x).lower() for x in source.get("exclude_path", []) if str(x).strip()]
    if exclude and any(bit in low for bit in exclude):
        return False

    return True


def scrape_index_source(source):
    if source.get("discovery_only"):
        print(f"DISCOVERY_ONLY {source['name']} {source['url']}")
        return []

    items = []
    try:
        response = main.SESSION.get(source["url"], timeout=20, allow_redirects=True)
        if response.status_code != 200:
            print(f"DIRECT_ERROR {source['name']} {response.status_code} {source['url']}")
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        links = []
        limit = int(source.get("max_links", DIRECT_LINK_LIMIT))

        for anchor in soup.find_all("a", href=True):
            href = urljoin(response.url, anchor["href"])
            host = urlparse(href).netloc.lower().replace("www.", "")
            title = clean_text(anchor.get_text(" ", strip=True))

            if source["domain"].replace("www.", "") not in host:
                continue
            if href.rstrip("/") == response.url.rstrip("/"):
                continue
            if not _allowed_link(source, href):
                continue
            if len(title) < 5:
                continue
            if href not in [x[0] for x in links]:
                links.append((href, title))
            if len(links) >= limit:
                break

        for href, title in links:
            item = extract_page_item(
                href,
                source["name"],
                title,
                "direct_index_v2",
                source.get("market", ""),
            )
            if item:
                items.append(item)

    except Exception as exc:
        print(f"DIRECT_EXCEPTION {source['name']} {exc}")

    return items


def discover_public_telegram_channels(catalog_names=None):
    wanted = set(catalog_names or [])
    channels = []
    source_counts = {}

    for catalog in DISCOVERY_CATALOGS:
        if wanted and catalog["name"] not in wanted:
            continue
        found = []
        try:
            response = main.SESSION.get(catalog["url"], timeout=20, allow_redirects=True)
            if response.status_code != 200:
                print(f"CATALOG_ERROR {catalog['name']} {response.status_code}")
                source_counts[catalog["name"]] = 0
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            for anchor in soup.find_all("a", href=True):
                href = anchor.get("href", "")
                if "t.me/" not in href:
                    continue
                parsed = urlparse(href if href.startswith("http") else "https://" + href.lstrip("/"))
                parts = [p for p in parsed.path.split("/") if p]
                if not parts:
                    continue
                username = parts[0].lstrip("@").strip()
                if not username or username.startswith("+") or username in ("s", "share"):
                    continue
                if username not in found:
                    found.append(username)
                if len(found) >= CATALOG_CHANNEL_LIMIT:
                    break
        except Exception as exc:
            print(f"CATALOG_EXCEPTION {catalog['name']} {exc}")

        source_counts[catalog["name"]] = len(found)
        for username in found:
            if username not in channels:
                channels.append(username)

    print("CATALOG_TELEGRAM_COUNTS", source_counts)
    return channels
