from __future__ import annotations

import os
import re
from collections import Counter, defaultdict

import local_home_buyer_radar_v2_precision as precision
import local_home_buyer_radar_v2 as radar


VERSION = "2.2-source-precision-diagnostics"
radar.VERSION = VERSION

# Preserve the V2 destination-precision patch and then tighten stage detection.
_ORIGINAL_CLASSIFY_V2 = radar.classify_v2
_ORIGINAL_SERPER = radar.base._serper

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

_DIAG_COUNTS = Counter()
_DIAG_DOMAINS = Counter()
_DIAG_SAMPLES = defaultdict(list)
_SERPER_WARNED = False


def _active_evidence(requirements: dict) -> int:
    """Count concrete search signals that indicate active house hunting."""
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
    """Keep broad discovery but guarantee user/community sources.

    offset=0 is the Bing lane. offset=3 is the Serper lane in radar.run(), so
    Serper spends its smaller quota on user-source queries instead of repeating
    the same four broad searches.
    """
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
    # Reserve roughly one third of Bing capacity for known user communities.
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
    if len(_DIAG_SAMPLES[reason]) < 2:
        title = radar.base.plain(str(item.get("title") or ""))[:110]
        snippet = radar.base.plain(str(item.get("text") or ""))[:180]
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


# Patch the V2 engine so radar.run() uses the corrected classifier/query mix.
radar.classify_v2 = classify_v2
radar.selected_queries = selected_queries
radar.base._serper = _serper_with_diag

# Expose the same public helpers used by tests/workflows.
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
