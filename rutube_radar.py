import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests

import main
import north_cyprus_catcher as catcher
import north_cyprus_focus as nf
import north_cyprus_spam_guard  # keep latest service/recruitment guards

RUTUBE = "https://rutube.ru"
WATCHLIST = "bay_s_rutube_watchlist"
NOTIFIED = "bay_s_rutube_notified_leads"
SCANS = "bay_s_rutube_scans"

nf.ALLOWED_USER_DOMAINS.add("rutube.ru")

QUERIES = [
    "Северный Кипр недвижимость", "Северный Кипр квартира", "Северный Кипр купить квартиру",
    "Северный Кипр вторичка", "Северный Кипр рассрочка", "Северный Кипр Long Beach",
    "Северный Кипр Искеле", "Северный Кипр Гирне", "Caesar Resort Северный Кипр",
    "Grand Sapphire Северный Кипр", "Isatis Северный Кипр", "Elysium Северный Кипр",
]

NC_VIDEO = [
    r"северн\w* кипр", r"north(?:ern)? cyprus", r"kuzey k[ıi]br[ıi]s", r"искеле", r"iskele",
    r"long beach", r"гирне", r"girne", r"kyrenia", r"esentepe", r"caesar", r"grand sapphire",
    r"isatis", r"elysium", r"fiora", r"royal sun", r"riverside",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
})


def _now():
    return datetime.now(timezone.utc)


def _get(url, params=None):
    try:
        r = SESSION.get(url, params=params or {}, timeout=25, allow_redirects=True)
        if r.status_code != 200:
            print("RUTUBE_HTTP_ERROR", r.status_code, r.url)
            return None
        return r.json()
    except Exception as exc:
        print("RUTUBE_HTTP_EXCEPTION", url, exc)
        return None


def _list(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("results", "items", "data", "comments"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _list(value)
            if nested:
                return nested
    return []


def _value(row, keys, default=""):
    if not isinstance(row, dict):
        return default
    for key in keys:
        value = row.get(key)
        if value not in (None, "", []):
            if isinstance(value, dict):
                for sub in ("name", "title", "username", "id", "value"):
                    if value.get(sub) not in (None, ""):
                        return value.get(sub)
            return value
    return default


def _video_id(row):
    value = str(_value(row, ("id", "video_id", "videoId", "hash", "video_hash"), "")).strip()
    if value:
        return value
    url = str(_value(row, ("url", "video_url", "html_url"), ""))
    m = re.search(r"/video/([0-9a-zA-Z_-]+)", url)
    return m.group(1) if m else ""


def _nc(text):
    return any(re.search(p, text or "", re.I) for p in NC_VIDEO)


def _rotate(limit):
    limit=max(1,min(limit,len(QUERIES)))
    now=_now(); slot=now.timetuple().tm_yday*4 + now.hour//6
    start=(slot*limit)%len(QUERIES)
    return [QUERIES[(start+i)%len(QUERIES)] for i in range(limit)]


def discover():
    db=main.firestore_client()
    if not db:
        return 0
    limit=int(os.getenv("RUTUBE_QUERY_LIMIT","4"))
    saved=0
    for query in _rotate(limit):
        data=_get(f"{RUTUBE}/api/search/video/", {"query":query,"page":1,"limit":20})
        rows=_list(data)
        kept=0
        for row in rows:
            vid=_video_id(row)
            title=str(_value(row,("title","name"),""))
            description=str(_value(row,("description","description_html","text"),""))
            author=str(_value(row,("author","user","channel"),""))
            if not vid or not _nc(f"{title} {description} {query}"):
                continue
            db.collection(WATCHLIST).document(vid).set({
                "video_id":vid,"title":title,"description":description[:1200],"author":author,
                "url":f"https://rutube.ru/video/{vid}/","market":"north_cyprus","status":"active",
                "query":query,"last_seen":_now().isoformat(),
            }, merge=True)
            saved+=1; kept+=1
        print(f"RUTUBE_DISCOVERY query={query!r} rows={len(rows)} kept={kept}")
    print(f"RUTUBE_DISCOVERY_COMPLETE saved={saved}")
    return saved


def _watchlist():
    db=main.firestore_client()
    if not db:
        return []
    limit=int(os.getenv("RUTUBE_WATCHLIST_LIMIT","100"))
    out=[]
    try:
        for doc in db.collection(WATCHLIST).limit(limit*2).stream():
            x=doc.to_dict() or {}
            if x.get("status")=="active" and x.get("video_id"):
                out.append(x)
            if len(out)>=limit:
                break
    except Exception as exc:
        print("RUTUBE_WATCHLIST_ERROR", exc)
    return out


def _comments(video_id):
    endpoints=[
        (f"{RUTUBE}/api/v2/comments/", {"video_id":video_id,"page":1}),
        (f"{RUTUBE}/api/v2/comments/video/{video_id}/", {"page":1}),
    ]
    for url, params in endpoints:
        data=_get(url, params)
        rows=_list(data)
        if rows:
            return rows
    return []


def _parse_date(value):
    if not value:
        return None
    if isinstance(value,(int,float)):
        try:
            return datetime.fromtimestamp(value,timezone.utc)
        except Exception:
            return None
    return main.parse_dt(str(value))


def _comment_item(row, video):
    cid=str(_value(row,("id","comment_id","commentId"),"")).strip()
    text=str(_value(row,("text","comment","body","content"),"")).strip()
    published=_parse_date(_value(row,("created_at","created","published_at","date","timestamp"),""))
    author=str(_value(row,("author","user","profile","username"),""))
    if not cid or not text or not published:
        return None
    return {
        "source":"RuTube Comment","url":f"{video.get('url','')}#comment-{cid}",
        "title":f"RuTube | {video.get('title','')} | Северный Кипр",
        "text":text,"published":published.isoformat(),"author":author,
        "source_bucket":"rutube_comments_north_cyprus","video_id":video.get("video_id",""),"comment_id":cid,
    }


def _seen(db, lead):
    key=hashlib.sha1(str(lead.get("comment_id") or lead.get("url")).encode()).hexdigest()
    try:
        return db.collection(NOTIFIED).document(key).get().exists if db else False
    except Exception:
        return False


def _mark(db, lead):
    if not db:
        return
    key=hashlib.sha1(str(lead.get("comment_id") or lead.get("url")).encode()).hexdigest()
    db.collection(NOTIFIED).document(key).set({"notified_at":_now().isoformat(),"url":lead.get("url",""),"classification":lead.get("classification","")},merge=True)


def scan():
    db=main.firestore_client(); lookback=int(os.getenv("RUTUBE_LOOKBACK_HOURS","24")); cutoff=_now()-timedelta(hours=lookback)
    videos=_watchlist(); raw=0; leads=[]; errors=0
    for video in videos:
        try:
            for row in _comments(video.get("video_id","")):
                item=_comment_item(row,video)
                if not item:
                    continue
                dt=main.parse_dt(item["published"])
                if not dt or dt<cutoff:
                    continue
                raw+=1
                lead, reason=catcher._classify(item, cutoff)
                if lead and not _seen(db, lead):
                    leads.append(lead)
        except Exception as exc:
            errors+=1; print("RUTUBE_VIDEO_ERROR",video.get("video_id"),exc)
    unique={x.get("comment_id") or x.get("url"):x for x in leads}; leads=list(unique.values())
    rank={"HOT":3,"WARM":2,"POTENTIAL":1}; leads.sort(key=lambda x:(rank.get(x.get("classification"),0),x.get("intent_score",0)),reverse=True)
    if leads:
        lines=[f"🇷🇺 BAY-S RUTUBE RADAR | {len(leads)} YENİ ADAY"]
        for lead in leads[:10]:
            excerpt=" ".join(str(lead.get("text","")).split())[:230]
            lines.append(f"\n{lead.get('classification')} | {lead.get('author') or 'kullanıcı'} | I{lead.get('intent_score',0)}\n💬 {excerpt}\n{lead.get('url','')}")
            _mark(db,lead)
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(f"🇷🇺 BAY-S RUTUBE RADAR tamamlandı.\nYeni aday yok.\nİzlenen video: {len(videos)}\nSon {lookback} saatte yorum: {raw}")
    if db:
        db.collection(SCANS).document(_now().strftime("%Y%m%d%H%M%S")).set({"scanned_at":_now().isoformat(),"videos":len(videos),"recent_comments":raw,"new_leads":len(leads),"errors":errors})
    print("RUTUBE_SCAN_COMPLETE",json.dumps({"videos":len(videos),"comments":raw,"leads":len(leads),"errors":errors},ensure_ascii=False))


def run():
    mode=os.getenv("RUTUBE_MODE","scan").strip().lower()
    if mode in ("discover","discover_scan"):
        discover()
    if mode in ("scan","discover_scan"):
        scan()

if __name__=="__main__":
    run()
