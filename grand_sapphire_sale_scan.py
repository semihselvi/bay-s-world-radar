from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User

QUERIES = [
    "Grand Sapphire",
    "Grand Sapphire Resort",
    "Grand Sapphire İskele",
    "Гранд Сапфир",
    "Гранд Сапфир Искеле",
]
SALE_RE = re.compile(
    r"(?:for\s+sale|sale|resale|selling|sat[ıi]l[ıi]k|sat[ıi]yorum|"
    r"продаю|продам|прода[её]тся|продажа|перепродаж|вторичк|"
    r"£\s?\d|\d[\d\s,.]*\s?£)",
    re.I,
)
PROJECT_RE = re.compile(
    r"(?:grand\s+sapphire|grand\s+sap+hire|гранд\s+сапфир)",
    re.I,
)


def link(chat, msg_id):
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{msg_id}"
    cid = abs(int(getattr(chat, "id", 0) or 0))
    return f"https://t.me/c/{cid}/{msg_id}" if cid else ""


def author_name(sender):
    if not isinstance(sender, User) or getattr(sender, "bot", False):
        return ""
    username = getattr(sender, "username", None)
    if username:
        return f"@{username}"
    first = getattr(sender, "first_name", "") or ""
    last = getattr(sender, "last_name", "") or ""
    return " ".join(x for x in (first, last) if x).strip()


def extract(text):
    room = ""
    m = re.search(r"\b(?:studio|студи\w*|[0-6]\s*\+\s*[0-3])\b", text, re.I)
    if m:
        room = m.group(0).replace(" ", "")
    price = ""
    m = re.search(r"(?:£\s?\d[\d\s,.]*|\b\d[\d\s,.]*\s?£)", text)
    if m:
        price = m.group(0).strip()
    sqm = ""
    m = re.search(r"\b\d{2,4}(?:[.,]\d+)?\s*(?:m2|m²|sqm|кв\.?\s?м)", text, re.I)
    if m:
        sqm = m.group(0).strip()
    floor = ""
    m = re.search(r"(?:floor|kat|этаж)\s*[:\-]?\s*\d+|\b\d+\s*(?:floor|kat|этаж)", text, re.I)
    if m:
        floor = m.group(0).strip()
    payment = ""
    if re.search(r"рассроч|installment|payment\s+plan|taksit", text, re.I):
        payment = "INSTALLMENT"
    return room, price, sqm, floor, payment


async def main():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    if not api_id or not api_hash or not session:
        raise SystemExit("Missing Telegram credentials")

    days = max(1, min(180, int(os.getenv("GRAND_SAPPHIRE_DAYS", "30"))))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit("Telegram session unauthorized")

    found = {}
    try:
        for query in QUERIES:
            async for msg in client.iter_messages(None, search=query, limit=200):
                dt = getattr(msg, "date", None)
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if not dt or dt < cutoff:
                    continue
                text = str(getattr(msg, "message", "") or "").strip()
                if not text or not PROJECT_RE.search(text) or not SALE_RE.search(text):
                    continue
                try:
                    chat = await msg.get_chat()
                except Exception:
                    chat = None
                if not isinstance(chat, (Channel, Chat)):
                    continue
                try:
                    sender = await msg.get_sender()
                except Exception:
                    sender = None
                author = author_name(sender)
                if not author:
                    continue
                url = link(chat, msg.id)
                room, price, sqm, floor, payment = extract(text)
                found[url] = {
                    "published": dt.astimezone(timezone.utc).isoformat(),
                    "group": getattr(chat, "title", "") or "",
                    "group_username": getattr(chat, "username", "") or "",
                    "author": author,
                    "room": room,
                    "price": price,
                    "sqm": sqm,
                    "floor": floor,
                    "payment": payment,
                    "url": url,
                    "text": text,
                }
    finally:
        await client.disconnect()

    rows = sorted(found.values(), key=lambda x: x["published"], reverse=True)
    print("GRAND_SAPPHIRE_SCAN_SUMMARY", json.dumps({"days": days, "count": len(rows)}, ensure_ascii=False))
    for i, row in enumerate(rows, 1):
        print("GRAND_SAPPHIRE_LISTING", json.dumps({"n": i, **row}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
