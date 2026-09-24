import asyncio
import hashlib
import os
import re

from telethon.errors import FloodWaitError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel

import main
import telegram_session_pool as tsp

COLLECTION="bay_s_dynamic_sources"

NC_RE=re.compile(
    r"(north(?:ern)?\s+cyprus|trnc|kktc|kuzey\s+k[ıi]br[ıi]s|северн\w*\s+кипр\w*|"
    r"iskele|i̇skele|long\s+beach|girne|kyrenia|esentepe|gazima[ğg]usa|famagust\w*|"
    r"bafra|lapta|alsancak|tatl[ıi]su|yenibo[ğg]azi[çc]i|caesar|sapphire|royal\s+sun|"
    r"riverside|isatis|elysium)",
    re.I,
)
SOUTH_RE=re.compile(
    r"\b(limassol|lemesos|paphos|pafos|larnaca|ayia\s+napa|agia\s+napa|"
    r"protaras|paralimni|republic\s+of\s+cyprus|south\s+cyprus)\b",
    re.I,
)


def _load_candidates(limit):
    db=main.firestore_client()
    if not db:
        return []
    rows=[]
    try:
        for doc in db.collection(COLLECTION).limit(1000).stream():
            data=doc.to_dict() or {}
            if data.get("market")!="north_cyprus" or data.get("type")!="telegram_public":
                continue
            if data.get("status")!="candidate":
                continue
            username=str(data.get("username") or "").strip().lstrip("@")
            if not username:
                continue
            rows.append((doc.id,username,data))
            if len(rows)>=limit:
                break
    except Exception as exc:
        print("TELEGRAM_CANDIDATE_LOAD_ERROR",exc)
    return rows


async def _validate():
    api_id=os.getenv("TELEGRAM_API_ID","").strip()
    api_hash=os.getenv("TELEGRAM_API_HASH","").strip()
    if not api_id or not api_hash:
        return []

    limit=max(1,min(80,int(os.getenv("NC_TELEGRAM_CANDIDATE_LIMIT","30"))))
    message_limit=max(10,min(80,int(os.getenv("NC_TELEGRAM_CANDIDATE_MESSAGES","30"))))
    candidates=_load_candidates(limit)
    if not candidates:
        return []

    slots=await tsp.open_pool(int(api_id),api_hash)
    if not slots:
        return []
    client=slots[0].client
    out=[]
    try:
        for doc_id,username,data in candidates:
            try:
                entity=await client.get_entity(username)
                if not isinstance(entity,Channel) or not getattr(entity,"username",None):
                    out.append((doc_id,"rejected","not_public_channel",0))
                    continue

                about=""
                try:
                    full=await client(GetFullChannelRequest(entity))
                    about=str(getattr(getattr(full,"full_chat",None),"about","") or "")
                except Exception:
                    pass

                header=f"{getattr(entity,'title','')} {getattr(entity,'username','')} {about}"
                if SOUTH_RE.search(header) and not NC_RE.search(header):
                    out.append((doc_id,"rejected","south_only",0))
                    continue

                nc_hits=0
                sampled=0
                async for msg in client.iter_messages(entity,limit=message_limit):
                    txt=str(getattr(msg,"message","") or "")
                    if not txt:
                        continue
                    sampled+=1
                    if NC_RE.search(txt):
                        nc_hits+=1

                if NC_RE.search(header) or nc_hits>=2:
                    out.append((doc_id,"active","validated_north_cyprus",nc_hits))
                else:
                    out.append((doc_id,"rejected","insufficient_north_cyprus_evidence",nc_hits))
            except FloodWaitError as exc:
                print(f"TELEGRAM_CANDIDATE_FLOOD_WAIT seconds={exc.seconds}")
                break
            except Exception as exc:
                print(f"TELEGRAM_CANDIDATE_ERROR @{username} {type(exc).__name__}: {exc}")
    finally:
        await tsp.close_pool(slots)
    return out


def validate_candidates():
    if os.getenv("NC_TELEGRAM_CANDIDATE_VALIDATE","1").strip()!="1":
        return {"checked":0,"activated":0,"rejected":0}
    try:
        rows=asyncio.run(_validate())
    except Exception as exc:
        print("TELEGRAM_CANDIDATE_EXCEPTION",repr(exc))
        return {"checked":0,"activated":0,"rejected":0}

    db=main.firestore_client()
    if not db:
        return {"checked":0,"activated":0,"rejected":0}

    activated=rejected=0
    now=main.now_utc().isoformat()
    for doc_id,status,reason,nc_hits in rows:
        db.collection(COLLECTION).document(doc_id).set({
            "status":status,
            "validation_reason":reason,
            "validation_nc_hits":nc_hits,
            "validated_at":now,
            "needs_validation":False,
        },merge=True)
        if status=="active":
            activated+=1
        else:
            rejected+=1

    print(f"TELEGRAM_CANDIDATE_COMPLETE checked={len(rows)} activated={activated} rejected={rejected}")
    return {"checked":len(rows),"activated":activated,"rejected":rejected}


if __name__=="__main__":
    print(validate_candidates())
