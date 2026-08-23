import asyncio
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User

import main
from north_cyprus_source_performance import ranked_usernames
from telegram_message_context import reply_context

# Public discussion / marketplace groups verified from live Telegram pages and
# Cyprus community directories. Seller-heavy groups remain useful because the
# shared buyer classifier rejects listings/agents and keeps human wanted posts.
KNOWN_GROUPS = [
    "cyprusy","cyprusposter","severnyy_kipr","north_cypruschat","northcypruschat","nordcyprus",
    "base_north_cyprus","kibris_cyprus","caesar_resort_chat","kipr_severnii","cyprusforum",
    "cyprus_nedvizhimost","meetinnorthcyprus","searchgirne","iskelesearch","famagustasearchsnc","lefkosasearch",
    "NorthCyprus_Island","severnyi_kipr_russian","northcyprusok",
    # Newly verified high-value public communities / marketplaces.
    "kipr_chat","iskele_chat","kiriniya","famagusta_ru","kipr_nedvizhimost","kipr360realestate","adscyprus",
    "Investments_North_Cyprus",
    # Active Iranian community explicitly covering residence and property buying.
    "ResidentIraniansOfCyprus",
    # Broader Cyprus relocation/expat surfaces: only messages with explicit NC
    # context survive classification, so these are high-recall but low-risk.
    "forum_cyprus","kipr_relokaciya","cyprus_expats",
]


def _dynamic_groups(limit=100):
    """Load public groups found by Source Scout / Telegram Network Crawler.

    This closes the discovery loop: a newly found group is not just stored in
    Firestore; it becomes a live Catcher source on the very next run.
    """
    db = main.firestore_client()
    if not db:
        return []
    out=[]; seen=set()
    try:
        for doc in db.collection("bay_s_dynamic_sources").limit(250).stream():
            data=doc.to_dict() or {}
            if data.get("market") != "north_cyprus" or data.get("type") != "telegram_public" or data.get("status") != "active":
                continue
            username=str(data.get("username") or "").strip().lstrip("@")
            if not username or username.lower() in seen:
                continue
            seen.add(username.lower()); out.append(username)
            if len(out)>=limit: break
    except Exception as exc:
        print("TELEGRAM_DYNAMIC_GROUP_LOAD_ERROR",exc)
    print(f"TELEGRAM_DYNAMIC_GROUPS loaded={len(out)}")
    return out


def _link(chat, message_id):
    username=getattr(chat,"username",None)
    if username: return f"https://t.me/{username}/{message_id}"
    cid=abs(int(getattr(chat,"id",0) or 0)); return f"https://t.me/c/{cid}/{message_id}" if cid else "https://t.me/"


def _author(sender):
    if not isinstance(sender,User) or getattr(sender,"bot",False): return ""
    username=getattr(sender,"username",None)
    if username: return f"@{username}"
    return " ".join(x for x in ((getattr(sender,"first_name","") or ""),(getattr(sender,"last_name","") or "")) if x).strip()


async def _collect():
    api_id=os.getenv("TELEGRAM_API_ID","").strip(); api_hash=os.getenv("TELEGRAM_API_HASH","").strip(); session=os.getenv("TELEGRAM_STRING_SESSION","").strip()
    if not api_id or not api_hash or not session: return []
    lookback=int(os.getenv("WORLD_LOOKBACK_HOURS","8")); cutoff=datetime.now(timezone.utc)-timedelta(hours=lookback)
    universe=KNOWN_GROUPS+_dynamic_groups(int(os.getenv("WORLD_TELEGRAM_DYNAMIC_GROUP_LIMIT","100")))
    ordered_groups=ranked_usernames(universe)
    max_groups=max(1,min(len(ordered_groups),int(os.getenv("WORLD_TELEGRAM_KNOWN_GROUP_LIMIT","40"))))
    max_messages=max(30,min(180,int(os.getenv("WORLD_TELEGRAM_KNOWN_GROUP_MESSAGES","100"))))
    client=TelegramClient(StringSession(session),int(api_id),api_hash); await client.connect()
    if not await client.is_user_authorized(): await client.disconnect(); return []
    items={}; scanned=0
    try:
        for username in ordered_groups[:max_groups]:
            try:
                chat=await client.get_entity(username)
                if not isinstance(chat,(Channel,Chat)) or isinstance(chat,User): continue
                if isinstance(chat,Channel) and getattr(chat,"broadcast",False) and not getattr(chat,"megagroup",False): continue
                scanned+=1; count=0
                actual_username=str(getattr(chat,"username",None) or username).strip().lstrip("@")
                async for msg in client.iter_messages(chat,limit=max_messages):
                    if not msg or not getattr(msg,"message",None): continue
                    dt=getattr(msg,"date",None)
                    if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    if dt and dt<cutoff: break
                    if not dt: continue
                    sender=None
                    try: sender=await msg.get_sender()
                    except Exception: pass
                    author=_author(sender)
                    if not author: continue
                    text=str(msg.message).strip()
                    if not text: continue
                    url=_link(chat,msg.id); parent_text=await reply_context(msg)
                    items[url]={"source":"Telegram Known/Dynamic NC Group","url":url,"title":f"Telegram Group | {getattr(chat,'title','') or username} | North Cyprus","text":text,"published":dt.astimezone(timezone.utc).isoformat(),"author":author,"source_bucket":"telegram_known_nc_groups","telegram_chat":getattr(chat,"title","") or username,"source_username":actual_username,"reply_context":parent_text}
                    count+=1
                print(f"TELEGRAM_KNOWN_GROUP @{username} recent_human_messages={count}")
            except FloodWaitError as exc:
                print(f"TELEGRAM_KNOWN_GROUP_FLOOD_WAIT @{username} seconds={exc.seconds}"); break
            except Exception as exc:
                print(f"TELEGRAM_KNOWN_GROUP_ERROR @{username} {exc}")
    finally: await client.disconnect()
    print(f"TELEGRAM_KNOWN_GROUP_COUNTS universe={len(ordered_groups)} scanned={scanned} unique_messages={len(items)}")
    return list(items.values())


def collect_known_public_groups():
    try: return asyncio.run(_collect())
    except RuntimeError:
        loop=asyncio.new_event_loop()
        try: return loop.run_until_complete(_collect())
        finally: loop.close()
    except Exception as exc:
        print("TELEGRAM_KNOWN_GROUP_EXCEPTION",exc); return []
