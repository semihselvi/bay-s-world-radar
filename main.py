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
    "frenchestateagents.com", "germanrealty.org", "thewanderinginvestor.com",
    "globalpropertyguide.com", "globalinvestments.net", "portugalist.com", "realtoreurope.com"
}

USER_SOURCE_DOMAINS = {
    "reddit.com", "nomadgate.com", "bogleheads.org", "expatforum.com", "expat.com",
    "property118.com", "housepricecrash.co.uk", "moneysavingexpert.com", "completefrance.com",
    "forum-eu.com", "awd.ru", "pim.be", "finary.com", "investisseurs-heureux.fr",
    "finanzaonline.com", "auswandererforum.de", "wertpapier-forum.de", "tweakers.net",
    "wiwi-treff.de", "propit.it", "allesamerika.com", "internations.org", "meetup.com",
    "montenegroexpats.com", "facebook.com", "t.me", "tlgrm.ru", "telegid.me", "telega.io",
    "chat.whatsapp.com", "cyprusliving.org"
}

EDITORIAL_SIGNALS = ["guide","requirements","cheatsheet","what to know","how to buy","steps to buy","tax regime","tax regimes","residence by investment guide","golden visa requirements","golden visa guide","investor visa guide","real estate guide","market report","property market","what and where","news","analysis","overview","explained","article","editorial","programme","program requirements","complete guide","investment guide","residency guide","non-dom","non dom"]
DISCUSSION_SIGNALS = ["reply","replies","member since","post new topic","subscribe","like","forum","looking for","we're considering","we are considering","i'm considering","i am considering","does anyone recommend","can anyone recommend","anyone know","has anyone","we plan to","we are planning","i plan to","i'm planning","i want to","we want to","my budget","our budget","i need","we need","seeking","help with","advice","recommendation"]

SOURCE_BUCKETS = []

def now_utc(): return datetime.now(timezone.utc)
def parse_dt(value):
    if not value: return None
    value=str(value).strip().replace("Z","+00:00")
    try: dt=datetime.fromisoformat(value)
    except Exception:
        try:
            from email.utils import parsedate_to_datetime
            dt=parsedate_to_datetime(value)
        except Exception: return None
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def extract_dates_from_text(text):
    dates=[]; month_map={"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,"july":7,"august":8,"september":9,"october":10,"november":11,"december":12,"jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
    patterns=[r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b",r"\b(\d{1,2})[./-](\d{1,2})[./-](20\d{2})\b",r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b",r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(20\d{2})\b"]
    for pattern in patterns:
        for m in re.finditer(pattern,text,flags=re.I):
            try:
                if m.group(1).startswith("20"): y,mo,d=int(m.group(1)),int(m.group(2)),int(m.group(3))
                elif m.group(3).startswith("20") and m.group(2).isdigit(): d,mo,y=int(m.group(1)),int(m.group(2)),int(m.group(3))
                else: d,mo,y=int(m.group(1)),month_map[m.group(2).lower()],int(m.group(3))
                dates.append(datetime(y,mo,d,tzinfo=timezone.utc))
            except Exception: pass
    return dates

def verified_published(item):
    direct=parse_dt(item.get("published"))
    if direct: return direct
    dates=extract_dates_from_text(str(item.get("text","")))
    return max(dates) if dates else None

def domain_of(url):
    try: return urlparse(url).netloc.lower().replace("www.","")
    except Exception: return ""
def source_is_user_generated(url):
    d=domain_of(url)
    if any(d==b or d.endswith("."+b) for b in DISCOVERY_ONLY_DOMAINS): return False
    return any(d==a or d.endswith("."+a) for a in USER_SOURCE_DOMAINS)
def text_of(item): return " ".join(str(item.get(k,"")) for k in ("title","text","author")).strip().lower()
def contains_any(text, phrases): return any(str(p).lower() in text for p in phrases)
def discussion_likelihood(item):
    text=text_of(item); score=min(4,sum(1 for p in DISCUSSION_SIGNALS if p.lower() in text))
    if re.search(r"\b(member since|new member|active member|reply|replies|post new topic)\b",text,re.I): score+=3
    if re.search(r"\b(my|our|i'm|i am|we're|we are|benim|bizim|бюджет|хочу|ищу)\b",text,re.I): score+=2
    return score
def editorial_likelihood(item):
    text=text_of(item); score=sum(1 for p in EDITORIAL_SIGNALS if p.lower() in text); url=item.get("url","").lower(); title=str(item.get("title","")).lower()
    if any(p in url for p in ("/news/","/guide","/guides/","/article","/info/")): score+=2
    if any(p in title for p in ("guide","requirements","cheatsheet","what to know","costs and deeds","tax regimes","investor visa","residence by investment")): score+=2
    if len(str(item.get("text","")))>2500: score+=1
    return score
def market_for(text,bucket_name="",url="",title=""):
    combined=f"{title} {text}".lower()
    for market,terms in MARKETS.items():
        if any(term.lower() in combined for term in terms): return market
    return "unknown"
def route_for(market): return ROUTES.get(market,"Partner Network")
def dedupe_key(item):
    basis=item.get("url") or f"{item.get('source')}|{item.get('title')}|{item.get('author')}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()
def exa_search(query,domains):
    api_key=os.getenv("EXA_API_KEY","").strip()
    if not api_key: print("EXA_DISABLED missing EXA_API_KEY"); return []
    payload={"query":query,"type":"auto","numResults":min(EXA_NUM_RESULTS,15),"includeDomains":domains,"contents":{"text":True}}
    response=SESSION.post(EXA_URL,json=payload,headers={"x-api-key":api_key,"Content-Type":"application/json"},timeout=35)
    if response.status_code!=200: print("EXA_ERROR",response.status_code,response.text[:350]); return []
    return [{"source":"Exa","url":x.get("url",""),"title":x.get("title",""),"text":x.get("text",""),"published":x.get("publishedDate",""),"author":""} for x in response.json().get("results",[])]
def buyer_scores(item):
    text=text_of(item); explicit=sum(1 for p in INTENT_PHRASES if p.lower() in text); personal=bool(re.search(r"\b(i|we|my|our|ben|biz|хочу|ищу|мой|наш)\b",text,re.I)); money=bool(re.search(r"(?:€|£|\$|₺|₽)\s?\d[\d,.\s]*(?:k|m)?",text)); transaction=contains_any(text,["viewing","offer","deposit","mortgage","payment plan","lawyer","title deed","reservation","due diligence","ипотека","взнос"]); intent=min(100,45+explicit*10+(15 if money else 0)+(10 if transaction else 0)+(8 if personal else 0)); credibility=min(100,55+discussion_likelihood(item)*4+(10 if money else 0)); fit=70 if item.get("market")!="unknown" else 55
    label="HOT" if intent>=80 and credibility>=75 and fit>=70 and personal and (money or transaction) else "WARM" if intent>=62 and credibility>=65 and personal else "REVIEW"
    return intent,credibility,fit,label
def keep_candidate(item,cutoff):
    text=text_of(item)
    if not item.get("url") or not source_is_user_generated(item.get("url","")): return False,"non_user_source"
    published=verified_published(item)
    if published is None: return False,"date_unverified"
    if published<cutoff: return False,"older_than_24h"
    if editorial_likelihood(item)>=3: return False,"editorial_or_article"
    if contains_any(text,NEGATIVE_PHRASES) or contains_any(text,["for rent","kiralık","сдам","сдается"]): return False,"negative_or_rental"
    if not contains_any(text,INTENT_PHRASES): return False,"no_buyer_intent"
    return True,"candidate"
def suggested_reply(market): return "Your requirements are specific enough to compare the area, total purchase costs and long-term use before making a decision."
def firestore_client():
    raw=os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON","").strip()
    if not raw: return None
    info=json.loads(raw); creds=service_account.Credentials.from_service_account_info(info)
    return firestore.Client(credentials=creds,project=info.get("project_id"))
def notify_telegram(message):
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip(); chat_id=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat_id: print("TELEGRAM_DISABLED missing token/chat id"); return
    try:
        response=SESSION.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":chat_id,"text":message[:3900]},timeout=15)
        if response.status_code!=200: print("TELEGRAM_ERROR",response.status_code,response.text[:300])
        else: print("TELEGRAM_SENT")
    except Exception as exc: print("TELEGRAM_NOTIFY_ERROR",exc)
def run():
    started=now_utc(); cutoff=started-timedelta(hours=LOOKBACK_HOURS); seen=set(); leads=[]; stats={"non_user_source":0,"date_unverified":0,"older_than_24h":0,"editorial_or_article":0,"not_enough_user_discussion_signal":0,"negative_or_rental":0,"seller_agent":0,"no_buyer_intent":0}; exa_calls=0
    for bucket in SOURCE_BUCKETS[:EXA_MAX_CALLS]:
        exa_calls+=1; print(f"EXA [{exa_calls}/{min(EXA_MAX_CALLS,len(SOURCE_BUCKETS))}] {bucket['name']}")
        try: results=exa_search(bucket["query"],bucket["domains"])
        except Exception as exc: print("EXA_EXCEPTION",exc); continue
        for item in results:
            item["source_bucket"]=bucket["name"]; key=dedupe_key(item)
            if key in seen: continue
            seen.add(key); published=verified_published(item); item["verified_published"]=published.isoformat() if published else ""; item["published_source"]="exa" if parse_dt(item.get("published")) else ("page_text" if published else "")
            keep,reason=keep_candidate(item,cutoff)
            if not keep:
                if reason in stats: stats[reason]+=1
                continue
            market=market_for(text_of(item),bucket["name"],item.get("url",""),item.get("title","")); item["market"]=market; intent,credibility,fit,label=buyer_scores(item)
            if label not in ("HOT","WARM"): continue
            item.update({"intent_score":intent,"credibility_score":credibility,"market_fit_score":fit,"classification":label,"route_to":route_for(market),"why":"Fresh public user discussion with personal purchase intent and concrete property, budget, timing, location or transaction evidence.","suggested_reply":suggested_reply(market),"scanned_at":started.isoformat(),"source_domain":domain_of(item.get("url",""))}); leads.append(item)
    leads=list({dedupe_key(x):x for x in leads}.values()); leads.sort(key=lambda x:(x["classification"]=="HOT",x["intent_score"],x["credibility_score"],x["market_fit_score"]),reverse=True)
    db=firestore_client(); scan_id=started.strftime("%Y%m%d%H%M%S")
    if db:
        scan_ref=db.collection(SCAN_LOG_COLLECTION).document(scan_id); batch=db.batch()
        for lead in leads[:100]: batch.set(scan_ref.collection("leads").document(hashlib.sha1((lead.get("url") or lead.get("title","")).encode("utf-8")).hexdigest()),lead,merge=True)
        batch.set(scan_ref,{"started_at":started.isoformat(),"finished_at":now_utc().isoformat(),"exa_calls":exa_calls,"source_baskets":min(EXA_MAX_CALLS,len(SOURCE_BUCKETS)),"unique_candidates":len(seen),"hot_warm":len(leads),"lookback_hours":LOOKBACK_HOURS,"filter_stats":stats},merge=True); batch.commit()
    print(f"SCAN_COMPLETE exa_calls={exa_calls} candidates={len(seen)} hot_warm={len(leads)}"); print("FILTER_STATS",json.dumps(stats,ensure_ascii=False))
    if leads:
        lines=[f"BAY-S WORLD RADAR | {len(leads)} HOT/WARM | Aday: {len(seen)} | Exa: {exa_calls}"]
        for lead in leads[:10]: lines.append(f"{lead['classification']} | {lead['market']} | I{lead['intent_score']} C{lead['credibility_score']} F{lead['market_fit_score']} | {lead.get('title','')[:120]} | {lead.get('url','')}")
        notify_telegram("\n".join(lines))
    else:
        notify_telegram(f"BAY-S WORLD RADAR tamamlandı.\nYeni HOT/WARM lead yok.\nİncelenen aday: {len(seen)}\nExa çağrısı: {exa_calls}\nTarama: son {LOOKBACK_HOURS} saat")
if __name__=="__main__": run()
