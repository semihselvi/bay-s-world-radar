import asyncio
import hashlib
import os
import re
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


def _nc_title(title):
    low=(title or "").lower()
    return any(x in low for x in NC_TITLE_HINTS)


def _doc_id(kind,value):
    return hashlib.sha1(f"{kind}|{value.lower()}".encode()).hexdigest()


def _extract(text):
    text=str(text or "")
    return set(PUBLIC_RE.findall(text)), {f"https://t.me/{x}" for x in INVITE_RE.findall(text)}


async def _collect_candidates():
    api_id=os.getenv("TELEGRAM_API_ID","").strip(); api_hash=os.getenv("TELEGRAM_API_HASH","").strip(); session=os.getenv("TELEGRAM_STRING_SESSION","").strip()
    if not api_id or not api_hash or not session: return set(),set()
    max_dialogs=int(os.getenv("WORLD_TELEGRAM_NETWORK_DIALOGS","40")); max_messages=int(os.getenv("WORLD_TELEGRAM_NETWORK_MESSAGES","80"))
    cutoff=datetime.now(timezone.utc)-timedelta(days=int(os.getenv("WORLD_TELEGRAM_NETWORK_DAYS","14")))
    client=TelegramClient(StringSession(session),int(api_id),api_hash); await client.connect()
    if not await client.is_user_authorized(): await client.disconnect(); return set(),set()
    public=set(); invites=set(); dialogs=[]
    try:
        async for dialog in client.iter_dialogs(limit=220):
            entity=dialog.entity
            if isinstance(entity,User) or not isinstance(entity,(Channel,Chat)): continue
            title=getattr(entity,"title","") or dialog.name or ""
            if not _nc_title(title): continue
            dialogs.append((entity,title))
            if len(dialogs)>=max_dialogs: break
        for entity,title in dialogs:
            try:
                about=""
                if isinstance(entity,Channel):
                    try:
                        full=await client(GetFullChannelRequest(entity)); about=str(getattr(getattr(full,"full_chat",None),"about","") or "")
                    except Exception: pass
                p,i=_extract(about); public|=p; invites|=i
                async for msg in client.iter_messages(entity,limit=max_messages):
                    dt=getattr(msg,"date",None)
                    if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    if dt and dt<cutoff: break
                    p,i=_extract(getattr(msg,"message","") or ""); public|=p; invites|=i
            except FloodWaitError as exc:
                print(f"TELEGRAM_NETWORK_FLOOD_WAIT chat={title!r} seconds={exc.seconds}"); break
            except Exception as exc: print(f"TELEGRAM_NETWORK_CHAT_ERROR chat={title!r} {exc}")

        verified=set()
        for username in sorted(public)[:80]:
            try:
                entity=await client.get_entity(username)
                if isinstance(entity,Channel) and getattr(entity,"megagroup",False) and getattr(entity,"username",None):
                    verified.add((str(entity.username),str(getattr(entity,"title","") or username)))
            except FloodWaitError as exc:
                print(f"TELEGRAM_NETWORK_VERIFY_FLOOD_WAIT seconds={exc.seconds}"); break
            except Exception: pass
        return verified,invites
    finally: await client.disconnect()


def crawl_network():
    if os.getenv("WORLD_TELEGRAM_NETWORK_CRAWL","0").strip()!="1": return {"public_new":0,"private_new":0}
    try: verified,invites=asyncio.run(_collect_candidates())
    except Exception as exc:
        print("TELEGRAM_NETWORK_EXCEPTION",exc); return {"public_new":0,"private_new":0}
    db=main.firestore_client()
    if not db: return {"public_new":0,"private_new":0}
    now=main.now_utc().isoformat(); public_new=[]; private_new=[]
    for username,title in verified:
        ref=db.collection(COLLECTION).document(_doc_id("telegram_public",username)); existed=ref.get().exists
        ref.set({"type":"telegram_public","market":"north_cyprus","username":username,"title":title,"url":f"https://t.me/{username}","status":"active","discovered_by":"telegram_network_crawler","last_seen":now},merge=True)
        if not existed: public_new.append(f"@{username}")
    for invite in sorted(invites):
        ref=db.collection(COLLECTION).document(_doc_id("telegram_private_invite",invite)); existed=ref.get().exists
        ref.set({"type":"telegram_private_invite","market":"north_cyprus","url":invite,"status":"join_candidate","discovered_by":"telegram_network_crawler","last_seen":now},merge=True)
        if not existed: private_new.append(invite)
    print(f"TELEGRAM_NETWORK_COMPLETE public_verified={len(verified)} public_new={len(public_new)} private_new={len(private_new)}")
    if private_new:
        main.notify_telegram("🔗 BAY-S NC JOIN LIST\nYeni private Telegram grup adayları bulundu. Otomatik katılım YOK.\n"+"\n".join(private_new[:8]))
    return {"public_new":len(public_new),"private_new":len(private_new)}

if __name__=="__main__": crawl_network()
