import asyncio
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User


# Public Telegram global-search queries. This is deliberately market-led rather
# than buyer-phrase-led: we search where North Cyprus conversations happen, then
# let the buyer-intent classifier decide whether the message is commercially useful.
GLOBAL_QUERIES = [
    "North Cyprus property",
    "North Cyprus apartment",
    "Northern Cyprus property",
    "Kuzey Kıbrıs daire",
    "Kuzey Kıbrıs ev",
    "İskele daire",
    "Long Beach İskele",
    "Girne daire",
    "Esentepe villa",
    "Северный Кипр квартира",
    "Северный Кипр недвижимость",
    "Caesar Resort",
    "Grand Sapphire",
    "Isatis",
    "Elysium",
    "Fiora",
    "Isatis Orchard",
    "Royal Sun",
    "Riverside Life",
    "K'Saba İskele",
]


def _chat_link(entity, message_id):
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    entity_id = abs(int(getattr(entity, "id", 0) or 0))
    return f"https://t.me/c/{entity_id}/{message_id}" if entity_id else "https://t.me/"


def _sender_name(sender):
    if not sender:
        return ""
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    first = getattr(sender, "first_name", "") or ""
    last = getattr(sender, "last_name", "") or ""
    return " ".join(x for x in (first, last) if x).strip()


async def _collect_global():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    if not api_id or not api_hash or not session:
        print("TELEGRAM_GLOBAL_DISABLED missing TELEGRAM_API_ID/API_HASH/STRING_SESSION")
        return []

    lookback_hours = int(os.getenv("WORLD_LOOKBACK_HOURS", "8"))
    query_limit = max(1, min(len(GLOBAL_QUERIES), int(os.getenv("WORLD_TELEGRAM_GLOBAL_QUERY_LIMIT", "16"))))
    result_limit = max(5, min(60, int(os.getenv("WORLD_TELEGRAM_GLOBAL_RESULTS_PER_QUERY", "30"))))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("TELEGRAM_GLOBAL_DISABLED session_not_authorized")
        await client.disconnect()
        return []

    items = {}
    query_counts = {}
    try:
        for idx, query in enumerate(GLOBAL_QUERIES[:query_limit], 1):
            kept = 0
            seen_for_query = 0
            try:
                # entity=None + search=... uses Telegram's global message search.
                # This expands coverage beyond only the groups/channels already joined.
                async for msg in client.iter_messages(None, search=query, limit=result_limit):
                    if not msg or not getattr(msg, "message", None):
                        continue
                    seen_for_query += 1

                    dt = getattr(msg, "date", None)
                    if dt and dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if not dt or dt < cutoff:
                        continue

                    chat = None
                    try:
                        chat = await msg.get_chat()
                    except Exception:
                        pass
                    if isinstance(chat, User) or not isinstance(chat, (Channel, Chat)):
                        continue

                    # Broadcast channels are overwhelmingly seller/brand posts. Genuine
                    # buyer questions are far more likely in groups/supergroups.
                    if isinstance(chat, Channel) and getattr(chat, "broadcast", False) and not getattr(chat, "megagroup", False):
                        continue

                    sender = None
                    try:
                        sender = await msg.get_sender()
                    except Exception:
                        pass
                    # Skip bots and anonymous/channel senders. The goal is a reachable
                    # human buyer, not another advertising feed.
                    if not isinstance(sender, User) or getattr(sender, "bot", False):
                        continue

                    text = str(msg.message).strip()
                    if not text:
                        continue

                    title = getattr(chat, "title", "") or "Telegram public group"
                    url = _chat_link(chat, msg.id)
                    item = {
                        "source": "Telegram Global Search",
                        "url": url,
                        "title": f"Telegram Global | {title}",
                        "text": text,
                        "published": dt.astimezone(timezone.utc).isoformat(),
                        "author": _sender_name(sender),
                        "source_bucket": "telegram_global_search",
                        "telegram_chat": title,
                        "telegram_query": query,
                    }
                    items[url] = item
                    kept += 1
            except FloodWaitError as exc:
                print(f"TELEGRAM_GLOBAL_FLOOD_WAIT query={query!r} seconds={exc.seconds}")
                break
            except Exception as exc:
                print(f"TELEGRAM_GLOBAL_QUERY_ERROR query={query!r} {exc}")

            query_counts[query] = kept
            print(f"TELEGRAM_GLOBAL_QUERY [{idx}/{query_limit}] query={query!r} seen={seen_for_query} kept={kept}")
    finally:
        await client.disconnect()

    out = list(items.values())
    out.sort(key=lambda x: x.get("published", ""), reverse=True)
    print(f"TELEGRAM_GLOBAL_COUNTS queries={len(query_counts)} unique_messages={len(out)}")
    return out


def collect_global_telegram():
    try:
        return asyncio.run(_collect_global())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_collect_global())
        finally:
            loop.close()
    except Exception as exc:
        print("TELEGRAM_GLOBAL_EXCEPTION", exc)
        return []
