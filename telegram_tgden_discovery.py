import hashlib
import os
import re
from datetime import timezone

import requests

import main

COLLECTION = "bay_s_dynamic_sources"
BASE = "https://tgden.com/api/catalog"

QUERIES = [
    "North Cyprus", "Northern Cyprus", "Kuzey Kıbrıs", "KKTC",
    "İskele", "Long Beach Cyprus", "Girne", "Kyrenia", "Esentepe",
    "Gazimağusa", "Famagusta North Cyprus", "Bafra Cyprus",
    "Северный Кипр", "Искеле", "Гирне", "Фамагуста",
    "Nordzypern", "Cypr Północny", "Chypre du Nord",
    "قبرص الشمالية", "قبرس شمالی",
]

NC_RE = re.compile(
    r"(north(?:ern)?\s+cyprus|trnc|kktc|kuzey\s+k[ıi]br[ıi]s|северн\w*\s+кипр\w*|"
    r"iskele|i̇skele|long\s+beach|girne|kyrenia|esentepe|gazima[ğg]usa|famagust\w*|"
    r"bafra|lapta|alsancak|tatl[ıi]su|yenibo[ğg]azi[çc]i|caesar|sapphire|royal\s+sun|"
    r"riverside|isatis|elysium|nordzypern|cypr\s+p[oó]łnocny|chypre\s+du\s+nord|"
    r"قبرص\s+الشمالية|قبرس\s+شمالی)",
    re.I,
)
SOUTH_RE = re.compile(
    r"\b(limassol|lemesos|paphos|pafos|larnaca|ayia\s+napa|agia\s+napa|"
    r"protaras|paralimni|republic\s+of\s+cyprus|south\s+cyprus)\b",
    re.I,
)


def _doc_id(username):
    return hashlib.sha1(f"telegram_public|{username.lower()}".encode("utf-8")).hexdigest()


def _quality(item):
    username=str(item.get("username") or "").strip().lstrip("@")
    title=str(item.get("title") or "")
    blob=" ".join(str(item.get(k) or "") for k in ("title","username","description","category","language"))
    if not username or item.get("is_private") is True:
        return False, "missing_or_private"
    if SOUTH_RE.search(blob) and not NC_RE.search(blob):
        return False, "south_only"
    if not NC_RE.search(blob):
        return False, "no_north_cyprus_signal"
    return True, "north_cyprus_catalog_match"


def discover_tgden():
    if os.getenv("NC_TGDEN_ENABLED","1").strip() != "1":
        return {"queries":0,"seen":0,"saved":0}

    try:
        per_query=max(5,min(50,int(os.getenv("NC_TGDEN_RESULTS_PER_QUERY","25"))))
        query_limit=max(1,min(len(QUERIES),int(os.getenv("NC_TGDEN_QUERY_LIMIT","20"))))
    except ValueError:
        per_query=25; query_limit=20

    db=main.firestore_client()
    if not db:
        return {"queries":0,"seen":0,"saved":0}

    seen={}
    for query in QUERIES[:query_limit]:
        for kind in ("chat","channel"):
            try:
                r=requests.get(BASE,params={"q":query,"type":kind,"limit":per_query},timeout=15)
                if r.status_code != 200:
                    print(f"TGDEN_HTTP query={query!r} type={kind} status={r.status_code}")
                    continue
                payload=r.json() if r.content else {}
                for item in payload.get("items",[]) or []:
                    username=str(item.get("username") or "").strip().lstrip("@")
                    if not username:
                        continue
                    row=dict(item)
                    row["tgden_query"]=query
                    row["tgden_type"]=kind
                    seen[username.lower()]=row
            except Exception as exc:
                print(f"TGDEN_ERROR query={query!r} type={kind} {type(exc).__name__}: {exc}")

    saved=0; candidates=0; rejected=0; now=main.now_utc().isoformat()
    for item in seen.values():
        ok,reason=_quality(item)
        username=str(item.get("username") or "").strip().lstrip("@")
        if not username:
            rejected+=1
            continue
        title=str(item.get("title") or username)
        ref=db.collection(COLLECTION).document(_doc_id(username))
        status="active" if ok else "candidate"
        if status=="candidate":
            candidates+=1
        else:
            saved+=1
        ref.set({
            "type":"telegram_public",
            "market":"north_cyprus",
            "username":username,
            "title":title,
            "url":f"https://t.me/{username}",
            "status":status,
            "discovered_by":"tgden_catalog",
            "external_catalog":"tgden",
            "external_catalog_query":item.get("tgden_query"),
            "external_catalog_type":item.get("tgden_type"),
            "external_catalog_id":item.get("id"),
            "telegram_id":item.get("telegram_id"),
            "market_quality_reason":reason,
            "needs_validation": not ok,
            "last_seen":now,
        },merge=True)

    print(f"TGDEN_DISCOVERY_COMPLETE queries={query_limit} seen={len(seen)} active={saved} candidates={candidates} rejected={rejected}")
    return {"queries":query_limit,"seen":len(seen),"active":saved,"candidates":candidates,"rejected":rejected}


if __name__=="__main__":
    print(discover_tgden())
