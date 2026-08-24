import asyncio
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import Channel, User

from telegram_message_context import reply_context

NC_PARENT_CHANNELS = [
    "velesproperty", "btinvestnorthcyprus", "simoncyprus", "leverageinvestmentsofficial",
    "flatty_cyprus", "cyprusposter", "nedvizhimost_kipr",
    "kibrishome", "vitriolkipr", "North_Cyprus", "northcyprus_real_estate",
    "kipr_nedvizhimost", "kipr360realestate",
]


def _sender_name(sender):
    if not sender: return ""
    username = getattr(sender, "username", None)
    if username: return f"@{username}"
    first = getattr(sender, "first_name", "") or ""; last = getattr(sender, "last_name", "") or ""
    return " ".join(x for x in (first, last) if x).strip()


def _chat_link(entity, message_id):
    username = getattr(entity, "username", None)
    if username: return f"https://t.me/{username}/{message_id}"
    entity_id = abs(int(getattr(entity, "id", 0) or 0))
    return f"https://t.me/c/{entity_id}/{message_id}" if entity_id else "https://t.me/"


def _extra_channels():
    raw = os.getenv("WORLD_TELEGRAM_COMMENT_CHANNELS", "")
    return [x.strip().lstrip("@") for x in raw.split(",") if x.strip()]


async def _collect():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip(); api_hash = os.getenv("TELEGRAM_API_HASH", "").strip(); session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    if not api_id or not api_hash or not session:
        print("TELEGRAM_COMMENTS_DISABLED missing TELEGRAM_API_ID/API_HASH/STRING_SESSION"); return []
    lookback_hours = int(os.getenv("WORLD_LOOKBACK_HOURS", "8")); cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    channel_limit = max(1, min(30, int(os.getenv("WORLD_TELEGRAM_COMMENT_CHANNEL_LIMIT", "20"))))
    message_limit = max(20, min(180, int(os.getenv("WORLD_TELEGRAM_COMMENT_MESSAGES", "80"))))
    channels=[]
    for username in NC_PARENT_CHANNELS + _extra_channels():
        username=username.strip().lstrip("@")
        if username and username.lower() not in {x.lower() for x in channels}: channels.append(username)
    channels=channels[:channel_limit]
    client=TelegramClient(StringSession(session),int(api_id),api_hash); await client.connect()
    if not await client.is_user_authorized(): await client.disconnect(); return []
    items={}; linked_found=0
    try:
        for idx,username in enumerate(channels,1):
            try:
                parent=await client.get_entity(username)
                if not isinstance(parent,Channel): continue
                full=await client(GetFullChannelRequest(parent)); linked_id=getattr(getattr(full,"full_chat",None),"linked_chat_id",None)
                if not linked_id: continue
                discussion=None
                for chat in getattr(full,"chats",[]) or []:
                    if int(getattr(chat,"id",0) or 0)==int(linked_id): discussion=chat; break
                if discussion is None:
                    try: discussion=await client.get_entity(int(linked_id))
                    except Exception: pass
                if not isinstance(discussion,Channel) or not getattr(discussion,"megagroup",False): continue
                linked_found+=1; parent_title=getattr(parent,"title","") or username; discussion_title=getattr(discussion,"title","") or "discussion"; count=0
                telegram_chat_id=str(int(getattr(discussion,"id",0) or 0))
                async for msg in client.iter_messages(discussion,limit=message_limit):
                    if not msg or not getattr(msg,"message",None): continue
                    dt=getattr(msg,"date",None)
                    if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    if dt and dt<cutoff: break
                    if not dt: continue
                    sender=None
                    try: sender=await msg.get_sender()
                    except Exception: pass
                    if not isinstance(sender,User) or getattr(sender,"bot",False): continue
                    text=str(msg.message).strip()
                    if not text: continue
                    url=_chat_link(discussion,msg.id); parent_text=await reply_context(msg)
                    items[url]={"source":"Telegram Channel Comments","url":url,"title":f"Telegram Comments | {parent_title} / {discussion_title} | North Cyprus","text":text,"published":dt.astimezone(timezone.utc).isoformat(),"author":_sender_name(sender),"telegram_user_id":str(int(getattr(sender,"id",0) or 0)),"telegram_chat_id":telegram_chat_id,"source_bucket":"telegram_channel_comments_north_cyprus","telegram_chat":f"{discussion_title} | North Cyprus","telegram_parent_channel":f"@{username}","reply_context":parent_text}
                    count+=1
                print(f"TELEGRAM_COMMENT_CHANNEL [{idx}/{len(channels)}] @{username} linked={discussion_title!r} recent_human_messages={count}")
            except FloodWaitError as exc:
                print(f"TELEGRAM_COMMENT_FLOOD_WAIT @{username} seconds={exc.seconds}"); break
            except Exception as exc: print(f"TELEGRAM_COMMENT_CHANNEL_ERROR @{username} {exc}")
    finally: await client.disconnect()
    out=list(items.values()); out.sort(key=lambda x:x.get("published",""),reverse=True)
    print(f"TELEGRAM_COMMENT_COUNTS parents={len(channels)} linked={linked_found} unique_messages={len(out)}")
    return out


def collect_channel_comments():
    try: return asyncio.run(_collect())
    except RuntimeError:
        loop=asyncio.new_event_loop()
        try: return loop.run_until_complete(_collect())
        finally: loop.close()
    except Exception as exc:
        print("TELEGRAM_COMMENTS_EXCEPTION",exc); return []
