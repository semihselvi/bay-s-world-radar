import os
import asyncio
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User


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
    title = getattr(sender, "title", "") or ""
    return " ".join(x for x in (first, last, title) if x).strip()


def _csv_env(name):
    return [x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()]


def _allowed_title(title):
    t = (title or "").lower()

    # Existing explicit allow-list remains authoritative when configured.
    wanted = _csv_env("WORLD_TELEGRAM_MEMBER_CHATS")
    if wanted and not any(x in t for x in wanted):
        return False

    # Optional broad title keywords let a dedicated shard scan only likely
    # North-Cyprus groups without changing the normal all-groups radar.
    keywords = _csv_env("WORLD_TELEGRAM_MEMBER_TITLE_KEYWORDS")
    if keywords and not any(x in t for x in keywords):
        return False

    return True


async def _collect():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    if not api_id or not api_hash or not session:
        print("TELEGRAM_MEMBER_DISABLED missing TELEGRAM_API_ID/API_HASH/STRING_SESSION")
        return []

    max_dialogs = int(os.getenv("WORLD_TELEGRAM_MEMBER_MAX_DIALOGS", "120"))
    max_messages = int(os.getenv("WORLD_TELEGRAM_MEMBER_MAX_MESSAGES", "40"))
    lookback = int(os.getenv("WORLD_LOOKBACK_HOURS", "24"))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback)

    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("TELEGRAM_MEMBER_DISABLED session_not_authorized")
        await client.disconnect()
        return []

    items = []
    dialogs_seen = 0
    try:
        async for dialog in client.iter_dialogs(limit=max_dialogs):
            entity = dialog.entity
            # Privacy boundary: only groups/supergroups/channels. Never private 1:1 chats.
            if isinstance(entity, User):
                continue
            if not isinstance(entity, (Channel, Chat)):
                continue

            title = getattr(entity, "title", "") or dialog.name or "Telegram group"
            if not _allowed_title(title):
                continue

            dialogs_seen += 1
            try:
                async for msg in client.iter_messages(entity, limit=max_messages):
                    if not msg or not getattr(msg, "message", None):
                        continue
                    dt = msg.date
                    if dt and dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt and dt < cutoff:
                        break

                    sender = None
                    try:
                        sender = await msg.get_sender()
                    except Exception:
                        pass

                    items.append({
                        "source": "Telegram Member",
                        "url": _chat_link(entity, msg.id),
                        "title": f"Telegram | {title}",
                        "text": str(msg.message).strip(),
                        "published": dt.astimezone(timezone.utc).isoformat() if dt else "",
                        "author": _sender_name(sender),
                        "source_bucket": "telegram_member_account",
                        "telegram_chat": title,
                    })
            except Exception as exc:
                print(f"TELEGRAM_MEMBER_CHAT_ERROR {title} {exc}")
    finally:
        await client.disconnect()

    print(f"TELEGRAM_MEMBER_COUNTS dialogs={dialogs_seen} messages={len(items)}")
    return items


def collect_member_telegram():
    try:
        return asyncio.run(_collect())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_collect())
        finally:
            loop.close()
    except Exception as exc:
        print("TELEGRAM_MEMBER_EXCEPTION", exc)
        return []
