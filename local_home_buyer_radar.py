from __future__ import annotations

import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

import main


PROFILE = os.getenv("LOCAL_HOME_RADAR_PROFILE", "germany_home").strip().lower()
LOOKBACK_HOURS = int(os.getenv("LOCAL_HOME_LOOKBACK_HOURS", "48"))
BING_QUERY_LIMIT = int(os.getenv("LOCAL_HOME_BING_QUERY_LIMIT", "10"))
SERPER_QUERY_LIMIT = int(os.getenv("LOCAL_HOME_SERPER_QUERY_LIMIT", "5"))
NOTIFIED_COLLECTION = "bay_s_local_home_notified"
SCAN_COLLECTION = "bay_s_local_home_scans"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; BAY-S-Local-Home-Radar/1.0)",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.9,nl;q=0.8,fr;q=0.8",
})

# We only want user/community discussions, not property portals or agency listings.
USER_DOMAINS = {
    "reddit.com", "old.reddit.com", "expat.com", "expatforum.com", "internations.org",
    "gutefrage.net", "finanztip.de", "wertpapier-forum.de", "wiwi-treff.de", "hausbau-forum.de",
    "tweakers.net", "forum.fok.nl", "investeerders.nl",
    "pim.be", "bouwinfo.be",
    "englishforum.ch", "beobachter.ch",
    "facebook.com", "threads.net", "x.com", "twitter.com", "t.me",
}

PROPERTY_RE = re.compile(
    r"(?:property|real\s+estate|apartment|flat|house|home|villa|studio|condo|land|plot|"
    r"immobilie|wohnung|haus|eigenheim|eigentumswohnung|grundst(?:u|ü)ck|"
    r"woning|huis|appartement|vastgoed|koopwoning|bouwgrond|"
    r"immobilier|appartement|maison|logement|villa|bien\s+immobilier|terrain|"
    r"квартир\w*|апартамент\w*|дом\w*|вилл\w*|недвижимост\w*)",
    re.I,
)

BUYER_VOICE_RE = re.compile(
    r"(?:"
    r"\b(?:i|we)\b.{0,55}\b(?:want|looking|trying|planning|plan|ready|need|hope|considering)\b.{0,70}\b(?:buy|purchase|apartment|flat|house|home|property)\b|"
    r"\blooking\s+for\b.{0,45}\b(?:to\s+buy|for\s+purchase)\b|\bhouse\s+hunting\b|\bhome\s+buyer\b|"
    r"\b(?:ich|wir)\b.{0,55}\b(?:suche|suchen|möchte|moechte|möchten|moechten|will|wollen|plane|planen)\b.{0,70}\b(?:kaufen|kauf|wohnung|haus|immobilie|eigenheim)\b|"
    r"\bsuche\b.{0,55}\b(?:wohnung|haus|immobilie|eigentumswohnung)\b.{0,35}\b(?:zum\s+kauf|kaufen)\b|"
    r"\b(?:ik|wij|we)\b.{0,55}\b(?:zoek|zoeken|wil|willen|plan|plannen|probeer|proberen)\b.{0,70}\b(?:kopen|woning|huis|appartement|vastgoed)\b|"
    r"\b(?:koopwoning|huis|woning|appartement)\s+gezocht\b|\bzoek\b.{0,45}\b(?:woning|huis|appartement)\b.{0,35}\b(?:om\s+te\s+kopen|te\s+koop)\b|"
    r"\b(?:je|nous)\b.{0,55}\b(?:cherche|cherchons|veux|voulons|souhaite|souhaitons|prévois|prevoyons)\b.{0,70}\b(?:acheter|appartement|maison|immobilier|logement)\b|"
    r"\brecherche\b.{0,45}\b(?:appartement|maison|logement)\b.{0,35}\b(?:à\s+acheter|a\s+acheter)\b|"
    r"\b(?:я|мы)\b.{0,55}\b(?:хочу|хотим|ищу|ищем|планир\w*|готов\w*)\b.{0,70}\b(?:купить|покупк\w*|квартир\w*|дом\w*|недвижимост\w*)\b"
    r")",
    re.I | re.S,
)

DIRECT_DEMAND_RE = re.compile(
    r"(?:looking\s+for\s+(?:an?\s+)?(?:apartment|flat|house|home)\s+to\s+buy|"
    r"suche\s+(?:eine?n?\s+)?(?:wohnung|haus|immobilie|eigentumswohnung)\s+(?:zum\s+kauf|zu\s+kaufen)|"
    r"(?:wohnung|haus|immobilie)\s+zum\s+kauf\s+gesucht|"
    r"(?:koopwoning|woning|huis|appartement)\s+gezocht|"
    r"(?:woning|huis|appartement)\s+om\s+te\s+kopen\s+gezocht|"
    r"recherche\s+(?:un\s+|une\s+)?(?:appartement|maison|logement)\s+(?:à|a)\s+acheter|"
    r"cherche\s+(?:un\s+|une\s+)?(?:appartement|maison)\s+(?:à|a)\s+acheter|"
    r"ищу\s+(?:квартир\w*|дом\w*|недвижимост\w*).{0,35}(?:купить|для\s+покупки))",
    re.I | re.S,
)

FIRST_PERSON_RE = re.compile(
    r"\b(?:i|we|my|our|ich|wir|mein\w*|unser\w*|ik|wij|we|mijn|ons|onze|je|nous|mon|ma|notre|я|мы|мой|наш)\b",
    re.I,
)

CONCRETE_RE = re.compile(
    r"(?:[£€$₣]\s*\d[\d\s.,]*(?:\s*[kKmM])?|\bCHF\s*\d[\d\s.,]*|\b\d{2,4}\s*[kK]\b|"
    r"\bbudget\b|\bbudget\s+van\b|\bbudget\s+de\b|\bbudget\s+bis\b|"
    r"\bmortgage\b|\bdeposit\b|\bdown\s+payment\b|\bpre[- ]?approval\b|"
    r"\bhypothek\b|\beigenkapital\b|\bfinanzierung\b|\banzahlung\b|"
    r"\bhypotheek\b|\beigen\s+geld\b|\bfinanciering\b|"
    r"\bprêt\s+hypothécaire\b|\bpret\s+hypothecaire\b|\bapport\b|\bfinancement\b|"
    r"\b\d+\s*(?:bed|bedroom|zimmer|slaapkamer|chambre)s?\b|"
    r"\b(?:this|next)\s+(?:month|year)\b|\bdieses\s+jahr\b|\bdit\s+jaar\b|\bcette\s+année\b|\bcette\s+annee\b)",
    re.I,
)

RENT_RE = re.compile(
    r"(?:looking\s+to\s+rent|for\s+rent|rental|renting|per\s+month|monthly\s+rent|"
    r"mieten|mietwohnung|zur\s+miete|monatsmiete|"
    r"huren|huurwoning|te\s+huur|maandhuur|"
    r"louer|location|à\s+louer|a\s+louer|loyer|"
    r"аренд\w*|снять|сниму|в\s+месяц)",
    re.I,
)

SELLER_STRONG_RE = re.compile(
    r"(?:\bi\s+am\s+selling\b|\bwe\s+are\s+selling\b|\bowner\s+selling\b|"
    r"\bich\s+verkaufe\b|\bwir\s+verkaufen\b|\bvon\s+privat\s+zu\s+verkaufen\b|"
    r"\bik\s+verkoop\b|\bwij\s+verkopen\b|\bte\s+koop\s+aangeboden\b|"
    r"\bje\s+vends\b|\bnous\s+vendons\b|\bà\s+vendre\b|\ba\s+vendre\b|"
    r"\bя\s+продаю\b|\bмы\s+продаем\b|\bпрода[её]тся\b)",
    re.I,
)

SELLER_MARKETING_RE = re.compile(
    r"(?:contact\s+us|whatsapp|dm\s+(?:me|us)|book\s+a\s+viewing|available\s+now|"
    r"real\s+estate\s+agent|estate\s+agent|realtor|broker|developer|listing\s+(?:id|ref)|property\s+(?:id|ref)|"
    r"immobilienmakler|makler|expos[ée]|objektnummer|courtage|"
    r"makelaar|immokantoor|agence\s+immobili[eè]re|courtier|"
    r"starting\s+from|price\s+from|ab\s+€|vanaf\s+€|à\s+partir\s+de)",
    re.I,
)

OTHER_COUNTRY_RE = re.compile(
    r"\b(?:spain|spanien|spanje|espagne|portugal|italy|italien|italië|italie|france|frankreich|frankrijk|"
    r"greece|griechenland|griekenland|cyprus|zypern|north\s+cyprus|nordzypern|turkey|türkei|turkije|"
    r"dubai|uae|montenegro|croatia|kroatien|kroatië)\b",
    re.I,
)

PROFILES = {
    "germany_home": {
        "icon": "🇩🇪",
        "title": "GERMANY HOME BUYER RADAR",
        "target": "germany",
        "target_re": re.compile(r"\b(?:germany|deutschland|berlin|m[üu]nchen|munich|hamburg|frankfurt|k[öo]ln|cologne|d[üu]sseldorf|stuttgart|leipzig|n[üu]rnberg)\b", re.I),
        "query_marker": re.compile(r"germany|deutschland|berlin|münchen|munich|hamburg|frankfurt|köln|cologne|düsseldorf|stuttgart", re.I),
        "queries": [
            'Deutschland "Wohnung zum Kauf gesucht" Forum',
            'Deutschland "Haus zum Kauf gesucht" Forum',
            'Deutschland "suche Wohnung zum Kauf"',
            'Berlin "suche Wohnung zum Kauf" Forum',
            'München "Wohnung kaufen" "suche" Forum',
            'Hamburg "Haus kaufen" "suche" Forum',
            'site:reddit.com Germany "looking to buy a house"',
            'site:reddit.com Berlin "looking to buy apartment"',
            'site:expat.com Germany "buy apartment" forum',
            'site:gutefrage.net Wohnung kaufen suche',
            'site:finanztip.de/community Immobilie kaufen suche',
            'site:hausbau-forum.de Haus kaufen suche',
        ],
    },
    "netherlands_home": {
        "icon": "🇳🇱",
        "title": "NETHERLANDS HOME BUYER RADAR",
        "target": "netherlands",
        "target_re": re.compile(r"\b(?:netherlands|nederland|amsterdam|rotterdam|den\s+haag|the\s+hague|utrecht|eindhoven|haarlem|almere|groningen)\b", re.I),
        "query_marker": re.compile(r"netherlands|nederland|amsterdam|rotterdam|den haag|the hague|utrecht|eindhoven|haarlem", re.I),
        "queries": [
            'Nederland "koopwoning gezocht" forum',
            'Nederland "huis om te kopen gezocht"',
            'Nederland "ik zoek een huis om te kopen"',
            'Amsterdam "woning kopen" "ik zoek" forum',
            'Rotterdam "koopwoning gezocht"',
            'Utrecht "huis kopen" "zoek" forum',
            'site:reddit.com Netherlands "looking to buy a house"',
            'site:reddit.com Amsterdam "buy apartment"',
            'site:expat.com Netherlands "buy house" forum',
            'site:tweakers.net woning kopen zoek',
            'site:forum.fok.nl huis kopen zoek',
            'site:investeerders.nl woning kopen',
        ],
    },
    "belgium_home": {
        "icon": "🇧🇪",
        "title": "BELGIUM HOME BUYER RADAR",
        "target": "belgium",
        "target_re": re.compile(r"\b(?:belgium|belgi[ëe]|belgique|brussels|brussel|bruxelles|antwerp|antwerpen|gent|ghent|brugge|leuven|li[eè]ge|charleroi)\b", re.I),
        "query_marker": re.compile(r"belgium|belgië|belgie|belgique|brussels|brussel|bruxelles|antwerp|antwerpen|gent|ghent|leuven", re.I),
        "queries": [
            'België "koopwoning gezocht" forum',
            'België "huis om te kopen gezocht"',
            'België "ik zoek een huis" kopen',
            'Brussel "appartement kopen" "zoek" forum',
            'Antwerpen "woning kopen" "zoek" forum',
            'Belgique "recherche appartement à acheter" forum',
            'Bruxelles "cherche appartement à acheter"',
            'site:reddit.com Belgium "looking to buy a house"',
            'site:expat.com Belgium "buy apartment" forum',
            'site:pim.be cherche appartement acheter',
            'site:bouwinfo.be woning kopen zoek',
        ],
    },
    "switzerland_home": {
        "icon": "🇨🇭",
        "title": "SWITZERLAND HOME BUYER RADAR",
        "target": "switzerland",
        "target_re": re.compile(r"\b(?:switzerland|schweiz|suisse|svizzera|z[üu]rich|zurich|geneva|gen[èe]ve|lausanne|basel|bern|luzern|lucerne|zug)\b", re.I),
        "query_marker": re.compile(r"switzerland|schweiz|suisse|svizzera|zürich|zurich|geneva|genève|lausanne|basel|bern|zug", re.I),
        "queries": [
            'Schweiz "Wohnung zum Kauf gesucht" Forum',
            'Schweiz "Haus zum Kauf gesucht" Forum',
            'Schweiz "suche Wohnung zum Kauf"',
            'Zürich "Wohnung kaufen" "suche" Forum',
            'Basel "Haus kaufen" "suche" Forum',
            'Suisse "recherche appartement à acheter" forum',
            'Genève "cherche appartement à acheter"',
            'site:reddit.com Switzerland "looking to buy a house"',
            'site:englishforum.ch "buy apartment" Switzerland',
            'site:expat.com Switzerland "buy house" forum',
            'site:beobachter.ch Wohnung kaufen Forum',
        ],
    },
}


def now_utc():
    return datetime.now(timezone.utc)


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def user_source(url: str) -> bool:
    d = domain_of(url)
    return any(d == x or d.endswith("." + x) for x in USER_DOMAINS)


def plain(value: str) -> str:
    return " ".join(BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True).split())


def parse_date(value: str):
    if not value:
        return None
    raw = str(value).strip()
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = parsedate_to_datetime(raw)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _target_match(profile: str, text: str, item: dict) -> tuple[bool, bool]:
    spec = PROFILES[profile]
    if spec["target_re"].search(text):
        return True, False

    # Search snippets are often truncated and lose the country name. We allow a
    # query-context bridge only when the result still looks like a genuine buyer
    # request and does not explicitly point at another foreign market.
    query = str(item.get("discovery_query") or "")
    if spec["query_marker"].search(query) and not OTHER_COUNTRY_RE.search(text):
        return True, True
    return False, False


def classify(profile: str, item: dict):
    if profile not in PROFILES:
        return None
    url = str(item.get("url") or "")
    if not url or not user_source(url):
        return None

    text = plain(f"{item.get('title','')} {item.get('text','')} {item.get('author','')}")
    if not text or RENT_RE.search(text):
        return None

    buyer_voice = bool(BUYER_VOICE_RE.search(text) or DIRECT_DEMAND_RE.search(text))
    prop = bool(PROPERTY_RE.search(text))
    if not buyer_voice or not prop:
        return None

    if SELLER_STRONG_RE.search(text):
        return None
    seller_hits = len(SELLER_MARKETING_RE.findall(text))
    if seller_hits >= 2:
        return None

    target_ok, bridged = _target_match(profile, text, item)
    if not target_ok:
        return None

    published = parse_date(item.get("published", ""))
    if published and published < now_utc() - timedelta(hours=LOOKBACK_HOURS):
        return None

    first = bool(FIRST_PERSON_RE.search(text))
    concrete = bool(CONCRETE_RE.search(text))
    terse = bool(DIRECT_DEMAND_RE.search(text))
    intent = min(100, 72 + (10 if first else 0) + (10 if concrete else 0) + (6 if terse else 0))
    label = "HOT" if concrete and (first or terse) else "WARM"
    credibility = min(96, 70 + (8 if published else 0) + (6 if item.get("author") else 0) + (5 if domain_of(url) in {"reddit.com", "expat.com", "expatforum.com", "englishforum.ch"} else 0) - (5 if bridged else 0))

    return {
        **item,
        "profile": profile,
        "target_market": PROFILES[profile]["target"],
        "classification": label,
        "intent_score": intent,
        "credibility_score": credibility,
        "market_fit_score": 99,
        "target_context_bridge": bridged,
        "scanned_at": now_utc().isoformat(),
    }


def _bing(query: str):
    cutoff = (now_utc() - timedelta(hours=LOOKBACK_HOURS)).date().isoformat()
    full_query = f"{query} after:{cutoff}"
    url = f"https://www.bing.com/search?q={quote_plus(full_query)}&format=rss"
    try:
        response = SESSION.get(url, timeout=20)
    except Exception as exc:
        print("LOCAL_HOME_BING_EXCEPTION", query, exc)
        return []
    if response.status_code != 200:
        print("LOCAL_HOME_BING_ERROR", response.status_code, query)
        return []
    out = []
    try:
        root = ET.fromstring(response.text)
        for node in root.findall(".//item"):
            link = (node.findtext("link") or "").strip()
            if not link:
                continue
            out.append({
                "source": "Bing RSS",
                "url": link,
                "title": plain(node.findtext("title") or ""),
                "text": plain(node.findtext("description") or ""),
                "published": (node.findtext("pubDate") or "").strip(),
                "author": "",
                "discovery_query": query,
            })
    except Exception as exc:
        print("LOCAL_HOME_BING_PARSE_ERROR", query, exc)
    print(f"LOCAL_HOME_BING_OK profile={PROFILE} query={query!r} results={len(out)}")
    return out


def _serper(query: str):
    key = os.getenv("SERPER_API_KEY", "").strip()
    if not key:
        return []
    cutoff = (now_utc() - timedelta(hours=LOOKBACK_HOURS)).date().isoformat()
    try:
        response = SESSION.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": f"{query} after:{cutoff}", "num": 10, "tbs": "qdr:w"},
            timeout=25,
        )
    except Exception as exc:
        print("LOCAL_HOME_SERPER_EXCEPTION", query, exc)
        return []
    if response.status_code != 200:
        print("LOCAL_HOME_SERPER_ERROR", response.status_code, response.text[:220])
        return []
    out = []
    for row in (response.json().get("organic") or []):
        out.append({
            "source": "Serper",
            "url": row.get("link", ""),
            "title": row.get("title", ""),
            "text": row.get("snippet", ""),
            "published": row.get("date", ""),
            "author": "",
            "discovery_query": query,
        })
    print(f"LOCAL_HOME_SERPER_OK profile={PROFILE} query={query!r} results={len(out)}")
    return out


def lead_key(profile: str, lead: dict) -> str:
    basis = f"{profile}|{lead.get('url','')}|{plain(lead.get('text',''))[:180]}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def notified_before(db, key: str, days: int = 7) -> bool:
    if not db:
        return False
    try:
        snap = db.collection(NOTIFIED_COLLECTION).document(key).get()
        if not snap.exists:
            return False
        data = snap.to_dict() or {}
        dt = parse_date(data.get("notified_at", ""))
        return bool(dt and dt >= now_utc() - timedelta(days=days))
    except Exception as exc:
        print("LOCAL_HOME_DEDUPE_READ_ERROR", exc)
        return False


def mark_notified(db, key: str, lead: dict):
    if not db:
        return
    try:
        db.collection(NOTIFIED_COLLECTION).document(key).set({
            "profile": PROFILE,
            "target_market": lead.get("target_market", ""),
            "url": lead.get("url", ""),
            "classification": lead.get("classification", ""),
            "notified_at": now_utc().isoformat(),
        }, merge=True)
    except Exception as exc:
        print("LOCAL_HOME_DEDUPE_WRITE_ERROR", exc)


def run():
    if PROFILE not in PROFILES:
        raise SystemExit(f"Unknown LOCAL_HOME_RADAR_PROFILE={PROFILE}")

    started = now_utc()
    spec = PROFILES[PROFILE]
    queries = spec["queries"]
    raw = []
    for query in queries[:BING_QUERY_LIMIT]:
        raw.extend(_bing(query))
    for query in queries[:SERPER_QUERY_LIMIT]:
        raw.extend(_serper(query))

    unique = {}
    for item in raw:
        url = str(item.get("url") or "")
        if url:
            unique[url] = item

    leads = []
    for item in unique.values():
        lead = classify(PROFILE, item)
        if lead:
            leads.append(lead)

    leads.sort(
        key=lambda x: (
            x.get("classification") == "HOT",
            int(x.get("intent_score") or 0),
            int(x.get("credibility_score") or 0),
        ),
        reverse=True,
    )

    db = main.firestore_client()
    new = []
    for lead in leads:
        key = lead_key(PROFILE, lead)
        if notified_before(db, key):
            continue
        new.append(lead)
        mark_notified(db, key, lead)

    scan_id = f"{started.strftime('%Y%m%d%H%M%S')}_{PROFILE}"
    if db:
        try:
            ref = db.collection(SCAN_COLLECTION).document(scan_id)
            batch = db.batch()
            for lead in leads[:100]:
                key = lead_key(PROFILE, lead)
                batch.set(ref.collection("leads").document(key), lead, merge=True)
            batch.set(ref, {
                "profile": PROFILE,
                "target_market": spec["target"],
                "started_at": started.isoformat(),
                "finished_at": now_utc().isoformat(),
                "raw_results": len(raw),
                "unique_results": len(unique),
                "qualified": len(leads),
                "new_to_notify": len(new),
                "lookback_hours": LOOKBACK_HOURS,
                "serper_enabled": bool(os.getenv("SERPER_API_KEY", "").strip()),
            }, merge=True)
            batch.commit()
        except Exception as exc:
            print("LOCAL_HOME_FIRESTORE_ERROR", exc)

    print("LOCAL_HOME_RADAR_COMPLETE", json.dumps({
        "profile": PROFILE,
        "target_market": spec["target"],
        "raw": len(raw),
        "unique": len(unique),
        "qualified": len(leads),
        "new": len(new),
    }, ensure_ascii=False))

    # Only actionable leads are sent; empty scans stay silent.
    if not new:
        return []

    lines = [f"{spec['icon']} BAY-S {spec['title']} | {len(new)} YENİ LEAD"]
    for lead in new[:10]:
        excerpt = plain(lead.get("text", ""))[:280]
        lines.append(
            f"\n{lead['classification']} | hedef={spec['target']} | {lead.get('source','')} | "
            f"I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']}\n"
            f"{lead.get('title','')[:120]}\n{excerpt}\n{lead.get('url','')}"
        )
    main.notify_telegram("\n".join(lines))
    return new


if __name__ == "__main__":
    run()
