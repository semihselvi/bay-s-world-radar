import asyncio
import os
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User


DEEP_BUYER_QUERIES = [
    "looking for", "want to buy", "price", "resale", "available", "1+1", "2+1", "3+1",
    "arıyorum", "almak istiyorum", "sahibinden", "var mı", "fiyat", "peşinat", "taksit",
    "ищу", "хочу купить", "нужна квартира", "цена", "рассрочка", "вторичка",
    "шукаю квартиру", "хочу купити", "szukam mieszkania", "chcę kupić",
]

NC_TITLE_HINTS = [
    "north cyprus", "northern cyprus", "northcyprus", "trnc", "kuzey kıbrıs", "kuzey kibris",
    "cyprus", "kıbrıs", "kibris", "кипр", "girne", "kyrenia", "iskele", "i̇skele",
    "long beach", "esentepe", "famagusta", "gazimağusa", "gazimagusa", "tatlısu", "tatlisu",
    "bafra", "lapta", "alsancak", "karşıyaka", "karsiyaka", "snc", "caesar", "sapphire",
    "isatis", "elysium", "fiora", "royal sun", "riverside",
]


def _csv_env(name):
    return [x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()]


def _title_allowed(title):
    low = (title or "").lower()
    explicit = _csv_env("WORLD_TELEGRAM_MEMBER_CHATS")
    if explicit:
        return any(x in low for x in explicit)
    return any(hint in low for hint in NC_TITLE_HINTS)


def _discussion_group(entity):
    if isinstance(entity, User) or not isinstance(entity, (Channel, Chat)):
        return False
    if isinstance(entity, Channel) and getattr(entity, "broadcast", False) and not getattr(entity, "megagroup", False):
        return False
    return True


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


def _rotating_queries(limit):
    limit = max(1, min(limit, len(DEEP_BUYER_QUERIES)))
    if limit >= len(DEEP_BUYER_QUERIES):
        return DEEP_BUYER_QUERIES[:]
    now = datetime.now(timezone.utc)
    slot = (now.timetuple().tm_yday * 8) + (now.hour // 3)
    start = (slot * limit) % len(DEEP_BUYER_QUERIES)
    return [DEEP_BUYER_QUERIES[(start + i) % len(DEEP_BUYER_QUERIES)] for i in range(limit)]


async def _collect():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    if not api_id or not api_hash or not session:
        print("TELEGRAM_DEEP_DISABLED missing TELEGRAM_API_ID/API_HASH/STRING_SESSION")
        return []

    lookback_hours = int(os.getenv("WORLD_LOOKBACK_HOURS", "8"))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    max_dialogs = max(5, min(60, int(os.getenv("WORLD_TELEGRAM_DEEP_MAX_DIALOGS", "24"))))
    query_limit = max(2, min(12, int(os.getenv("WORLD_TELEGRAM_DEEP_QUERY_LIMIT", "8"))))
    results_per_query = max(5, min(40, int(os.getenv("WORLD_TELEGRAM_DEEP_RESULTS", "18"))))
    queries = _rotating_queries(query_limit)

    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("TELEGRAM_DEEP_DISABLED session_not_authorized")
        await client.disconnect()
        return []

    items = {}
    dialogs = []
    try:
        async for dialog in client.iter_dialogs(limit=220):
            entity = dialog.entity
            if not _discussion_group(entity):
                continue
            title = getattr(entity, "title", "") or dialog.name or "Telegram group"
            if not _title_allowed(title):
                continue
            dialogs.append((entity, title))
            if len(dialogs) >= max_dialogs:
                break

        for d_idx, (entity, title) in enumerate(dialogs, 1):
            chat_hits = 0
            for query in queries:
                try:
                    async for msg in client.iter_messages(entity, search=query, limit=results_per_query):
                        if not msg or not getattr(msg, "message", None):
                            continue
                        dt = getattr(msg, "date", None)
                        if dt and dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        if not dt or dt < cutoff:
                            continue
                        sender = None
                        try:
                            sender = await msg.get_sender()
                        except Exception:
                            pass
                        if not isinstance(sender, User) or getattr(sender, "bot", False):
                            continue
                        text = str(msg.message).strip()
                        if not text:
                            continue
                        url = _chat_link(entity, msg.id)
                        items[url] = {
                            "source": "Telegram Joined-Group Deep Search", "url": url,
                            "title": f"Telegram Deep | {title}", "text": text,
                            "published": dt.astimezone(timezone.utc).isoformat(),
                            "author": _sender_name(sender), "source_bucket": "telegram_member_deep_search",
                            "telegram_chat": title, "telegram_query": query,
                        }
                        chat_hits += 1
                except FloodWaitError as exc:
                    print(f"TELEGRAM_DEEP_FLOOD_WAIT chat={title!r} query={query!r} seconds={exc.seconds}")
                    return list(items.values())
                except Exception as exc:
                    print(f"TELEGRAM_DEEP_QUERY_ERROR chat={title!r} query={query!r} {exc}")
            print(f"TELEGRAM_DEEP_CHAT [{d_idx}/{len(dialogs)}] chat={title!r} raw_hits={chat_hits}")
    finally:
        await client.disconnect()

    out = list(items.values())
    out.sort(key=lambda x: x.get("published", ""), reverse=True)
    print(f"TELEGRAM_DEEP_COUNTS dialogs={len(dialogs)} queries={len(queries)} unique_messages={len(out)}")
    return out


def collect_member_deep_search():
    try:
        return asyncio.run(_collect())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_collect())
        finally:
            loop.close()
    except Exception as exc:
        print("TELEGRAM_DEEP_EXCEPTION", exc)
        return []
