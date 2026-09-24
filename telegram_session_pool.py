import os
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.sessions import StringSession


@dataclass
class SessionSlot:
    name: str
    session: str
    client: TelegramClient | None = None
    authorized: bool = False
    flood_until: float = 0.0


def _env_sessions():
    names = [
        ("WORLD", "TELEGRAM_STRING_SESSION"),
        ("WORLD_2", "TELEGRAM_STRING_SESSION_WORLD_2"),
        ("WORLD_3", "TELEGRAM_STRING_SESSION_WORLD_3"),
    ]
    out = []
    seen = set()
    for name, env_name in names:
        value = os.getenv(env_name, "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(SessionSlot(name=name, session=value))
    return out


async def open_pool(api_id: int, api_hash: str):
    slots = _env_sessions()
    ready = []
    for slot in slots:
        try:
            client = TelegramClient(StringSession(slot.session), api_id, api_hash)
            await client.connect()
            slot.client = client
            slot.authorized = bool(await client.is_user_authorized())
            if slot.authorized:
                ready.append(slot)
            else:
                await client.disconnect()
        except Exception as exc:
            print(f"TELEGRAM_SESSION_POOL_OPEN_ERROR slot={slot.name} {type(exc).__name__}: {exc}")
    print(f"TELEGRAM_SESSION_POOL ready={len(ready)} configured={len(slots)}")
    return ready


async def close_pool(slots):
    for slot in slots:
        client = getattr(slot, "client", None)
        if not client:
            continue
        try:
            await client.disconnect()
        except Exception:
            pass


def next_slot(slots, start_index=0):
    if not slots:
        return None, -1
    idx = start_index % len(slots)
    return slots[idx], idx


def rotate_index(slots, current_index):
    if not slots:
        return -1
    return (current_index + 1) % len(slots)
