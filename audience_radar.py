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


PROFILE = os.getenv("AUDIENCE_RADAR_PROFILE", "germany").strip().lower()
LOOKBACK_HOURS = int(os.getenv("AUDIENCE_LOOKBACK_HOURS", "48"))
BING_QUERY_LIMIT = int(os.getenv("AUDIENCE_BING_QUERY_LIMIT", "10"))
SERPER_QUERY_LIMIT = int(os.getenv("AUDIENCE_SERPER_QUERY_LIMIT", "6"))
NOTIFIED_COLLECTION = "bay_s_audience_notified"
SCAN_COLLECTION = "bay_s_audience_scans"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; BAY-S-Audience-Radar/1.0)",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8,nl;q=0.8,fr;q=0.7",
})

USER_DOMAINS = {
    "reddit.com", "old.reddit.com", "expat.com", "expatforum.com", "nomadgate.com",
    "bogleheads.org", "moneysavingexpert.com", "property118.com", "housepricecrash.co.uk",
    "auswandererforum.de", "wertpapier-forum.de", "wiwi-treff.de", "tweakers.net",
    "pim.be", "finary.com", "investisseurs-heureux.fr", "forum-eu.com", "englishforum.ch",
    "internations.org", "facebook.com", "threads.net", "x.com", "twitter.com", "t.me",
    "finanzaonline.com", "propit.it", "allesamerika.com", "investeerders.nl",
}

PROPERTY_RE = re.compile(
    r"(?:property|real\s+estate|apartment|flat|house|home|villa|studio|land|plot|second\s+home|holiday\s+home|"
    r"immobilie|wohnung|haus|ferienwohnung|ferienhaus|grundst(?:u|ü)ck|auslandsimmobilie|"
    r"woning|huis|vastgoed|appartement|vakantiehuis|tweede\s+huis|"
    r"immobilier|appartement|maison|villa|résidence|residence|bien\s+immobilier|"
    r"квартир\w*|дом\w*|вилл\w*|недвижимост\w*)",
    re.I,
)

BUY_RE = re.compile(
    r"(?:"
    r"\b(?:i|we)\b.{0,50}\b(?:want|looking|planning|plan|considering|ready|need|seeking)\b.{0,55}\b(?:buy|purchase|invest|property|apartment|house|villa|home)\b|"
    r"\blooking\s+to\s+buy\b|\bwant\s+to\s+buy\b|\bplanning\s+to\s+buy\b|\bbuying\s+property\b|\bsecond\s+home\b|\bholiday\s+home\b|"
    r"\b(?:ich|wir)\b.{0,45}\b(?:suche|suchen|möchte|moechte|möchten|moechten|will|wollen|plane|planen|überlege|ueberlege)\b.{0,55}\b(?:kaufen|investieren|immobilie|wohnung|haus|villa)\b|"
    r"\bimmobilie\s+im\s+ausland\s+kaufen\b|\bauslandsimmobilie\b|\bferien(?:wohnung|haus)\s+kaufen\b|"
    r"\b(?:ik|wij|we)\b.{0,45}\b(?:zoek|zoeken|wil|willen|plan|plannen|overweeg|overwegen)\b.{0,55}\b(?:kopen|investeren|woning|huis|vastgoed|appartement)\b|"
    r"\b(?:woning|huis|vastgoed|tweede\s+huis|vakantiehuis)\s+in\s+het\s+buitenland\b|"
    r"\b(?:je|nous)\b.{0,45}\b(?:cherche|cherchons|veux|voulons|souhaite|souhaitons|prévois|prevoyons)\b.{0,55}\b(?:acheter|investir|immobilier|appartement|maison|villa)\b|"
    r"\bacheter\s+(?:un\s+)?bien\s+immobilier\s+à\s+l'étranger\b|"
    r"\b(?:я|мы)\b.{0,45}\b(?:хочу|хотим|ищу|ищем|планир\w*|готов\w*)\b.{0,55}\b(?:купить|покупк\w*|недвижимост\w*|квартир\w*|дом\w*|вилл\w*)\b"
    r")",
    re.I | re.S,
)

QUESTION_BUY_RE = re.compile(
    r"(?:where\s+should\s+i\s+buy|which\s+country\s+.*buy|best\s+country\s+.*property|"
    r"wo\s+soll\w*\s+ich\s+.*kaufen|welches\s+land\s+.*immobilie|"
    r"waar\s+.*(?:woning|huis|vastgoed)\s+kopen|welk\s+land\s+.*kopen|"
    r"où\s+acheter|ou\s+acheter|quel\s+pays\s+.*acheter)",
    re.I,
)

FIRST_PERSON_RE = re.compile(
    r"\b(?:i|we|my|our|ich|wir|mein\w*|unser\w*|ik|wij|we|mijn|ons|onze|je|nous|mon|ma|notre|я|мы|мой|наш)\b",
    re.I,
)

CONCRETE_RE = re.compile(
    r"(?:[£€$₣]\s*\d[\d\s.,]*(?:\s*[kKmM])?|\b\d{2,4}\s*[kK]\b|\bbudget\b|\bbudgett?\b|\bbudget\s+van\b|"
    r"\bbudget\s+de\b|\bmortgage\b|\bdeposit\b|\bpayment\s+plan\b|\btitle\s+deed\b|"
    r"\bhypothek\b|\beigenkapital\b|\banzahlung\b|\bfinanzierung\b|"
    r"\bhypotheek\b|\baanbetaling\b|\bfinanciering\b|\bprijsklasse\b|"
    r"\bprêt\b|\bpret\b|\bapport\b|\bfinancement\b|\bprix\b|\bипотек\w*\b|\bбюджет\b)",
    re.I,
)

RENT_RE = re.compile(
    r"(?:for\s+rent|looking\s+to\s+rent|rental|per\s+month|monthly|mieten|miete|zur\s+miete|"
    r"huren|huur|per\s+maand|à\s+louer|a\s+louer|location\s+mensuelle|аренд\w*|снять|в\s+месяц)",
    re.I,
)

SELLER_RE = re.compile(
    r"(?:for\s+sale|available\s+now|contact\s+us|contact\s+me|whatsapp|dm\s+(?:me|us)|estate\s+agent|real\s+estate\s+agent|realtor|broker|developer|listing|our\s+project|our\s+properties|"
    r"zu\s+verkaufen|makler|immobilienmakler|projektentwickler|angebot\s+ab|"
    r"te\s+koop|makelaar|vastgoedmakelaar|projectontwikkelaar|"
    r"à\s+vendre|a\s+vendre|agent\s+immobilier|promoteur|прода[её]тся|продам|агентств\w*|риэлтор)",
    re.I,
)

NEGATIVE_RE = re.compile(
    r"(?:already\s+bought|already\s+purchased|i\s+bought|we\s+bought|not\s+buying|no\s+longer\s+looking|"
    r"bereits\s+gekauft|nicht\s+mehr\s+auf\s+der\s+suche|al\s+gekocht|niet\s+meer\s+op\s+zoek|"
    r"déjà\s+acheté|deja\s+achete|plus\s+à\s+la\s+recherche|купил|купили|передумал)",
    re.I,
)

GOLDEN_CONTEXT_RE = re.compile(
    r"(?:golden\s+visa|golden\s+residence|residency\s+by\s+investment|residence\s+by\s+investment|investment\s+migration|investor\s+visa|"
    r"goldenes?\s+visum|aufenthalt\s+durch\s+investition|aufenthaltsgenehmigung\s+durch\s+investition|"
    r"gouden\s+visum|verblijfsvergunning\s+door\s+investering|"
    r"visa\s+dor[ée]|résidence\s+par\s+investissement|residence\s+par\s+investissement|"
    r"золот\w*\s+виз\w*|внж\s+за\s+инвестиц\w*)",
    re.I,
)

GOLDEN_INTENT_RE = re.compile(
    r"(?:"
    r"\b(?:i|we)\b.{0,55}\b(?:want|looking|considering|planning|need|interested)\b.{0,70}\b(?:golden\s+visa|residency|residence|investor\s+visa|investment)\b|"
    r"\bwhich\s+(?:golden\s+visa|country|program)\b|\bminimum\s+investment\b|\bwhat\s+is\s+the\s+minimum\b|\brequirements?\b|"
    r"\b(?:ich|wir)\b.{0,55}\b(?:suche|suchen|möchte|moechte|will|wollen|überlege|ueberlege)\b.{0,70}\b(?:visum|aufenthalt|investition)\b|"
    r"\b(?:ik|wij|we)\b.{0,55}\b(?:zoek|zoeken|wil|willen|overweeg|overwegen)\b.{0,70}\b(?:visum|verblijf|investering)\b|"
    r"\b(?:je|nous)\b.{0,55}\b(?:cherche|cherchons|veux|voulons|souhaite|souhaitons)\b.{0,70}\b(?:visa|résidence|residence|investissement)\b|"
    r"\b(?:я|мы)\b.{0,55}\b(?:хочу|хотим|ищу|ищем|интерес\w*|планир\w*)\b.{0,70}\b(?:виз\w*|внж|инвестиц\w*)\b"
    r")",
    re.I | re.S,
)

AUDIENCE_ANCHORS = {
    "germany": re.compile(r"(?:\bgermany\b|\bdeutschland\b|\bgerman\b|\bdeutsch\w*\b|\bberlin\b|\bm[üu]nchen\b|\bmunich\b|\bfrankfurt\b|\bhamburg\b|\bk[öo]ln\b|\bcologne\b|\bd[üu]sseldorf\b)", re.I),
    "netherlands": re.compile(r"(?:\bnetherlands\b|\bnederland\b|\bdutch\b|\bnederlandse?\b|\bamsterdam\b|\brotterdam\b|\bden\s+haag\b|\bthe\s+hague\b|\butrecht\b)", re.I),
    "belgium": re.compile(r"(?:\bbelgium\b|\bbelgi[ëe]\b|\bbelgique\b|\bbelgian\b|\bbrussels\b|\bbruxelles\b|\bantwerp\b|\bantwerpen\b|\bghent\b|\bgent\b|\bvlaanderen\b|\bflanders\b)", re.I),
    "switzerland": re.compile(r"(?:\bswitzerland\b|\bschweiz\b|\bsuisse\b|\bsvizzera\b|\bswiss\b|\bz[üu]rich\b|\bzurich\b|\bgeneva\b|\bgen[èe]ve\b|\bbasel\b|\bbern\b|\blausanne\b)", re.I),
}

SOURCE_ANCHORS = {
    "germany": ("/germany/", "auswandererforum.de", "wertpapier-forum.de", "wiwi-treff.de"),
    "netherlands": ("/netherlands/", "tweakers.net", "investeerders.nl"),
    "belgium": ("/belgium/", "pim.be"),
    "switzerland": ("/switzerland/", "englishforum.ch"),
}

PROFILE_META = {
    "germany": ("🇩🇪", "GERMANY BUYER RADAR"),
    "netherlands": ("🇳🇱", "NETHERLANDS BUYER RADAR"),
    "belgium": ("🇧🇪", "BELGIUM BUYER RADAR"),
    "switzerland": ("🇨🇭", "SWITZERLAND BUYER RADAR"),
    "golden_visa": ("🛂", "GOLDEN VISA RADAR"),
}

QUERIES = {
    "germany": [
        'Deutschland "Immobilie im Ausland kaufen" Forum',
        'Deutschland "Ferienwohnung im Ausland kaufen" Erfahrung',
        'Deutschland "zweites Haus im Ausland" kaufen Forum',
        'Deutschland Auswandern Immobilie kaufen Forum',
        'Deutschland "Nordzypern" "Wohnung kaufen"',
        'Deutschland "North Cyprus" property buy forum',
        'site:reddit.com Germany "buy property abroad"',
        'site:expat.com Germany "buy property abroad"',
        'site:auswandererforum.de Immobilie Ausland kaufen',
        'site:wertpapier-forum.de Auslandsimmobilie kaufen',
    ],
    "netherlands": [
        'Nederland "huis in het buitenland kopen" forum',
        'Nederland "tweede huis in het buitenland" kopen',
        'Nederland "vastgoed in het buitenland" kopen forum',
        'Nederland emigreren woning kopen buitenland',
        'Nederland "Noord Cyprus" woning kopen',
        'Nederland "North Cyprus" property buy forum',
        'site:reddit.com Netherlands "buy property abroad"',
        'site:expat.com Netherlands "buy property abroad"',
        'site:tweakers.net vastgoed buitenland kopen',
        'site:investeerders.nl vastgoed buitenland',
    ],
    "belgium": [
        'België "vastgoed in het buitenland" kopen forum',
        'België "tweede verblijf" buitenland kopen',
        'Belgique "acheter immobilier à l’étranger" forum',
        'Belgique "résidence secondaire" acheter étranger',
        'België "Noord Cyprus" woning kopen',
        'Belgique "Chypre du Nord" acheter immobilier',
        'site:reddit.com Belgium "buy property abroad"',
        'site:expat.com Belgium "buy property abroad"',
        'site:pim.be immobilier étranger acheter',
        'site:pim.be vastgoed buitenland kopen',
    ],
    "switzerland": [
        'Schweiz "Immobilie im Ausland kaufen" Forum',
        'Schweiz "Ferienwohnung im Ausland kaufen"',
        'Suisse "acheter immobilier à l’étranger" forum',
        'Switzerland "buy property abroad" forum',
        'Schweiz "Nordzypern" Immobilie kaufen',
        'Suisse "Chypre du Nord" acheter immobilier',
        'site:reddit.com Switzerland "buy property abroad"',
        'site:expat.com Switzerland "buy property abroad"',
        'site:englishforum.ch property abroad buy',
        'site:englishforum.ch second home abroad',
    ],
    "golden_visa": [
        '"golden visa" "I want" investment forum',
        '"golden visa" "looking for" property investment forum',
        '"golden visa" "which country" investor forum',
        '"residency by investment" "looking for" forum',
        '"residence by investment" "minimum investment" forum',
        '"investor visa" property "budget" forum',
        'site:reddit.com "golden visa" "looking for"',
        'site:reddit.com "residency by investment" property',
        'site:nomadgate.com "golden visa" investment',
        'site:expatforum.com "golden visa" property',
    ],
}

TARGET_MARKERS = [
    ("north_cyprus", re.compile(r"north(?:ern)?\s+cyprus|nordzypern|chypre\s+du\s+nord|noord[- ]cyprus|kuzey\s+k[ıi]br[ıi]s|северн\w*\s+кипр", re.I)),
    ("greece", re.compile(r"\bgreece\b|\bgriechenland\b|\bgr[èe]ce\b|\bgriekenland\b", re.I)),
    ("portugal", re.compile(r"\bportugal\b", re.I)),
    ("spain", re.compile(r"\bspain\b|\bspanien\b|\bespagne\b|\bspanje\b", re.I)),
    ("italy", re.compile(r"\bitaly\b|\bitalien\b|\bitalie\b|\bitalië\b", re.I)),
    ("cyprus", re.compile(r"\bcyprus\b|\bzypern\b|\bchypre\b|\bcyprus\b", re.I)),
    ("montenegro", re.compile(r"\bmontenegro\b", re.I)),
    ("turkey", re.compile(r"\bturkey\b|\btürkei\b|\bturquie\b|\bturkije\b", re.I)),
]


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
    value = str(value).strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = parsedate_to_datetime(value)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _audience_match(profile: str, text: str, url: str) -> bool:
    if profile == "golden_visa":
        return bool(GOLDEN_CONTEXT_RE.search(text))
    anchor = AUDIENCE_ANCHORS[profile]
    if anchor.search(text):
        return True
    low_url = (url or "").lower()
    return any(marker in low_url for marker in SOURCE_ANCHORS[profile])


def detect_target(text: str, profile: str) -> str:
    for name, rx in TARGET_MARKERS:
        if rx.search(text):
            if name != profile:
                return name
    return "unspecified_abroad"


def classify(profile: str, item: dict):
    text = plain(f"{item.get('title','')} {item.get('text','')} {item.get('author','')}")
    url = str(item.get("url") or "")
    if not url or not user_source(url):
        return None
    if NEGATIVE_RE.search(text) or RENT_RE.search(text):
        return None
    seller_hits = len(SELLER_RE.findall(text))

    if profile == "golden_visa":
        if not GOLDEN_CONTEXT_RE.search(text) or not GOLDEN_INTENT_RE.search(text):
            return None
        first = bool(FIRST_PERSON_RE.search(text))
        concrete = bool(CONCRETE_RE.search(text))
        if seller_hits >= 2 and not first:
            return None
        intent = min(100, 76 + (10 if first else 0) + (10 if concrete else 0) + (4 if PROPERTY_RE.search(text) else 0))
        label = "HOT" if first and concrete else "WARM"
        target = detect_target(text, profile)
    else:
        if not _audience_match(profile, text, url):
            return None
        buyer = bool(BUY_RE.search(text) or QUESTION_BUY_RE.search(text))
        prop = bool(PROPERTY_RE.search(text))
        if not buyer or not prop:
            return None
        first = bool(FIRST_PERSON_RE.search(text))
        concrete = bool(CONCRETE_RE.search(text))
        if seller_hits >= 2 and not first:
            return None
        intent = min(100, 70 + (12 if buyer else 0) + (8 if first else 0) + (8 if concrete else 0))
        label = "HOT" if first and concrete else "WARM"
        target = detect_target(text, profile)

    published = parse_date(item.get("published", ""))
    if published and published < now_utc() - timedelta(hours=LOOKBACK_HOURS):
        return None

    credibility = min(95, 68 + (8 if published else 0) + (6 if item.get("author") else 0) + (5 if domain_of(url) in {"reddit.com", "expat.com", "expatforum.com", "englishforum.ch"} else 0))
    return {
        **item,
        "audience": profile,
        "target_market": target,
        "classification": label,
        "intent_score": intent,
        "credibility_score": credibility,
        "market_fit_score": 98,
        "scanned_at": now_utc().isoformat(),
    }


def _bing(query: str):
    cutoff = (now_utc() - timedelta(hours=LOOKBACK_HOURS)).date().isoformat()
    full_query = f"{query} after:{cutoff}"
    url = f"https://www.bing.com/search?q={quote_plus(full_query)}&format=rss"
    try:
        response = SESSION.get(url, timeout=20)
    except Exception as exc:
        print("AUDIENCE_BING_EXCEPTION", query, exc)
        return []
    if response.status_code != 200:
        print("AUDIENCE_BING_ERROR", response.status_code, query)
        return []
    out = []
    try:
        root = ET.fromstring(response.text)
        for node in root.findall(".//item"):
            link = (node.findtext("link") or "").strip()
            title = plain(node.findtext("title") or "")
            desc = plain(node.findtext("description") or "")
            published = (node.findtext("pubDate") or "").strip()
            if not link:
                continue
            out.append({
                "source": "Bing RSS",
                "url": link,
                "title": title,
                "text": desc,
                "published": published,
                "author": "",
                "discovery_query": query,
            })
    except Exception as exc:
        print("AUDIENCE_BING_PARSE_ERROR", query, exc)
    print(f"AUDIENCE_BING_OK profile={PROFILE} query={query!r} results={len(out)}")
    return out


def _serper(query: str):
    key = os.getenv("SERPER_API_KEY", "").strip()
    if not key:
        return []
    try:
        response = SESSION.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": query, "num": 10, "tbs": "qdr:w"},
            timeout=25,
        )
    except Exception as exc:
        print("AUDIENCE_SERPER_EXCEPTION", query, exc)
        return []
    if response.status_code != 200:
        print("AUDIENCE_SERPER_ERROR", response.status_code, response.text[:220])
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
    print(f"AUDIENCE_SERPER_OK profile={PROFILE} query={query!r} results={len(out)}")
    return out


def lead_key(profile: str, lead: dict) -> str:
    basis = f"{profile}|{lead.get('url','')}|{plain(lead.get('text',''))[:240]}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def notified_before(db, key: str) -> bool:
    if not db:
        return False
    try:
        snap = db.collection(NOTIFIED_COLLECTION).document(key).get()
        if not snap.exists:
            return False
        data = snap.to_dict() or {}
        dt = parse_date(data.get("notified_at", ""))
        return bool(dt and dt >= now_utc() - timedelta(days=7))
    except Exception as exc:
        print("AUDIENCE_DEDUPE_READ_ERROR", exc)
        return False


def mark_notified(db, key: str, lead: dict):
    if not db:
        return
    try:
        db.collection(NOTIFIED_COLLECTION).document(key).set({
            "profile": PROFILE,
            "url": lead.get("url", ""),
            "classification": lead.get("classification", ""),
            "notified_at": now_utc().isoformat(),
        }, merge=True)
    except Exception as exc:
        print("AUDIENCE_DEDUPE_WRITE_ERROR", exc)


def run():
    if PROFILE not in QUERIES:
        raise SystemExit(f"Unknown AUDIENCE_RADAR_PROFILE={PROFILE}")

    started = now_utc()
    queries = QUERIES[PROFILE]
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

    leads.sort(key=lambda x: (x.get("classification") == "HOT", int(x.get("intent_score") or 0), int(x.get("credibility_score") or 0)), reverse=True)
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
            print("AUDIENCE_FIRESTORE_ERROR", exc)

    icon, title = PROFILE_META[PROFILE]
    print("AUDIENCE_RADAR_COMPLETE", json.dumps({
        "profile": PROFILE,
        "raw": len(raw),
        "unique": len(unique),
        "qualified": len(leads),
        "new": len(new),
    }, ensure_ascii=False))

    # Noise policy: only real leads are sent; empty runs stay silent.
    if not new:
        return []

    lines = [f"{icon} BAY-S {title} | {len(new)} YENİ LEAD"]
    for lead in new[:10]:
        excerpt = plain(lead.get("text", ""))[:280]
        target = lead.get("target_market") or "unspecified_abroad"
        lines.append(
            f"\n{lead['classification']} | hedef={target} | {lead.get('source','')} | "
            f"I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']}\n"
            f"{lead.get('title','')[:120]}\n{excerpt}\n{lead.get('url','')}"
        )
    main.notify_telegram("\n".join(lines))
    return new


if __name__ == "__main__":
    run()
