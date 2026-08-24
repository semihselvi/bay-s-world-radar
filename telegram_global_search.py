import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest as SearchContactsRequest
from telethon.tl.types import Channel, Chat, User

import main
from telegram_message_context import reply_context

GLOBAL_QUERIES = [
    "North Cyprus property","North Cyprus apartment","Northern Cyprus property","Kuzey Kıbrıs daire","Kuzey Kıbrıs ev",
    "İskele daire","Long Beach İskele","Girne daire","Esentepe villa","Северный Кипр квартира","Северный Кипр недвижимость",
    "Caesar Resort","Grand Sapphire","Isatis","Elysium","Fiora","Isatis Orchard","Royal Sun","Riverside Life","K'Saba İskele",
]

PUBLIC_GROUP_DISCOVERY_QUERIES = ["North Cyprus","Northern Cyprus","Kuzey Kıbrıs","Северный Кипр","İskele","Long Beach Cyprus","Girne","Esentepe"]


def _chat_link(entity,message_id):
    username=getattr(entity,"username",None)
    if username: return f"https://t.me/{username}/{message_id}"
    entity_id=abs(int(getattr(entity,"id",0) or 0)); return f"https://t.me/c/{entity_id}/{message_id}" if entity_id else "https://t.me/"


def _sender_name(sender):
    if not sender: return ""
    username=getattr(sender,"username",None)
    if username: return f"@{username}"
    first=getattr(sender,"first_name","") or ""; last=getattr(sender,"last_name","") or ""
    return " ".join(x for x in (first,last) if x).strip()


def _discussion_group(chat):
    if isinstance(chat,User) or not isinstance(chat,(Channel,Chat)): return False
    if isinstance(chat,Channel) and getattr(chat,"broadcast",False) and not getattr(chat,"megagroup",False): return False
    return True


async def _message_item(msg,chat,source,source_bucket,query=""):
    if not msg or not getattr(msg,"message",None) or not _discussion_group(chat): return None
    sender=None
    try: sender=await msg.get_sender()
    except Exception: pass
    if not isinstance(sender,User) or getattr(sender,"bot",False): return None
    dt=getattr(msg,"date",None)
    if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    if not dt: return None
    text=str(msg.message).strip()
    if not text: return None
    title=getattr(chat,"title","") or "Telegram public group"
    parent_text=await reply_context(msg)
    source_username=str(getattr(chat,"username","") or "").strip().lstrip("@")
    telegram_user_id=str(int(getattr(sender,"id",0) or 0))
    telegram_chat_id=str(int(getattr(chat,"id",0) or 0))
    return {"source":source,"url":_chat_link(chat,msg.id),"title":f"{source} | {title}","text":text,"published":dt.astimezone(timezone.utc).isoformat(),"author":_sender_name(sender),"telegram_user_id":telegram_user_id,"telegram_chat_id":telegram_chat_id,"source_bucket":source_bucket,"telegram_chat":title,"source_username":source_username,"telegram_query":query,"reply_context":parent_text}


def _persist_discovered_groups(groups):
    if not groups:
        return
    db=main.firestore_client()
    if not db:
        return
    now=main.now_utc().isoformat(); saved=0
    try:
        for chat in groups:
            username=str(getattr(chat,"username","") or "").strip().lstrip("@")
            if not username:
                continue
            doc_id=hashlib.sha1(f"telegram_public|{username.lower()}".encode("utf-8")).hexdigest()
            db.collection("bay_s_dynamic_sources").document(doc_id).set({
                "type":"telegram_public","market":"north_cyprus","username":username,
                "title":str(getattr(chat,"title","") or username),"url":f"https://t.me/{username}",
                "status":"active","discovered_by":"telegram_contact_search","last_seen":now,
            },merge=True)
            saved+=1
        if saved:
            print(f"TELEGRAM_PUBLIC_DISCOVERY_SAVED count={saved}")
    except Exception as exc:
        print("TELEGRAM_PUBLIC_DISCOVERY_SAVE_ERROR",exc)


async def _collect_global():
    api_id=os.getenv("TELEGRAM_API_ID","").strip(); api_hash=os.getenv("TELEGRAM_API_HASH","").strip(); session=os.getenv("TELEGRAM_STRING_SESSION","").strip()
    if not api_id or not api_hash or not session:
        print("TELEGRAM_GLOBAL_DISABLED missing TELEGRAM_API_ID/API_HASH/STRING_SESSION"); return []
    lookback_hours=int(os.getenv("WORLD_LOOKBACK_HOURS","8")); query_limit=max(1,min(len(GLOBAL_QUERIES),int(os.getenv("WORLD_TELEGRAM_GLOBAL_QUERY_LIMIT","16"))))
    result_limit=max(5,min(60,int(os.getenv("WORLD_TELEGRAM_GLOBAL_RESULTS_PER_QUERY","30")))); cutoff=datetime.now(timezone.utc)-timedelta(hours=lookback_hours)
    discover_public=os.getenv("WORLD_TELEGRAM_DISCOVER_PUBLIC_GROUPS","0").strip()=="1"
    public_group_limit=max(5,min(60,int(os.getenv("WORLD_TELEGRAM_PUBLIC_GROUP_LIMIT","40")))); public_message_limit=max(20,min(150,int(os.getenv("WORLD_TELEGRAM_PUBLIC_GROUP_MESSAGES","70"))))
    client=TelegramClient(StringSession(session),int(api_id),api_hash); await client.connect()
    if not await client.is_user_authorized(): await client.disconnect(); return []
    items={}; query_counts={}; discovered_groups={}
    try:
        for idx,query in enumerate(GLOBAL_QUERIES[:query_limit],1):
            kept=0; seen_for_query=0
            try:
                async for msg in client.iter_messages(None,search=query,limit=result_limit):
                    if not msg or not getattr(msg,"message",None): continue
                    seen_for_query+=1; dt=getattr(msg,"date",None)
                    if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    if not dt or dt<cutoff: continue
                    chat=None
                    try: chat=await msg.get_chat()
                    except Exception: pass
                    item=await _message_item(msg,chat,"Telegram Global Search","telegram_global_search",query)
                    if not item: continue
                    items[item["url"]]=item; kept+=1
            except FloodWaitError as exc:
                print(f"TELEGRAM_GLOBAL_FLOOD_WAIT query={query!r} seconds={exc.seconds}"); break
            except Exception as exc: print(f"TELEGRAM_GLOBAL_QUERY_ERROR query={query!r} {exc}")
            query_counts[query]=kept; print(f"TELEGRAM_GLOBAL_QUERY [{idx}/{query_limit}] query={query!r} seen={seen_for_query} kept={kept}")

        if discover_public:
            for query in PUBLIC_GROUP_DISCOVERY_QUERIES:
                try:
                    result=await client(SearchContactsRequest(q=query,limit=30))
                    for chat in getattr(result,"chats",[]) or []:
                        if not isinstance(chat,Channel) or not getattr(chat,"megagroup",False): continue
                        username=str(getattr(chat,"username","") or "").strip()
                        if not username: continue
                        discovered_groups[str(chat.id)]=chat
                        if len(discovered_groups)>=public_group_limit: break
                    if len(discovered_groups)>=public_group_limit: break
                except FloodWaitError as exc:
                    print(f"TELEGRAM_PUBLIC_DISCOVERY_FLOOD_WAIT query={query!r} seconds={exc.seconds}"); break
                except Exception as exc: print(f"TELEGRAM_PUBLIC_DISCOVERY_ERROR query={query!r} {exc}")
            for idx,chat in enumerate(discovered_groups.values(),1):
                recent=0
                try:
                    async for msg in client.iter_messages(chat,limit=public_message_limit):
                        dt=getattr(msg,"date",None)
                        if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                        if dt and dt<cutoff: break
                        item=await _message_item(msg,chat,"Telegram Public Discovery","telegram_public_discovery","public_group_discovery")
                        if not item: continue
                        items[item["url"]]=item; recent+=1
                    print(f"TELEGRAM_PUBLIC_GROUP_SCAN [{idx}/{len(discovered_groups)}] chat={getattr(chat,'title','')!r} recent_human_messages={recent}")
                except FloodWaitError as exc:
                    print(f"TELEGRAM_PUBLIC_GROUP_FLOOD_WAIT chat={getattr(chat,'title','')!r} seconds={exc.seconds}"); break
                except Exception as exc: print(f"TELEGRAM_PUBLIC_GROUP_SCAN_ERROR chat={getattr(chat,'title','')!r} {exc}")
    finally: await client.disconnect()

    _persist_discovered_groups(list(discovered_groups.values()))
    out=list(items.values()); out.sort(key=lambda x:x.get("published",""),reverse=True)
    print(f"TELEGRAM_GLOBAL_COUNTS queries={len(query_counts)} discovered_public_groups={len(discovered_groups)} unique_messages={len(out)}")
    return out


def collect_global_telegram():
    try: return asyncio.run(_collect_global())
    except RuntimeError:
        loop=asyncio.new_event_loop()
        try: return loop.run_until_complete(_collect_global())
        finally: loop.close()
    except Exception as exc:
        print("TELEGRAM_GLOBAL_EXCEPTION",exc); return []
