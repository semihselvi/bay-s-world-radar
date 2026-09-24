import asyncio
import hashlib
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel, Chat, User

import main
from telegram_member_deep_search import NC_TITLE_HINTS

COLLECTION="bay_s_dynamic_sources"
PUBLIC_RE=re.compile(r"https?://t\.me/(?!\+|joinchat/)([A-Za-z0-9_]{5,})",re.I)
INVITE_RE=re.compile(r"https?://t\.me/(\+[A-Za-z0-9_-]{8,}|joinchat/[A-Za-z0-9_-]{8,})",re.I)

# Verified private/invite-only communities are never auto-joined. They are seeded
# into the same JOIN LIST mechanism so the user can decide whether to join them.
STATIC_JOIN_CANDIDATES = {
    "https://t.me/+Rxo-Uo74TL5kZGFi",  # buyer/owner focused North Cyprus property discussion
    "https://t.me/+1s8HYWeJIN81NDdk", # Turkey + North Cyprus property community
    "https://t.me/+WZluIebsLjwxYTFk",
    "https://t.me/+9zAKnC6fojdlMDBk", # Iranians North Cyprus community
    "https://t.me/+S9eHfRwbsJgVK84l", # active Persian-speaking NC experience/investment community
    "https://t.me/+Z_JMGTu9Zs44ODY6", # North Cyprus general community
}


def _nc_title(title):
    low=(title or "").lower()
    return any(x in low for x in NC_TITLE_HINTS)


def _doc_id(kind,value):
    return hashlib.sha1(f"{kind}|{value.lower()}".encode()).hexdigest()


def _extract(text):
    text=str(text or "")
    return set(PUBLIC_RE.findall(text)), {f"https://t.me/{x}" for x in INVITE_RE.findall(text)}


def _dynamic_frontier(limit=80):
    db=main.firestore_client()
    if not db:
        return []
    rows=[]
    try:
        for doc in db.collection(COLLECTION).limit(1000).stream():
            data=doc.to_dict() or {}
            if data.get("market")!="north_cyprus" or data.get("type")!="telegram_public":
                continue
            if data.get("status")!="active":
                continue
            username=str(data.get("username") or "").strip().lstrip("@")
            if not username:
                continue
            score=float(data.get("discovery_score",0) or 0)+float(data.get("priority_score",0) or 0)
            rows.append((score,username))
    except Exception as exc:
        print("TELEGRAM_NETWORK_FRONTIER_LOAD_ERROR",exc)
        return []
    rows.sort(reverse=True)
    out=[]; seen=set()
    for score,username in rows:
        key=username.lower()
        if key in seen:
            continue
        seen.add(key); out.append(username)
        if len(out)>=limit:
            break
    return out


async def _collect_candidates():
    api_id=os.getenv("TELEGRAM_API_ID","").strip(); api_hash=os.getenv("TELEGRAM_API_HASH","").strip(); session=os.getenv("TELEGRAM_STRING_SESSION","").strip()
    if not api_id or not api_hash or not session: return set(),set(STATIC_JOIN_CANDIDATES)
    max_dialogs=int(os.getenv("WORLD_TELEGRAM_NETWORK_DIALOGS","40")); max_messages=int(os.getenv("WORLD_TELEGRAM_NETWORK_MESSAGES","80"))
    frontier_limit=int(os.getenv("WORLD_TELEGRAM_NETWORK_FRONTIER","80"))
    cutoff=datetime.now(timezone.utc)-timedelta(days=int(os.getenv("WORLD_TELEGRAM_NETWORK_DAYS","14")))
    client=TelegramClient(StringSession(session),int(api_id),api_hash); await client.connect()
    if not await client.is_user_authorized(): await client.disconnect(); return set(),set(STATIC_JOIN_CANDIDATES)
    public=set(); invites=set(STATIC_JOIN_CANDIDATES); dialogs=[]
    public_mentions=Counter(); public_sources=defaultdict(set)
    try:
        async for dialog in client.iter_dialogs(limit=220):
            entity=dialog.entity
            if isinstance(entity,User) or not isinstance(entity,(Channel,Chat)): continue
            title=getattr(entity,"title","") or dialog.name or ""
            if not _nc_title(title): continue
            dialogs.append((entity,title))
            if len(dialogs)>=max_dialogs: break
        joined_ids={int(getattr(entity,"id",0) or 0) for entity,title in dialogs}
        frontier_added=0
        for username in _dynamic_frontier(frontier_limit):
            try:
                entity=await client.get_entity(username)
                entity_id=int(getattr(entity,"id",0) or 0)
                if entity_id in joined_ids or isinstance(entity,User) or not isinstance(entity,(Channel,Chat)):
                    continue
                title=getattr(entity,"title","") or username
                dialogs.append((entity,title))
                joined_ids.add(entity_id)
                frontier_added+=1
            except FloodWaitError as exc:
                print(f"TELEGRAM_NETWORK_FRONTIER_FLOOD_WAIT seconds={exc.seconds}")
                break
            except Exception:
                pass
        print(f"TELEGRAM_NETWORK_FRONTIER added={frontier_added} total_scan_sources={len(dialogs)}")

        for entity,title in dialogs:
            try:
                about=""
                if isinstance(entity,Channel):
                    try:
                        full=await client(GetFullChannelRequest(entity))
                        about=str(getattr(getattr(full,"full_chat",None),"about","") or "")
                        linked_id=getattr(getattr(full,"full_chat",None),"linked_chat_id",None)
                        if linked_id:
                            for linked in getattr(full,"chats",[]) or []:
                                if int(getattr(linked,"id",0) or 0)!=int(linked_id):
                                    continue
                                linked_username=str(getattr(linked,"username","") or "").strip()
                                if linked_username:
                                    public.add(linked_username)
                                    public_mentions[linked_username]+=2
                                    public_sources[linked_username].add(title+" [linked discussion]")
                    except Exception:
                        pass
                p,i=_extract(about); public|=p; invites|=i
                for username in p:
                    public_mentions[username]+=1
                    public_sources[username].add(title)
                async for msg in client.iter_messages(entity,limit=max_messages):
                    dt=getattr(msg,"date",None)
                    if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    if dt and dt<cutoff: break
                    p,i=_extract(getattr(msg,"message","") or ""); public|=p; invites|=i
                    for username in p:
                        public_mentions[username]+=1
                        public_sources[username].add(title)

                    fwd=getattr(msg,"forward",None)
                    from_id=getattr(fwd,"from_id",None) if fwd else None
                    if from_id is not None:
                        try:
                            origin=await client.get_entity(from_id)
                            origin_username=str(getattr(origin,"username","") or "").strip()
                            if origin_username:
                                public.add(origin_username)
                                public_mentions[origin_username]+=2
                                public_sources[origin_username].add(title+" [forward]")
                        except Exception:
                            pass
            except FloodWaitError as exc:
                print(f"TELEGRAM_NETWORK_FLOOD_WAIT chat={title!r} seconds={exc.seconds}"); break
            except Exception as exc: print(f"TELEGRAM_NETWORK_CHAT_ERROR chat={title!r} {exc}")

        verified=[]
        ranked_public=sorted(
            public,
            key=lambda u:(len(public_sources.get(u,set())),public_mentions.get(u,0),u.lower()),
            reverse=True,
        )
        for username in ranked_public[:300]:
            try:
                entity=await client.get_entity(username)
                if isinstance(entity,Channel) and getattr(entity,"megagroup",False) and getattr(entity,"username",None):
                    verified.append((
                        str(entity.username),
                        str(getattr(entity,"title","") or username),
                        int(public_mentions.get(username,0)),
                        len(public_sources.get(username,set())),
                        sorted(public_sources.get(username,set()))[:20],
                    ))
            except FloodWaitError as exc:
                print(f"TELEGRAM_NETWORK_VERIFY_FLOOD_WAIT seconds={exc.seconds}"); break
            except Exception: pass
        return verified,invites
    finally: await client.disconnect()


def crawl_network():
    enabled=os.getenv("WORLD_TELEGRAM_NETWORK_CRAWL","0").strip()=="1" or os.getenv("GITHUB_EVENT_NAME","").strip()=="push"
    if not enabled: return {"public_new":0,"private_new":0}
    try: verified,invites=asyncio.run(_collect_candidates())
    except Exception as exc:
        print("TELEGRAM_NETWORK_EXCEPTION",exc); return {"public_new":0,"private_new":0}
    db=main.firestore_client()
    if not db: return {"public_new":0,"private_new":0}
    now=main.now_utc().isoformat(); public_new=[]; private_new=[]
    for username,title,mention_count,mention_source_count,mention_sources in verified:
        ref=db.collection(COLLECTION).document(_doc_id("telegram_public",username)); existed=ref.get().exists
        discovery_score=min(100, mention_source_count*12 + min(40,mention_count*3))
        ref.set({
            "type":"telegram_public","market":"north_cyprus","username":username,"title":title,
            "url":f"https://t.me/{username}","status":"active","discovered_by":"telegram_network_crawler",
            "mention_count":mention_count,"mention_source_count":mention_source_count,
            "mention_sources":mention_sources,"discovery_score":discovery_score,"last_seen":now
        },merge=True)
        if not existed: public_new.append(f"@{username}")
    for invite in sorted(invites):
        ref=db.collection(COLLECTION).document(_doc_id("telegram_private_invite",invite)); existed=ref.get().exists
        ref.set({"type":"telegram_private_invite","market":"north_cyprus","url":invite,"status":"join_candidate","discovered_by":"telegram_network_crawler","last_seen":now},merge=True)
        if not existed: private_new.append(invite)
    top=sorted(verified,key=lambda x:(x[3],x[2]),reverse=True)[:10]
    print(f"TELEGRAM_NETWORK_COMPLETE public_verified={len(verified)} public_new={len(public_new)} private_new={len(private_new)}")
    if top:
        print("TELEGRAM_NETWORK_TOP "+", ".join(f"@{u}:sources={sc}:mentions={mc}" for u,t,mc,sc,src in top))
    if private_new:
        main.notify_telegram("🔗 BAY-S NC JOIN LIST\nYeni private Telegram grup adayları bulundu. Otomatik katılım YOK.\n"+"\n".join(private_new[:8]))
    return {"public_new":len(public_new),"private_new":len(private_new)}

if __name__=="__main__": crawl_network()
