from __future__ import annotations

import os
import re
from urllib.parse import urlparse

import requests

import local_home_buyer_radar_v2 as radar
import local_home_buyer_radar_v2_stagefix as stage

VERSION = "2.4-native-community-reader"
radar.VERSION = VERSION
stage.VERSION = VERSION

PROFILE = os.getenv("LOCAL_HOME_RADAR_PROFILE", "germany_home").strip().lower()
DETAIL_LIMIT = max(1, min(8, int(os.getenv("LOCAL_HOME_NATIVE_DETAIL_LIMIT", "6"))))

# Jina Reader works without an API key for basic read access. We use it only as a
# reader/proxy for known public community pages, not as a search API.
JINA_READER = "https://r.jina.ai/"

PROFILE_MARKER = {
    "germany_home": "Germany Deutschland",
    "netherlands_home": "Netherlands Nederland",
    "belgium_home": "Belgium België Belgique",
    "switzerland_home": "Switzerland Schweiz Suisse",
}

NATIVE_INDEXES = {
    "germany_home": [
        ("Finanztip Forum", "https://www.finanztip.de/community/forum/board/43-immobilienfinanzierung/"),
        ("Reddit Germany", "https://www.reddit.com/r/germany/new/"),
    ],
    "netherlands_home": [
        ("Reddit NetherlandsHousing", "https://www.reddit.com/r/NetherlandsHousing/new/"),
        ("Reddit Netherlands", "https://www.reddit.com/r/Netherlands/new/"),
        ("Tweakers Koopwoning", "https://tweakers.net/tag/Koopwoning/forum/2026/"),
    ],
    "belgium_home": [
        ("BouwInfo Gevraagd", "https://www.bouwinfo.be/bouwforum/forums/gevraagd.524/"),
        ("Pim Forum", "https://forum.pim.be/"),
        ("Reddit Belgium", "https://www.reddit.com/r/belgium/new/"),
    ],
    "switzerland_home": [
        ("Reddit SwissPersonalFinance", "https://www.reddit.com/r/SwissPersonalFinance/new/"),
        ("Reddit Switzerland", "https://www.reddit.com/r/Switzerland/new/"),
    ],
}

LINK_HINT_RE = re.compile(
    r"(?:"
    r"buy|buying|purchase|property|apartment|house|home|mortgage|"
    r"kauf|kaufen|wohnung|haus|immobilie|eigenkapital|finanzierung|hypothek|"
    r"kopen|koopwoning|woning|huis|appartement|hypotheek|bezichtiging|bod|"
    r"acheter|achat|appartement|maison|immobilier|hypoth[eè]que|cr[eé]dit"
    r")",
    re.I,
)

# Links that are likely to be individual user threads/posts. This prevents us from
# treating a generic index/profile/category page as a buyer lead.
def _thread_like(url: str) -> bool:
    low = (url or "").lower()
    return any(
        marker in low
        for marker in (
            "reddit.com/r/", "/comments/", "/community/forum/thema/",
            "gathering.tweakers.net/forum/list_messages/", "/bouwforum/threads/",
            "forum.pim.be/topic-",
        )
    )


def _reader_get(url: str) -> str:
    target = JINA_READER + url
    try:
        response = requests.get(
            target,
            headers={
                "User-Agent": "BAY-S-Local-Home-Radar/2.4",
                "Accept": "text/plain",
            },
            timeout=35,
        )
    except Exception as exc:
        print("LOCAL_HOME_NATIVE_READER_EXCEPTION", url, exc)
        return ""
    if response.status_code != 200:
        print("LOCAL_HOME_NATIVE_READER_ERROR", response.status_code, url)
        return ""
    return response.text or ""


def extract_markdown_links(markdown: str) -> list[tuple[str, str]]:
    out = []
    seen = set()
    for label, url in re.findall(r"\[([^\]]{2,220})\]\((https?://[^)\s]+)\)", markdown or ""):
        clean_label = " ".join(label.split())
        clean_url = url.strip()
        key = (clean_label, clean_url)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def relevant_thread_link(label: str, url: str) -> bool:
    if not url or not radar.base.user_source(url):
        return False
    if not _thread_like(url):
        return False
    return bool(LINK_HINT_RE.search(f"{label} {url}"))


def parse_reader_page(source: str, url: str, text: str, profile: str) -> dict | None:
    if not text:
        return None

    title = ""
    published = ""
    author = ""

    m = re.search(r"(?mi)^Title:\s*(.+)$", text)
    if m:
        title = m.group(1).strip()
    if not title:
        m = re.search(r"(?m)^#\s+(.+)$", text)
        if m:
            title = m.group(1).strip()

    m = re.search(r"(?mi)^Published Time:\s*(.+)$", text)
    if m:
        published = m.group(1).strip()

    # Best-effort author extraction for Reddit and common forum renderings.
    m = re.search(r"(?i)(?:submitted\s+by|posted\s+by|by\s+u/|u/)([A-Za-z0-9_-]{2,40})", text)
    if m:
        author = m.group(1)

    body = text
    marker = re.search(r"(?mi)^Markdown Content:\s*$", text)
    if marker:
        body = text[marker.end():]
    body = " ".join(body.split())[:12000]
    if not body:
        return None

    return {
        "source": source,
        "url": url,
        "title": title or source,
        "text": body,
        "published": published,
        "author": author,
        "discovery_query": f"native {PROFILE_MARKER.get(profile, profile)} {source}",
        "native_reader": True,
    }


def collect_native(profile: str) -> list[dict]:
    indexes = NATIVE_INDEXES.get(profile, [])
    if not indexes:
        return []

    candidates: list[tuple[str, str, str]] = []
    seen_urls = set()

    for source, index_url in indexes:
        index_text = _reader_get(index_url)
        if not index_text:
            continue
        found = 0
        for label, url in extract_markdown_links(index_text):
            if url in seen_urls or not relevant_thread_link(label, url):
                continue
            seen_urls.add(url)
            candidates.append((source, label, url))
            found += 1
            if found >= 5:
                break
        print(f"LOCAL_HOME_NATIVE_INDEX profile={profile} source={source!r} candidates={found}")

    items = []
    for source, _label, url in candidates[:DETAIL_LIMIT]:
        page_text = _reader_get(url)
        item = parse_reader_page(source, url, page_text, profile)
        if item:
            items.append(item)

    print(
        f"LOCAL_HOME_NATIVE_COMPLETE profile={profile} indexes={len(indexes)} "
        f"candidate_links={len(candidates)} items={len(items)}"
    )
    return items


_NATIVE_EMITTED = False


def _native_bing_bridge(_query: str) -> list[dict]:
    global _NATIVE_EMITTED
    if _NATIVE_EMITTED:
        return []
    _NATIVE_EMITTED = True
    print("LOCAL_HOME_NATIVE_MODE direct community indexes via Jina Reader")
    return collect_native(PROFILE)


# Replace the failing Bing/DDG lane with direct community discovery. Serper remains
# additive if a key is configured in the repository.
radar.base._bing = _native_bing_bridge
radar.VERSION = VERSION
stage.radar.VERSION = VERSION

# Keep the corrected V2.2/V2.3 classifier and diagnostics.
classify_v2 = stage.classify_v2
extract_requirements = stage.extract_requirements
semantic_key = stage.semantic_key
selected_queries = stage.selected_queries


def run():
    return stage.run()


if __name__ == "__main__":
    run()
