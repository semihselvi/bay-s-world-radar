import os
import re
import json
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
from google.cloud import firestore
from google.oauth2 import service_account

from config import *

UA = "Mozilla/5.0 (compatible; BAY-S-World-Radar/2.0)"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
EXA_URL = "https://api.exa.ai/search"

DISCOVERY_ONLY_DOMAINS = {
    "prian.ru", "realting.com", "nepokretnost.me", "101evler.com", "ilancik.com",
    "tekce.com", "northern-cyprus-property.com", "getgoldenvisa.com", "imidaily.com",
    "henleyglobal.com", "goldenvisas.com", "jarniascyril.com", "adrianleeds.com",
    "frenchestateagents.com", "germanrealty.org", "thewanderinginvestor.com"
}

USER_SOURCE_DOMAINS = {
    "reddit.com", "nomadgate.com", "bogleheads.org", "expatforum.com", "expat.com",
    "property118.com", "housepricecrash.co.uk", "moneysavingexpert.com", "completefrance.com",
    "forum-eu.com", "awd.ru", "pim.be", "finary.com", "investisseurs-heureux.fr",
    "finanzaonline.com", "auswandererforum.de", "wertpapier-forum.de", "tweakers.net",
    "allesamerika.com", "internations.org", "meetup.com", "montenegroexpats.com",
    "facebook.com", "t.me", "tlgrm.ru", "telegid.me", "telega.io", "chat.whatsapp.com"
}

SOURCE_BUCKETS = [
    {
        "name": "north_cyprus_turkey",
        "domains": ["reddit.com","facebook.com","t.me","tlgrm.ru","telegid.me","telega.io","expat.com","expatforum.com","nomadgate.com","101evler.com","ilancik.com","northern-cyprus-property.com","cyprusliving.org","tekce.com"],
        "query": "real person actively looking to buy property or relocate with purchase intention in North Cyprus, Northern Cyprus, Iskele, Long Beach, Kyrenia, Girne, Esentepe, Famagusta, Gazimağusa, Turkey, Antalya, Alanya, Mersin; include English Turkish Russian discussions, budgets, property requirements, viewing trips and payment/legal questions; prioritize forums, Reddit, Facebook public pages and Telegram public pages; exclude listings, developers and agents"
    },
    {
        "name": "balkans_greece_portugal_spain_italy_cyprus",
        "domains": ["reddit.com","facebook.com","t.me","telegid.me","expat.com","expatforum.com","montenegroexpats.com","internations.org","meetup.com","forum-eu.com","prian.ru","realting.com","finanzaonline.com","nomadgate.com"],
        "query": "real person actively seeking to buy property, investment property, second home, relocation home or Golden Visa property in Montenegro Budva Kotor Tivat, Greece Athens Thessaloniki, Portugal Lisbon Algarve, Spain, Italy or Cyprus; prioritize genuine user questions and experience discussions with budgets, timing, viewing or legal/payment questions; include Russian-speaking and expat communities; exclude property advertisements"
    },
    {
        "name": "western_europe",
        "domains": ["reddit.com","facebook.com","expat.com","expatforum.com","finary.com","investisseurs-heureux.fr","pim.be","wertpapier-forum.de","gathering.tweakers.net","forum-eu.com"],
        "query": "real person asking how or where to buy a house, apartment or investment property in Germany, France, Netherlands, Belgium or Lithuania; relocation and expat property discussions; look for explicit buyer intent, budget, timeframe, viewing, financing, deposit, legal or area comparison; include German French Dutch English discussions; exclude agencies and listings"
    },
    {
        "name": "uk_central_europe",
        "domains": ["reddit.com","facebook.com","expat.com","expatforum.com","property118.com","housepricecrash.co.uk","moneysavingexpert.com","forum-eu.com","auswandererforum.de","forum.allesamerika.com"],
        "query": "real person discussing an active property purchase, relocation with buying intent or overseas investment property from or in the United Kingdom, Poland, Czech Republic or Austria; require concrete buying signals such as budget, specific property, viewing, mortgage, deposit, timeframe or area comparison; English German Polish Czech discussions; do not treat UK as a Golden Visa market"
    },
    {
        "name": "golden_visa_global",
        "domains": ["nomadgate.com","bogleheads.org","expatforum.com","expat.com","reddit.com","facebook.com","forum-eu.com","t.me","tlgrm.ru","telega.io"],
        "query": "real investor or family actively considering Golden Visa, residency by investment or European property purchase; focus on Greece Portugal Italy Cyprus Malta Montenegro and other valid investment residency routes; require concrete property or investment intent, budget, family, timeline, planned visit or legal/payment question; distinguish Italy as non-real-estate Golden Visa route and do not treat UK Germany France Netherlands Belgium as classic Golden Visa property markets"
    },
    {
        "name": "russian_cis_abroad",
        "domains": ["reddit.com","forum.awd.ru","prian.ru","realting.com","t.me","tlgrm.ru","telega.io","facebook.com","expat.com","forum-eu.com","internations.org"],
        "query": "Russian or Kazakh real person looking to buy property abroad, move abroad or invest in property in Montenegro, North Cyprus, Greece, Turkey or Europe; search Russian phrases хочу купить, ищу квартиру, ищу недвижимость, куплю недвижимость, планирую купить, недвижимость за рубежом, инвестиции в недвижимость, переезд, ВНЖ and Kazakhstan Almaty Алматы Astana Астана; require concrete budget, location, property type or timing; exclude seller advertisements"
    }
]


def now_utc():
    return datetime.now(timezone.utc)


def parse_dt(value):
    if not value:
        return None
    value = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(value)
    except Exception:
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(value)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def domain_of(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def source_is_user_generated(url):
    d = domain_of(url)
    if any(d == blocked or d.endswith("." + blocked) for blocked in DISCOVERY_ONLY_DOMAINS):
        return False
    return any(d == allowed or d.endswith("." + allowed) for allowed in USER_SOURCE_DOMAINS)


def text_of(item):
    return " ".join(str(item.get(k, "")) for k in ("title", "text", "author")).strip().lower()


def market_for(text):
    t = text.lower()
    for market, terms in MARKETS.items():
        if any(term.lower() in t for term in terms):
            return market
    return "unknown"


def route_for(market):
    return ROUTES.get(market, "Direct Review")


def contains_any(text, phrases):
    return any(p.lower() in text for p in phrases)


def dedupe_key(item):
    basis = item.get("url") or f"{item.get('source')}|{item.get('title')}|{item.get('author')}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def exa_search(query, domains):
    api_key = os.getenv("EXA_API_KEY", "").strip()
    if not api_key:
        print("EXA_DISABLED missing EXA_API_KEY")
        return []
    payload = {"query": query, "type": "auto", "numResults": min(EXA_NUM_RESULTS, 6), "includeDomains": domains, "contents": {"text": True}}
    response = SESSION.post(EXA_URL, json=payload, headers={"x-api-key": api_key, "Content-Type": "application/json"}, timeout=35)
    if response.status_code != 200:
        print("EXA_ERROR", response.status_code, response.text[:350])
        return []
    data = response.json()
    return [{"source":"Exa","url":x.get("url","") ,"title":x.get("title","") ,"text":x.get("text","") ,"published":x.get("publishedDate","") ,"author":""} for x in data.get("results",[])]


def buyer_scores(item):
    text = text_of(item)
    if not source_is_user_generated(item.get("url", "")) or contains_any(text, NEGATIVE_PHRASES):
        return 0,0,0,"COLD"
    explicit = sum(1 for p in ["looking to buy","want to buy","planning to buy","ready to buy","looking for apartment","looking for property","хочу купить","ищу квартиру","куплю недвижимость","ev almak istiyorum","daire arıyorum","satın almak istiyorum"] if p in text)
    personal = sum(1 for p in ["i am","i'm","we are","we're","my budget","our budget","i want","we want","ben","biz","bütçem","бюджет","мой бюджет","наш бюджет"] if p in text)
    money = bool(re.search(r"(?:€|£|\$|₺|₽)\s?\d[\d,.\s]*(?:k|m)?|\b\d{2,3}\s?[km]\b", text))
    property_type = sum(1 for p in ["apartment","house","villa","property","land","daire","ev","квартира","дом","вилла","недвижимость"] if p in text)
    transaction = sum(1 for p in ["viewing","property viewing","offer","deposit","mortgage","payment plan","lawyer","title deed","reservation","due diligence","ипотека","взнос"] if p in text)
    relocation = sum(1 for p in ["moving to","relocating to","переезд","переезжаем","taşınmak","Kıbrıs'a taşınmak"] if p in text)
    seller_hits = sum(1 for p in EXCLUDE_PHRASES if p.lower() in text)
    personal_story = personal >= 2 or len(text) > 650

    intent = 25 + explicit*12 + personal*6 + (15 if money else 0) + min(12,property_type*3) + min(15,transaction*3) + min(8,relocation*4) - min(35,seller_hits*8)
    credibility = 50 + 14 + (12 if money else 0) + (10 if personal_story else 0) + (8 if personal >= 2 else 0) - min(30,seller_hits*8)
    fit = 50 + (25 if market_for(text) != "unknown" else 0) + (10 if money else 0)
    if "golden visa" in text or "residency by investment" in text:
        fit += 5
    intent=max(0,min(100,intent)); credibility=max(0,min(100,credibility)); fit=max(0,min(100,fit))
    if intent >= 78 and credibility >= 78 and fit >= 70 and (money or transaction >= 2 or personal_story):
        label="HOT"
    elif intent >= 60 and credibility >= 65 and fit >= 60:
        label="WARM"
    elif intent >= 45:
        label="REVIEW"
    else:
        label="COLD"
    return intent,credibility,fit,label


def keep_candidate(item):
    text=text_of(item)
    if not item.get("url") or not source_is_user_generated(item["url"]):
        return False
    if contains_any(text,NEGATIVE_PHRASES) or contains_any(text,["for rent","kiralık","сдам","сдается"]):
        return False
    seller_hits=sum(1 for p in EXCLUDE_PHRASES if p.lower() in text)
    personal=contains_any(text,["i want","i'm looking","we want","we're looking","my budget","our budget","ben","biz","хочу","ищу"])
    if seller_hits >= 2 and not personal:
        return False
    return contains_any(text,INTENT_PHRASES)


def suggested_reply(market):
    replies={
        "north_cyprus":"Your requirements are specific enough to compare areas and total purchase costs rather than just asking price. I would check title/deed position, ongoing fees and how the property fits your intended use before deciding.",
        "turkey":"With a defined area and budget, I would compare total acquisition costs, financing and resale/rental demand before choosing the property.",
        "montenegro":"I would compare the short-listed areas on purchase costs, year-round demand, legal checks and resale liquidity before committing.",
        "greece":"For a Golden Visa-related purchase, separate the residency requirement from the investment decision and compare the property on its own numbers as well.",
        "portugal":"It is worth checking the current residency route separately from the property investment, then comparing net costs, liquidity and long-term use."
    }
    return replies.get(market,"Your requirements are specific enough to compare the area, total purchase costs and long-term use before making a decision.")


def firestore_client():
    raw=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON","").strip()
    if not raw:
        return None
    info=json.loads(raw); creds=service_account.Credentials.from_service_account_info(info)
    return firestore.Client(credentials=creds, project=info.get("project_id"))


def notify_telegram(message):
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); chat_id=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat_id: return
    try:
        SESSION.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat_id,"text":message[:3900]},timeout=15)
    except Exception as exc:
        print("TELEGRAM_NOTIFY_ERROR",exc)


def run():
    started=now_utc(); cutoff=started-timedelta(hours=LOOKBACK_HOURS); seen=set(); leads=[]; exa_calls=0
    for bucket in SOURCE_BUCKETS[:EXA_MAX_CALLS]:
        exa_calls += 1
        print(f"EXA [{exa_calls}/{min(EXA_MAX_CALLS,len(SOURCE_BUCKETS))}] {bucket['name']}")
        try:
            results=exa_search(bucket["query"],bucket["domains"])
        except Exception as exc:
            print("EXA_EXCEPTION",exc); continue
        for item in results:
            item["source_bucket"]=bucket["name"]; key=dedupe_key(item)
            if key in seen: continue
            seen.add(key)
            published=parse_dt(item.get("published"))
            if published and published < cutoff: continue
            if not keep_candidate(item): continue
            market=market_for(text_of(item)); intent,credibility,fit,label=buyer_scores(item)
            if label not in ("HOT","WARM"): continue
            item.update({"market":market,"intent_score":intent,"credibility_score":credibility,"market_fit_score":fit,"classification":label,"route_to":route_for(market),"why":"Explicit buyer language combined with concrete property, budget, timing, location or transaction research on a public user/community source.","suggested_reply":suggested_reply(market),"scanned_at":started.isoformat(),"source_domain":domain_of(item.get("url",""))})
            leads.append(item)

    unique={dedupe_key(x):x for x in leads}; leads=list(unique.values())
    leads.sort(key=lambda x:(x["classification"]=="HOT",x["intent_score"],x["credibility_score"],x["market_fit_score"]),reverse=True)

    db=firestore_client()
    if db:
        batch=db.batch()
        for lead in leads[:100]:
            doc_id=hashlib.sha1((lead.get("url") or lead.get("title","")).encode("utf-8")).hexdigest()
            batch.set(db.collection(COLLECTION).document(doc_id),lead,merge=True)
        batch.set(db.collection(SCAN_LOG_COLLECTION).document(started.strftime("%Y%m%d%H%M%S")),{"started_at":started.isoformat(),"finished_at":now_utc().isoformat(),"exa_calls":exa_calls,"source_baskets":min(EXA_MAX_CALLS,len(SOURCE_BUCKETS)),"unique_candidates":len(seen),"hot_warm":len(leads),"lookback_hours":LOOKBACK_HOURS})
        batch.commit()

    print(f"SCAN_COMPLETE exa_calls={exa_calls} candidates={len(seen)} hot_warm={len(leads)}")
    if leads:
        lines=[f"BAY-S WORLD RADAR | {len(leads)} HOT/WARM | Exa calls: {exa_calls}"]
        for lead in leads[:10]:
            lines.append(f"{lead['classification']} | {lead['market']} | I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']} | {lead.get('title','')[:120]} | {lead.get('url','')}")
        notify_telegram("\n".join(lines))


if __name__ == "__main__":
    run()
