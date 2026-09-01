import os
import re
import asyncio
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User


PROPERTY_RE = re.compile(
    r"(?:property|apartment|flat|house|villa|studio|land|plot|real\s+estate|"
    r"квартир\w*|апартамент\w*|дом\w*|вилл\w*|недвижимост\w*|студи\w*|участ\w*|"
    r"daire|ev|villa|arsa|gayrimenkul|konut|"
    r"immobilie|wohnung|haus|grundst(?:u|ü)ck|"
    r"nieruchomo\w*|mieszkan\w*|apartament\w*|dom\w*|działk\w*|dzialk\w*)",
    re.I,
)
REQUEST_VOICE_RE = re.compile(
    r"(?:\b(?:i|we)\b.{0,45}\b(?:want|looking|need|plan|planning|considering|ready|seeking)\b|"
    r"\b(?:я|мы)\b.{0,45}\b(?:хочу|хотим|ищу|ищем|нужн\w*|планир\w*|готов\w*)\b|"
    r"\b(?:ben|biz)\b.{0,45}\b(?:istiyorum|istiyoruz|arıyorum|ariyorum|bakıyorum|bakiyorum|düşünüyorum|dusunuyorum)\b|"
    r"\b(?:ich|wir)\b.{0,45}\b(?:suche|suchen|möchte|moechte|möchten|moechten|will|wollen)\b|"
    r"\b(?:ja|my)\b.{0,45}\b(?:chcę|chcemy|szukam|szukamy|planuję|planujemy)\b|"
    r"\bje\b.{0,30}\b(?:cherche|veux|souhaite)\b|\b(?:ik|wij|we)\b.{0,30}\b(?:zoek|zoeken|wil|willen)\b)",
    re.I | re.S,
)
PURCHASE_RE = re.compile(
    r"(?:\b(?:buy|purchase|buying|purchasing)\b|\b(?:купить|куплю|покупк\w*|приобрест\w*)\b|"
    r"\b(?:satın\s+al\w*|almak)\b|\b(?:kaufen|kauf|erwerben)\b|"
    r"\b(?:kupić|kupic|zakupić|zakupic)\b|\bacheter\b|\bkopen\b)",
    re.I,
)
PURCHASE_QUALIFIER_RE = re.compile(
    r"(?:title\s+deed|deed|ownership|freehold|mortgage|payment\s+plan|installment|deposit|"
    r"тапу|титул\w*|переуступк\w*|ипотек\w*|рассрочк\w*|первоначальн\w*\s+взнос\w*|"
    r"tapu|koçan|kocan|eşdeğer|esdeger|tahsis|peşinat|pesinat|taksit|"
    r"grundbuch|eigentum|hypothek|zahlungsplan|ksi[eę]ga\s+wieczysta|własno\w*|wlasno\w*)",
    re.I,
)
RENT_RE = re.compile(
    r"(?:for\s+rent|looking\s+to\s+rent|rental|per\s+month|monthly|"
    r"аренд\w*|сниму|снять|сда[её]тся|в\s+месяц|посуточ\w*|"
    r"kiralık|aylık|günlük|mieten|miete|wynajem\w*)",
    re.I,
)
SELLER_RE = re.compile(
    r"(?:for\s+sale|owner'?s\s+sale|available\s+now|property\s+(?:id|code|ref)|listing\s+(?:id|ref)|"
    r"прода[её]тся|продам|код\s+объекта|номер\s+объекта|цена\s+от|"
    r"satılık|portföy|ilan\s+no|zu\s+verkaufen|na\s+sprzedaż|numer\s+oferty|"
    r"contact\s+(?:me|us)|whatsapp|dm\s+(?:me|us)|agent|agency|realtor|broker|developer|риэлтор|агентств\w*)",
    re.I,
)
AMOUNT_RE = re.compile(r"(?P<sym>[£€$])\s*(?P<num>\d[\d\s.,]*)(?P<k>\s*[kK])?")


def _purchase_scale_budget(text):
    for m in AMOUNT_RE.finditer(text or ""):
        raw = m.group("num").replace(" ", "")
        if "," in raw or "." in raw:
            parts = re.split(r"[.,]", raw)
            raw = "".join(parts) if len(parts[-1]) == 3 else raw.replace(",", ".")
        try:
            value = float(raw)
        except Exception:
            continue
        if m.group("k"):
            value *= 1000
        if value >= 10000:
            return True
    return False


def _actionable_property_buyer(text):
    body = " ".join(str(text or "").split())
    if not body or not PROPERTY_RE.search(body):
        return False
    if SELLER_RE.search(body) or RENT_RE.search(body):
        return False
    if not REQUEST_VOICE_RE.search(body):
        return False
    return bool(
        PURCHASE_RE.search(body)
        or PURCHASE_QUALIFIER_RE.search(body)
        or _purchase_scale_budget(body)
    )


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
    wanted = _csv_env("WORLD_TELEGRAM_MEMBER_CHATS")
    if wanted and not any(x in t for x in wanted):
        return False
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
    rejected = 0
    dialogs_seen = 0
    try:
        async for dialog in client.iter_dialogs(limit=max_dialogs):
            entity = dialog.entity
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

                    text = str(msg.message).strip()
                    if not _actionable_property_buyer(text):
                        rejected += 1
                        continue

                    sender = None
                    try:
                        sender = await msg.get_sender()
                    except Exception:
                        pass

                    items.append({
                        "source": "Telegram Member",
                        "url": _chat_link(entity, msg.id),
                        "title": f"Telegram | {title}",
                        "text": text,
                        "published": dt.astimezone(timezone.utc).isoformat() if dt else "",
                        "author": _sender_name(sender),
                        "source_bucket": "telegram_member_account",
                        "telegram_chat": title,
                    })
            except Exception as exc:
                print(f"TELEGRAM_MEMBER_CHAT_ERROR {title} {exc}")
    finally:
        await client.disconnect()

    print(f"TELEGRAM_MEMBER_COUNTS dialogs={dialogs_seen} messages={len(items)} rejected_nonbuyer={rejected}")
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
