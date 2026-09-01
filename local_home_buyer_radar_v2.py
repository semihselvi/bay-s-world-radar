from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import timedelta

import local_home_buyer_radar as base


VERSION = "2.0-buyer-qualification"
PROFILE = os.getenv("LOCAL_HOME_RADAR_PROFILE", "germany_home").strip().lower()
LOOKBACK_HOURS = int(os.getenv("LOCAL_HOME_LOOKBACK_HOURS", "48"))
BING_QUERY_LIMIT = int(os.getenv("LOCAL_HOME_BING_QUERY_LIMIT", "12"))
SERPER_QUERY_LIMIT = int(os.getenv("LOCAL_HOME_SERPER_QUERY_LIMIT", "4"))

_BASE_CLASSIFY = base.classify

# Always run a few high-intent searches, then rotate city/community/financing searches.
CORE_QUERIES = {
    "germany_home": [
        'Deutschland "Wohnung zum Kauf gesucht"',
        'Deutschland "Haus zum Kauf gesucht"',
        'Deutschland "suche Wohnung zum Kauf" Budget',
        'Deutschland "Immobilie kaufen" Eigenkapital Forum',
    ],
    "netherlands_home": [
        'Nederland "koopwoning gezocht"',
        'Nederland "huis om te kopen gezocht"',
        'Nederland "ik zoek een huis om te kopen"',
        'Nederland woning kopen hypotheek forum',
    ],
    "belgium_home": [
        'België "koopwoning gezocht"',
        'België "huis om te kopen gezocht"',
        'Belgique "recherche appartement à acheter"',
        'Belgique acheter maison budget crédit hypothécaire forum',
    ],
    "switzerland_home": [
        'Schweiz "Wohnung zum Kauf gesucht"',
        'Schweiz "Haus zum Kauf gesucht"',
        'Suisse "recherche appartement à acheter"',
        'Schweiz Immobilie kaufen Eigenkapital Hypothek Forum',
    ],
}

ROTATING_QUERIES = {
    "germany_home": [
        'Berlin "suche Wohnung zum Kauf" Forum',
        'Berlin "looking to buy apartment" reddit',
        'München "Wohnung zum Kauf gesucht"',
        'München Wohnung kaufen Eigenkapital Forum',
        'Hamburg "Haus zum Kauf gesucht"',
        'Frankfurt "Wohnung kaufen" suche Forum',
        'Düsseldorf "Wohnung zum Kauf gesucht"',
        'Köln "Haus kaufen" suche Forum',
        'Stuttgart "Wohnung kaufen" suche Forum',
        'Leipzig "Haus kaufen" suche Forum',
        'site:reddit.com/r/germany "buy apartment" Germany',
        'site:reddit.com/r/berlin "buy apartment"',
        'site:reddit.com/r/Munich "buy apartment"',
        'site:gutefrage.net "Wohnung kaufen" suche',
        'site:finanztip.de/community Immobilie kaufen Eigenkapital',
        'site:wertpapier-forum.de Immobilie kaufen Eigennutzung',
        'site:wiwi-treff.de Wohnung kaufen Finanzierung',
        'site:hausbau-forum.de Haus kaufen gesucht',
        'site:expat.com Germany "buy apartment" forum',
        'site:expatforum.com Germany "buy house"',
        'Deutschland "Finanzierungsbestätigung" Wohnung kaufen',
        'Deutschland "Kaufzusage" Immobilie suche',
    ],
    "netherlands_home": [
        'Amsterdam "koopwoning gezocht"',
        'Amsterdam "looking to buy apartment" reddit',
        'Rotterdam "koopwoning gezocht"',
        'Den Haag "huis kopen" zoek forum',
        'Utrecht "woning om te kopen gezocht"',
        'Eindhoven "koopwoning gezocht"',
        'Haarlem "huis kopen" zoek',
        'Almere "koopwoning gezocht"',
        'Groningen "woning kopen" zoek forum',
        'site:reddit.com/r/NetherlandsHousing "buy house"',
        'site:reddit.com/r/Netherlands "buy house"',
        'site:reddit.com/r/Amsterdam "buy apartment"',
        'site:tweakers.net woning kopen hypotheek',
        'site:forum.fok.nl huis kopen zoek',
        'site:investeerders.nl woning kopen',
        'site:expat.com Netherlands "buy house" forum',
        'site:expatforum.com Netherlands "buy apartment"',
        'Nederland "hypotheek akkoord" huis kopen',
        'Nederland "aankoopmakelaar" "ik zoek" woning',
        'Nederland "eigen geld" woning kopen forum',
    ],
    "belgium_home": [
        'Brussel "appartement kopen" zoek forum',
        'Bruxelles "cherche appartement à acheter"',
        'Antwerpen "woning kopen" zoek forum',
        'Gent "huis kopen" zoek forum',
        'Leuven "appartement kopen" zoek',
        'Liège "cherche maison à acheter"',
        'Charleroi "cherche maison à acheter"',
        'site:reddit.com/r/belgium "buy house"',
        'site:reddit.com/r/brussels "buy apartment"',
        'site:pim.be cherche appartement acheter',
        'site:pim.be woning kopen gezocht',
        'site:bouwinfo.be woning kopen zoek',
        'site:expat.com Belgium "buy apartment" forum',
        'site:expatforum.com Belgium "buy house"',
        'België "hypothecaire lening" woning kopen forum',
        'Belgique "prêt hypothécaire" appartement acheter forum',
        'België "eigen inbreng" huis kopen',
        'Belgique "apport" maison acheter budget',
    ],
    "switzerland_home": [
        'Zürich "Wohnung zum Kauf gesucht"',
        'Zürich Wohnung kaufen Eigenkapital Forum',
        'Basel "Haus zum Kauf gesucht"',
        'Bern "Wohnung kaufen" suche Forum',
        'Luzern "Wohnung zum Kauf gesucht"',
        'Zug "Wohnung kaufen" suche Forum',
        'Genève "cherche appartement à acheter"',
        'Lausanne "cherche appartement à acheter"',
        'site:reddit.com/r/Switzerland "buy apartment"',
        'site:reddit.com/r/askswitzerland "buy house"',
        'site:englishforum.ch "buy apartment" Switzerland',
        'site:englishforum.ch "buy house" mortgage',
        'site:beobachter.ch Wohnung kaufen Hypothek',
        'site:expat.com Switzerland "buy house" forum',
        'site:expatforum.com Switzerland "buy apartment"',
        'Schweiz "Hypothek bestätigt" Wohnung kaufen',
        'Schweiz "Eigenkapital" "Wohnung kaufen"',
        'Suisse "hypothèque" appartement acheter budget',
        'Suisse "apport" maison acheter',
    ],
}

CITY_PATTERNS = {
    "germany_home": ["Berlin", "München", "Munich", "Hamburg", "Frankfurt", "Düsseldorf", "Dusseldorf", "Köln", "Cologne", "Stuttgart", "Leipzig", "Nürnberg", "Nurnberg"],
    "netherlands_home": ["Amsterdam", "Rotterdam", "Den Haag", "The Hague", "Utrecht", "Eindhoven", "Haarlem", "Almere", "Groningen"],
    "belgium_home": ["Brussels", "Brussel", "Bruxelles", "Antwerp", "Antwerpen", "Gent", "Ghent", "Leuven", "Brugge", "Liège", "Liege", "Charleroi"],
    "switzerland_home": ["Zürich", "Zurich", "Geneva", "Genève", "Geneve", "Lausanne", "Basel", "Bern", "Luzern", "Lucerne", "Zug"],
}

PROPERTY_TYPES = [
    ("apartment", re.compile(r"apartment|flat|wohnung|eigentumswohnung|appartement|квартир", re.I)),
    ("house", re.compile(r"house|home|haus|eigenheim|huis|woning|maison|дом", re.I)),
    ("villa", re.compile(r"villa|вилл", re.I)),
    ("land", re.compile(r"land|plot|grundst(?:u|ü)ck|bouwgrond|terrain|участ", re.I)),
]

PURCHASE_ACTION_RE = re.compile(
    r"buy|purchase|kaufen|kauf|zum\s+kauf|kopen|koopwoning|acheter|achat|купить|покупк",
    re.I,
)

FOREIGN_MARKET_RE = re.compile(
    r"spain|spanien|spanje|espagne|portugal|italy|italien|italië|italie|france|frankreich|frankrijk|"
    r"greece|griechenland|griekenland|cyprus|zypern|north\s+cyprus|nordzypern|turkey|türkei|turkije|"
    r"dubai|uae|montenegro|croatia|kroatien|kroatië|austria|österreich|poland|polen|polska",
    re.I,
)

READY_RE = re.compile(
    r"pre[- ]?approved|mortgage\s+(?:approved|agreed)|cash\s+buyer|ready\s+to\s+buy|book(?:ed)?\s+(?:a\s+)?viewing|make\s+an\s+offer|"
    r"finanzierungsbestätigung|finanzierung\s+(?:steht|bestätigt)|eigenkapital\s+(?:ist\s+)?vorhanden|kaufzusage|"
    r"hypotheek\s+(?:akkoord|rond)|financiering\s+(?:rond|goedgekeurd)|eigen\s+geld\s+(?:beschikbaar|aanwezig)|"
    r"prêt\s+hypothécaire\s+(?:accordé|approuvé)|financement\s+(?:approuvé|accordé)|apport\s+(?:disponible|prêt)|"
    r"hypothek\s+(?:bestätigt|genehmigt)|finanzierung\s+(?:bestätigt|gesichert)",
    re.I,
)

FINANCE_RE = re.compile(
    r"mortgage|deposit|down\s+payment|pre[- ]?approval|hypothek|eigenkapital|finanzierung|anzahlung|"
    r"hypotheek|eigen\s+geld|financiering|prêt\s+hypothécaire|pret\s+hypothecaire|apport|financement|cash\s+buyer",
    re.I,
)

TIME_RE = re.compile(
    r"this\s+month|next\s+month|this\s+year|next\s+year|within\s+\d+\s+months?|"
    r"dieses\s+jahr|nächstes\s+jahr|naechstes\s+jahr|in\s+den\s+nächsten\s+\d+\s+monaten|"
    r"dit\s+jaar|volgend\s+jaar|binnen\s+\d+\s+maanden|"
    r"cette\s+année|cette\s+annee|l'année\s+prochaine|dans\s+\d+\s+mois",
    re.I,
)

BUDGET_RE = re.compile(r"(?:CHF|EUR|EUR\s*|€|£|\$)\s*\d[\d\s.,]*(?:\s*[kKmM])?", re.I)
BED_RE = re.compile(r"\b(\d+)\s*(?:bed(?:room)?s?|zimmer|slaapkamer(?:s)?|chambre(?:s)?)\b", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w€£$₣]+", " ", (text or "").casefold())).strip()


def semantic_key(profile: str, lead: dict) -> str:
    author = _norm(str(lead.get("author") or ""))
    text = _norm(base.plain(f"{lead.get('title','')} {lead.get('text','')}"))[:360]
    basis = f"{profile}|{author}|{text}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _rotate(values: list[str], count: int, offset: int = 0) -> list[str]:
    if count <= 0 or not values:
        return []
    if count >= len(values):
        return values[:]
    now = base.now_utc()
    slot = now.timetuple().tm_yday * 8 + now.hour // 3 + offset
    start = (slot * count) % len(values)
    return [values[(start + i) % len(values)] for i in range(count)]


def selected_queries(profile: str, limit: int, offset: int = 0) -> list[str]:
    core = CORE_QUERIES[profile]
    if limit <= len(core):
        return core[:limit]
    return core + _rotate(ROTATING_QUERIES[profile], limit - len(core), offset=offset)


def _near(regex_a: re.Pattern, regex_b: re.Pattern, text: str, radius: int = 90) -> bool:
    aa = list(regex_a.finditer(text))
    bb = list(regex_b.finditer(text))
    return any(abs(a.start() - b.start()) <= radius for a in aa for b in bb)


def _wrong_purchase_country(profile: str, text: str) -> bool:
    # Crucial precision guard: "I live in Germany and want to buy in Spain" is NOT
    # a Germany-home lead. Reject a foreign country tied to the purchase action,
    # unless a target-country/city term is tied at least as clearly to the purchase.
    foreign_linked = _near(PURCHASE_ACTION_RE, FOREIGN_MARKET_RE, text, 85)
    if not foreign_linked:
        return False
    target_re = base.PROFILES[profile]["target_re"]
    local_linked = _near(PURCHASE_ACTION_RE, target_re, text, 55)
    return not local_linked


def extract_requirements(profile: str, text: str) -> dict:
    req = {}
    budget = BUDGET_RE.search(text)
    if budget:
        req["budget"] = " ".join(budget.group(0).split())

    city = next((name for name in CITY_PATTERNS[profile] if re.search(rf"\b{re.escape(name)}\b", text, re.I)), "")
    if city:
        req["city"] = city

    prop = next((label for label, rx in PROPERTY_TYPES if rx.search(text)), "")
    if prop:
        req["property_type"] = prop

    bed = BED_RE.search(text)
    if bed:
        req["bedrooms"] = int(bed.group(1))

    if FINANCE_RE.search(text):
        req["financing"] = "mentioned"

    timeframe = TIME_RE.search(text)
    if timeframe:
        req["timeframe"] = " ".join(timeframe.group(0).split())

    return req


def classify_v2(profile: str, item: dict):
    lead = _BASE_CLASSIFY(profile, item)
    if lead is None:
        return None

    text = base.plain(f"{item.get('title','')} {item.get('text','')} {item.get('author','')}")
    if _wrong_purchase_country(profile, text):
        return None

    requirements = extract_requirements(profile, text)
    published = base.parse_date(item.get("published", ""))
    direct = bool(base.DIRECT_DEMAND_RE.search(text))
    ready = bool(READY_RE.search(text))

    if ready:
        stage = "READY"
    elif direct and (requirements.get("budget") or requirements.get("city") or requirements.get("financing")):
        stage = "ACTIVE"
    else:
        stage = "RESEARCH"

    # Unknown-date search snippets can still be useful, but they cannot be HOT
    # unless the buyer is clearly transaction-ready. This keeps stale SEO results
    # from outranking verified fresh demand.
    classification = lead.get("classification", "WARM")
    if published is None and classification == "HOT" and not ready:
        classification = "WARM"
    if ready:
        classification = "HOT"

    intent = int(lead.get("intent_score") or 0)
    if requirements.get("budget"):
        intent = min(100, intent + 3)
    if requirements.get("city"):
        intent = min(100, intent + 2)
    if ready:
        intent = max(intent, 94)

    return {
        **lead,
        "classification": classification,
        "intent_score": intent,
        "buyer_stage": stage,
        "requirements": requirements,
        "freshness_verified": published is not None,
        "radar_version": VERSION,
    }


def _format_requirements(lead: dict) -> str:
    req = lead.get("requirements") or {}
    bits = []
    if req.get("city"):
        bits.append("Şehir: " + str(req["city"]))
    if req.get("property_type"):
        bits.append("Mülk: " + str(req["property_type"]))
    if req.get("bedrooms"):
        bits.append("Oda: " + str(req["bedrooms"]))
    if req.get("budget"):
        bits.append("Bütçe: " + str(req["budget"]))
    if req.get("financing"):
        bits.append("Finansman: var")
    if req.get("timeframe"):
        bits.append("Zaman: " + str(req["timeframe"]))
    return " | ".join(bits)


def run():
    if PROFILE not in base.PROFILES:
        raise SystemExit(f"Unknown LOCAL_HOME_RADAR_PROFILE={PROFILE}")

    started = base.now_utc()
    spec = base.PROFILES[PROFILE]
    bing_queries = selected_queries(PROFILE, BING_QUERY_LIMIT, offset=0)
    serper_queries = selected_queries(PROFILE, SERPER_QUERY_LIMIT, offset=3)

    raw = []
    for query in bing_queries:
        raw.extend(base._bing(query))
    for query in serper_queries:
        raw.extend(base._serper(query))

    by_url = {}
    for item in raw:
        url = str(item.get("url") or "")
        if url:
            by_url[url] = item

    leads = []
    seen_content = set()
    for item in by_url.values():
        lead = classify_v2(PROFILE, item)
        if not lead:
            continue
        ckey = semantic_key(PROFILE, lead)
        if ckey in seen_content:
            continue
        seen_content.add(ckey)
        lead["semantic_key"] = ckey
        leads.append(lead)

    stage_rank = {"READY": 3, "ACTIVE": 2, "RESEARCH": 1}
    leads.sort(
        key=lambda x: (
            x.get("classification") == "HOT",
            stage_rank.get(x.get("buyer_stage"), 0),
            int(x.get("intent_score") or 0),
            int(x.get("credibility_score") or 0),
        ),
        reverse=True,
    )

    db = base.main.firestore_client()
    new = []
    for lead in leads:
        key = semantic_key(PROFILE, lead)
        if base.notified_before(db, key, days=14):
            continue
        new.append(lead)
        base.mark_notified(db, key, lead)

    scan_id = f"{started.strftime('%Y%m%d%H%M%S')}_{PROFILE}_v2"
    if db:
        try:
            ref = db.collection(base.SCAN_COLLECTION).document(scan_id)
            batch = db.batch()
            for lead in leads[:100]:
                batch.set(ref.collection("leads").document(semantic_key(PROFILE, lead)), lead, merge=True)
            batch.set(ref, {
                "profile": PROFILE,
                "radar_version": VERSION,
                "target_market": spec["target"],
                "started_at": started.isoformat(),
                "finished_at": base.now_utc().isoformat(),
                "raw_results": len(raw),
                "unique_urls": len(by_url),
                "semantic_unique_leads": len(leads),
                "new_to_notify": len(new),
                "lookback_hours": LOOKBACK_HOURS,
                "bing_queries": len(bing_queries),
                "serper_queries": len(serper_queries),
            }, merge=True)
            batch.commit()
        except Exception as exc:
            print("LOCAL_HOME_V2_FIRESTORE_ERROR", exc)

    print("LOCAL_HOME_RADAR_V2_COMPLETE", json.dumps({
        "profile": PROFILE,
        "version": VERSION,
        "target_market": spec["target"],
        "raw": len(raw),
        "unique_urls": len(by_url),
        "qualified": len(leads),
        "new": len(new),
        "bing_queries": len(bing_queries),
        "serper_queries": len(serper_queries),
    }, ensure_ascii=False))

    if not new:
        return []

    lines = [f"{spec['icon']} BAY-S {spec['title']} V2 | {len(new)} YENİ LEAD"]
    for lead in new[:10]:
        excerpt = base.plain(lead.get("text", ""))[:260]
        req_line = _format_requirements(lead)
        freshness = "tarih✓" if lead.get("freshness_verified") else "tarih?"
        lines.append(
            f"\n{lead['classification']} | {lead.get('buyer_stage','RESEARCH')} | {freshness} | "
            f"I{lead['intent_score']} C{lead['credibility_score']}\n"
            + (req_line + "\n" if req_line else "")
            + f"{lead.get('title','')[:115]}\n{excerpt}\n{lead.get('url','')}"
        )
    base.main.notify_telegram("\n".join(lines))
    return new


if __name__ == "__main__":
    run()
