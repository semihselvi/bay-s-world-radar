import asyncio
import hashlib
import os
import re

from telethon import functions
from telethon.tl.types import Channel, Chat, User

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


def _doc_id(username):
    return hashlib.sha1(f"telegram_public|{username.lower()}".encode("utf-8")).hexdigest()


def _is_nc(entity):
    blob=" ".join([
        str(getattr(entity,"title","") or ""),
        str(getattr(entity,"username","") or ""),
    ])
    return bool(NC_RE.search(blob))


async def _discover():
    api_id=os.getenv("TELEGRAM_API_ID","").strip()
    api_hash=os.getenv("TELEGRAM_API_HASH","").strip()
    if not api_id or not api_hash:
        return []

    request_cls=getattr(functions.channels,"GetChannelRecommendationsRequest",None)
    if request_cls is None:
        print("TELEGRAM_RECOMMENDATIONS_UNSUPPORTED telethon_missing_method")
        return []

    slots=await tsp.open_pool(int(api_id),api_hash)
    if not slots:
        return []

    slot=slots[0]; client=slot.client
    found={}
    try:
        seeds=[]
        async for dialog in client.iter_dialogs(limit=260):
            entity=dialog.entity
            if isinstance(entity,Channel) and _is_nc(entity):
                seeds.append(entity)
                if len(seeds)>=20:
                    break

        for seed in seeds:
            try:
                input_channel=await client.get_input_entity(seed)
                res=await client(request_cls(channel=input_channel))
                for entity in getattr(res,"chats",[]) or []:
                    if not isinstance(entity,Channel):
                        continue
                    username=str(getattr(entity,"username","") or "").strip().lstrip("@")
                    if not username:
                        continue
                    row=found.setdefault(username.lower(),{
                        "username":username,
                        "title":str(getattr(entity,"title","") or username),
                        "recommended_from":set(),
                    })
                    row["recommended_from"].add(str(getattr(seed,"username","") or getattr(seed,"title","") or "seed"))
            except Exception as exc:
                print(f"TELEGRAM_RECOMMENDATION_SEED_ERROR seed={getattr(seed,'title','')!r} {type(exc).__name__}: {exc}")

        print(f"TELEGRAM_RECOMMENDATIONS_DISCOVERED seeds={len(seeds)} unique={len(found)}")
        return list(found.values())
    finally:
        await tsp.close_pool(slots)


def discover_recommendations():
    if os.getenv("NC_TELEGRAM_RECOMMENDATIONS","1").strip()!="1":
        return {"seen":0,"saved":0}

    try:
        rows=asyncio.run(_discover())
    except Exception as exc:
        print("TELEGRAM_RECOMMENDATIONS_EXCEPTION",repr(exc))
        return {"seen":0,"saved":0}

    db=main.firestore_client()
    if not db:
        return {"seen":len(rows),"saved":0}

    saved=0; now=main.now_utc().isoformat()
    for row in rows:
        username=row["username"]
        title=row["title"]
        refs=sorted(row["recommended_from"])[:20]
        # Keep recommendation graph candidates, but give strong NC-title matches a
        # higher initial discovery score. Existing network quality checks still
        # decide whether they become productive scan sources.
        nc_title=bool(NC_RE.search(f"{title} {username}"))
        score=min(100,20+len(refs)*12+(30 if nc_title else 0))
        db.collection(COLLECTION).document(_doc_id(username)).set({
            "type":"telegram_public",
            "market":"north_cyprus",
            "username":username,
            "title":title,
            "url":f"https://t.me/{username}",
            "status":"active",
            "discovered_by":"telegram_channel_recommendations",
            "recommended_from":refs,
            "recommendation_source_count":len(refs),
            "discovery_score":score,
            "last_seen":now,
        },merge=True)
        saved+=1

    print(f"TELEGRAM_RECOMMENDATIONS_COMPLETE seen={len(rows)} saved={saved}")
    return {"seen":len(rows),"saved":saved}


if __name__=="__main__":
    print(discover_recommendations())
