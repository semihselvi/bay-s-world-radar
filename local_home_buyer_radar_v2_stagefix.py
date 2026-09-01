from __future__ import annotations

import os
import re
from collections import Counter, defaultdict
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from bs4 import BeautifulSoup

import local_home_buyer_radar_v2_precision as precision
import local_home_buyer_radar_v2 as radar


VERSION = "2.3-community-search-rescue"
radar.VERSION = VERSION

# Preserve the V2 destination-precision patch and then tighten stage detection.
_ORIGINAL_CLASSIFY_V2 = radar.classify_v2
_ORIGINAL_SERPER = radar.base._serper
_ORIGINAL_BING = radar.base._bing

# Covers transaction-ready equity/finance wording even when a currency amount sits
# between the finance term and "available/present/approved" wording.
READY_FLEX_RE = re.compile(
    r"(?:"
    r"pre[- ]?approved|mortgage\s+(?:approved|agreed)|cash\s+buyer|ready\s+to\s+buy|"
    r"book(?:ed)?\s+(?:a\s+)?viewing|make\s+an\s+offer|"
    r"finanzierungsbestätigung|finanzierung.{0,45}(?:steht|bestätigt|genehmigt|gesichert)|"
    r"eigenkapital.{0,55}(?:vorhanden|verfügbar|verfuegbar|gesichert)|kaufzusage|"
    r"hypotheek.{0,45}(?:akkoord|rond|goedgekeurd)|financiering.{0,45}(?:rond|goedgekeurd)|"
    r"eigen\s+geld.{0,55}(?:beschikbaar|aanwezig)|"
    r"prêt\s+hypothécaire.{0,45}(?:accordé|approuvé)|pret\s+hypothecaire.{0,45}(?:accorde|approuve)|"
    r"financement.{0,45}(?:approuvé|accordé|approuve|accorde)|apport.{0,55}(?:disponible|prêt|pret)|"
    r"hypothek.{0,45}(?:bestätigt|genehmigt|gesichert)"
    r")",
    re.I | re.S,
)

# Guaranteed community/user-source queries. Broad queries often return portals,
# developer pages and SEO articles. These lanes force part of every scan into
# places where an actual buyer can speak in first person.
FORCED_USER_QUERIES = {
    "germany_home": [
        'site:reddit.com/r/germany "buy apartment" Germany',
        'site:gutefrage.net "Wohnung kaufen" suche',
        'site:finanztip.de/community Immobilie kaufen Eigenkapital',
        'site:hausbau-forum.de Haus kaufen gesucht',
        'site:wertpapier-forum.de Immobilie kaufen Eigennutzung',
        'site:expatforum.com Germany "buy house"',
    ],
    "netherlands_home": [
        'site:reddit.com/r/NetherlandsHousing "buy house"',
        'site:reddit.com/r/Netherlands "buy house"',
        'site:tweakers.net woning kopen hypotheek',
        'site:forum.fok.nl huis kopen zoek',
        'site:expatforum.com Netherlands "buy apartment"',
        'site:expat.com Netherlands "buy house" forum',
    ],
    "belgium_home": [
        'site:reddit.com/r/belgium "buy house"',
        'site:reddit.com/r/brussels "buy apartment"',
        'site:pim.be cherche appartement acheter',
        'site:bouwinfo.be woning kopen zoek',
        'site:expatforum.com Belgium "buy house"',
        'site:expat.com Belgium "buy apartment" forum',
    ],
    "switzerland_home": [
        'site:reddit.com/r/Switzerland "buy apartment"',
        'site:reddit.com/r/askswitzerland "buy house"',
        'site:englishforum.ch "buy apartment" Switzerland',
        'site:englishforum.ch "buy house" mortgage',
        'site:expatforum.com Switzerland "buy apartment"',
        'site:expat.com Switzerland "buy house" forum',
    ],
}

SEARCH_LOCALE = {
    "germany_home": "de-DE",
    "netherlands_home": "nl-NL",
    "belgium_home": "nl-BE",
    "switzerland_home": "de-CH",
}
DDG_REGION = {
    "germany_home": "de-de",
    "netherlands_home": "nl-nl",
    "belgium_home": "be-nl",
    "switzerland_home": "ch-de",
}

_DIAG_COUNTS = Counter()
_DIAG_DOMAINS = Counter()
_DIAG_SAMPLES = defaultdict(list)
_SERPER_WARNED = False


def _active_evidence(requirements: dict) -> int:
    keys = ("budget", "city", "financing", "timeframe", "bedrooms")
    return sum(1 for key in keys if requirements.get(key))


def _rotate(values: list[str], count: int, offset: int = 0) -> list[str]:
    if count <= 0 or not values:
        return []
    if count >= len(values):
        return values[:]
    now = radar.base.now_utc()
    slot = now.timetuple().tm_yday * 8 + now.hour // 3 + offset
    start = (slot * count) % len(values)
    return [values[(start + i) % len(values)] for i in range(count)]


def selected_queries(profile: str, limit: int, offset: int = 0) -> list[str]:
    core = list(radar.CORE_QUERIES[profile])
    forced = list(FORCED_USER_QUERIES[profile])
    rotating = [q for q in radar.ROTATING_QUERIES[profile] if q not in forced]

    if offset == 3:
        if limit <= len(forced):
            return forced[:limit]
        return forced + _rotate(rotating, limit - len(forced), offset=offset)

    chosen = []
    for q in core:
        if q not in chosen:
            chosen.append(q)
    forced_slots = min(len(forced), max(2, limit // 3))
    for q in forced[:forced_slots]:
        if q not in chosen:
            chosen.append(q)
    remaining = limit - len(chosen)
    if remaining > 0:
        for q in _rotate(rotating, remaining, offset=offset):
            if q not in chosen:
                chosen.append(q)
    return chosen[:limit]


def _expected_domain(query: str) -> str:
    match = re.search(r"(?:^|\s)site:([^\s\"']+)", query or "", re.I)
    if not match:
        return ""
    token = match.group(1).strip().lower().split("/", 1)[0]
    return token.removeprefix("www.")


def _domain_matches(url: str, expected: str) -> bool:
    if not expected:
        return True
    domain = radar.base.domain_of(url)
    return domain == expected or domain.endswith("." + expected)


def _search_result_allowed(query: str, item: dict) -> bool:
    url = str(item.get("url") or "")
    if not url or not radar.base.user_source(url):
        return False
    expected = _expected_domain(query)
    return _domain_matches(url, expected)


def _full_query(query: str) -> str:
    cutoff = (radar.base.now_utc() - radar.timedelta(hours=radar.LOOKBACK_HOURS)).date().isoformat()
    return f"{query} after:{cutoff}"


def _bing_html(query: str) -> list[dict]:
    try:
        response = radar.base.SESSION.get(
            "https://www.bing.com/search",
            params={
                "q": _full_query(query),
                "count": "20",
                "setlang": SEARCH_LOCALE.get(radar.PROFILE, "en-US"),
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
                "Accept-Language": SEARCH_LOCALE.get(radar.PROFILE, "en-US") + ",en;q=0.8",
            },
            timeout=20,
        )
    except Exception as exc:
        print("LOCAL_HOME_BING_HTML_EXCEPTION", query, exc)
        return []
    if response.status_code != 200:
        print("LOCAL_HOME_BING_HTML_ERROR", response.status_code, query)
        return []

    out = []
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup.select("li.b_algo"):
        link = node.select_one("h2 a")
        if not link:
            continue
        href = str(link.get("href") or "").strip()
        if not href:
            continue
        caption = node.select_one(".b_caption p") or node.select_one("p")
        item = {
            "source": "Bing HTML",
            "url": href,
            "title": radar.base.plain(link.get_text(" ", strip=True)),
            "text": radar.base.plain(caption.get_text(" ", strip=True) if caption else ""),
            "published": "",
            "author": "",
            "discovery_query": query,
        }
        if _search_result_allowed(query, item):
            out.append(item)
        if len(out) >= 10:
            break
    print(f"LOCAL_HOME_BING_HTML_OK profile={radar.PROFILE} query={query!r} user_results={len(out)}")
    return out


def _decode_ddg_url(href: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc or href.startswith("/l/"):
        values = parse_qs(parsed.query).get("uddg")
        if values:
            return unquote(values[0])
    return href


def _ddg_html(query: str) -> list[dict]:
    try:
        response = radar.base.SESSION.get(
            "https://html.duckduckgo.com/html/",
            params={"q": _full_query(query), "kl": DDG_REGION.get(radar.PROFILE, "wt-wt")},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
                "Accept-Language": SEARCH_LOCALE.get(radar.PROFILE, "en-US") + ",en;q=0.8",
            },
            timeout=20,
        )
    except Exception as exc:
        print("LOCAL_HOME_DDG_EXCEPTION", query, exc)
        return []
    if response.status_code != 200:
        print("LOCAL_HOME_DDG_ERROR", response.status_code, query)
        return []

    out = []
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup.select(".result"):
        link = node.select_one("a.result__a")
        if not link:
            continue
        href = _decode_ddg_url(str(link.get("href") or "").strip())
        snippet = node.select_one(".result__snippet")
        item = {
            "source": "DuckDuckGo HTML",
            "url": href,
            "title": radar.base.plain(link.get_text(" ", strip=True)),
            "text": radar.base.plain(snippet.get_text(" ", strip=True) if snippet else ""),
            "published": "",
            "author": "",
            "discovery_query": query,
        }
        if _search_result_allowed(query, item):
            out.append(item)
        if len(out) >= 10:
            break
    print(f"LOCAL_HOME_DDG_OK profile={radar.PROFILE} query={query!r} user_results={len(out)}")
    return out


def _bing_community_rescue(query: str) -> list[dict]:
    """Use Bing HTML first, then a no-key DDG rescue, then filtered RSS fallback.

    Bing RSS was observed returning unrelated domains even for site:reddit.com and
    site:gutefrage.net queries. Every result is now domain-enforced before it reaches
    the buyer classifier.
    """
    merged = {}
    for item in _bing_html(query):
        merged[item["url"]] = item

    # Search a second engine only when Bing HTML did not find enough actual user posts.
    if len(merged) < 2:
        for item in _ddg_html(query):
            merged[item["url"]] = item

    if not merged:
        rss = _ORIGINAL_BING(query)
        kept = [item for item in rss if _search_result_allowed(query, item)]
        if kept:
            print(f"LOCAL_HOME_BING_RSS_RESCUE profile={radar.PROFILE} query={query!r} user_results={len(kept)}")
        for item in kept:
            merged[item["url"]] = item

    return list(merged.values())[:10]


def _rejection_reason(profile: str, item: dict) -> str:
    base = radar.base
    url = str(item.get("url") or "")
    if not url:
        return "missing_url"
    if not base.user_source(url):
        return "non_user_source"

    text = base.plain(f"{item.get('title','')} {item.get('text','')} {item.get('author','')}")
    if not text:
        return "empty_text"
    if base.RENT_RE.search(text):
        return "rental"

    buyer_voice = bool(base.BUYER_VOICE_RE.search(text) or base.DIRECT_DEMAND_RE.search(text))
    prop = bool(base.PROPERTY_RE.search(text))
    if not buyer_voice:
        return "no_buyer_voice"
    if not prop:
        return "no_property_context"
    if base.SELLER_STRONG_RE.search(text):
        return "seller"
    if len(base.SELLER_MARKETING_RE.findall(text)) >= 2:
        return "marketing_listing"

    target_ok, _bridged = base._target_match(profile, text, item)
    if not target_ok:
        return "target_mismatch"

    published = base.parse_date(item.get("published", ""))
    if published and published < base.now_utc() - radar.timedelta(hours=radar.LOOKBACK_HOURS):
        return "stale"

    if radar._wrong_purchase_country(profile, text):
        return "foreign_destination"
    return "other_classifier_reject"


def _record_reject(profile: str, item: dict):
    reason = _rejection_reason(profile, item)
    _DIAG_COUNTS[reason] += 1
    domain = radar.base.domain_of(str(item.get("url") or "")) or "unknown"
    _DIAG_DOMAINS[domain] += 1
    if len(_DIAG_SAMPLES[reason]) < 3:
        title = radar.base.plain(str(item.get("title") or ""))[:110]
        snippet = radar.base.plain(str(item.get("text") or ""))[:220]
        query = str(item.get("discovery_query") or "")[:110]
        _DIAG_SAMPLES[reason].append((domain, title, snippet, query))


def classify_v2(profile: str, item: dict):
    lead = _ORIGINAL_CLASSIFY_V2(profile, item)
    if lead is None:
        _record_reject(profile, item)
        return None

    text = radar.base.plain(
        f"{item.get('title','')} {item.get('text','')} {item.get('author','')}"
    )
    requirements = dict(lead.get("requirements") or {})
    ready = bool(READY_FLEX_RE.search(text))

    stage = lead.get("buyer_stage", "RESEARCH")
    if ready:
        stage = "READY"
    elif stage == "RESEARCH" and _active_evidence(requirements) >= 2:
        stage = "ACTIVE"

    classification = lead.get("classification", "WARM")
    intent = int(lead.get("intent_score") or 0)
    if ready:
        classification = "HOT"
        intent = max(intent, 94)

    return {
        **lead,
        "buyer_stage": stage,
        "classification": classification,
        "intent_score": intent,
        "radar_version": VERSION,
    }


def _serper_with_diag(query: str):
    global _SERPER_WARNED
    if not os.getenv("SERPER_API_KEY", "").strip():
        if not _SERPER_WARNED:
            print("LOCAL_HOME_SERPER_DISABLED missing SERPER_API_KEY")
            _SERPER_WARNED = True
        return []
    return _ORIGINAL_SERPER(query)


radar.classify_v2 = classify_v2
radar.selected_queries = selected_queries
radar.base._bing = _bing_community_rescue
radar.base._serper = _serper_with_diag

extract_requirements = radar.extract_requirements
semantic_key = radar.semantic_key


def _print_diagnostics():
    if _DIAG_COUNTS:
        print("LOCAL_HOME_REJECT_COUNTS", dict(_DIAG_COUNTS))
    if _DIAG_DOMAINS:
        print("LOCAL_HOME_TOP_REJECT_DOMAINS", _DIAG_DOMAINS.most_common(12))
    for reason, samples in _DIAG_SAMPLES.items():
        for idx, (domain, title, snippet, query) in enumerate(samples, 1):
            print(
                f"LOCAL_HOME_REJECT_SAMPLE reason={reason} sample={idx} domain={domain} "
                f"title={title!r} snippet={snippet!r} query={query!r}"
            )


def run():
    try:
        return radar.run()
    finally:
        _print_diagnostics()


if __name__ == "__main__":
    run()
