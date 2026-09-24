from __future__ import annotations

import asyncio
import hashlib
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.types import (
    Channel, Chat, User,
    MessageEntityMention, MessageEntityUrl, MessageEntityTextUrl,
)

import main
from telegram_known_public_groups import KNOWN_GROUPS

COLLECTION = "bay_s_dynamic_sources"
SCAN_COLLECTION = "bay_s_source_discovery_scans"

RE_TME = re.compile(
    r"(?:https?://)?(?:t(?:elegram)?\.me|telegram\.dog)/(?P<path>[A-Za-z0-9_+\-/]{3,})",
    re.I,
)
RE_USER = re.compile(r"(?<!\w)@([A-Za-z][A-Za-z0-9_]{3,30})")
RE_INVITE = re.compile(r"(?:https?://)?t\.me/(?P<invite>\+[A-Za-z0-9_-]{8,}|joinchat/[A-Za-z0-9_-]{8,})", re.I)

NC_HINTS = re.compile(
    r"(north(?:ern)?\s+cyprus|kuzey\s+k[ıi]br[ıi]s|\bkktc\b|северн\w*\s+кипр|"
    r"\biskele\b|\bİskele\b|long\s+beach|girne|kyrenia|esentepe|famagusta|gazima[ğg]usa|"
    r"yenibo[ğg]azi[çc]i|lapta|alsancak|tatl[ıi]su|bafra|caesar\s+resort|grand\s+sapphire|"
    r"royal\s+sun|riverside\s+life|isatis|elysium|fiora|قبرص\s+الشمالية|قبرس\s+شمالی)",
    re.I,
)

BUYERISH = re.compile(
    r"(looking\s+to\s+buy|want\s+to\s+buy|looking\s+for|budget|cash\s+buyer|"
    r"sat[ıi]n\s+al|daire\s+ar[ıi]yorum|ev\s+ar[ıi]yorum|b[üu]t[çc]e|"
    r"хочу\s+купить|ищу\s+квартир|ищу\s+вилл|бюджет|"
    r"wohnung\s+kaufen|immobilie\s+kaufen|acheter|kupi[ćc])",
    re.I,
)

PROMO = re.compile(
    r"(contact\s+us|whatsapp|dm\s+us|our\s+project|our\s+properties|estate\s+agency|"
    r"developer|starting\s+from|limited\s+offer|прода[её]тся|риэлтор|агентств|sat[ıi]l[ıi]k)",
    re.I,
)


def now_utc():
    return datetime.now(timezone.utc)


def _clean_username(value: str) -> str:
    value = str(value or "").strip()
    value = value.lstrip("@")
    value = value.split("?")[0].split("/")[0]
    return value if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,30}", value) else ""


def extract_refs(text: str, entities=None):
    text = str(text or "")
    users = set()
    invites = set()

    for entity in entities or []:
        try:
            if isinstance(entity, MessageEntityMention):
                raw = text[entity.offset:entity.offset + entity.length]
                u = _clean_username(raw)
                if u:
                    users.add(u)
            elif isinstance(entity, MessageEntityUrl):
                raw = text[entity.offset:entity.offset + entity.length]
                m = RE_TME.search(raw)
                if m:
                    path = m.group("path")
                    if path.startswith("+") or path.lower().startswith("joinchat/"):
                        invites.add("https://t.me/" + path)
                    else:
                        u = _clean_username(path)
                        if u:
                            users.add(u)
            elif isinstance(entity, MessageEntityTextUrl):
                raw = str(getattr(entity, "url", "") or "")
                m = RE_TME.search(raw)
                if m:
                    path = m.group("path")
                    if path.startswith("+") or path.lower().startswith("joinchat/"):
                        invites.add("https://t.me/" + path)
                    else:
                        u = _clean_username(path)
                        if u:
                            users.add(u)
        except Exception:
            pass

    for m in RE_USER.finditer(text):
        u = _clean_username(m.group(1))
        if u:
            users.add(u)

    for m in RE_TME.finditer(text):
        path = m.group("path")
        if path.startswith("+") or path.lower().startswith("joinchat/"):
            invites.add("https://t.me/" + path)
        else:
            u = _clean_username(path)
            if u:
                users.add(u)

    for m in RE_INVITE.finditer(text):
        invites.add("https://t.me/" + m.group("invite"))

    return users, invites


def _source_doc_id(kind: str, value: str) -> str:
    return hashlib.sha1(f"{kind}|{value.lower()}".encode("utf-8")).hexdigest()


def _load_dynamic_seeds(limit: int = 250):
    db = main.firestore_client()
    if not db:
        return []
    rows = []
    try:
        for doc in db.collection(COLLECTION).limit(1000).stream():
            data = doc.to_dict() or {}
            if data.get("market") != "north_cyprus" or data.get("type") != "telegram_public":
                continue
            if data.get("status") not in {"active", "candidate", "discovered"}:
                continue
            username = _clean_username(data.get("username") or "")
            if not username:
                continue
            priority = float(data.get("priority_score", 0) or 0)
            discovery = float(data.get("discovery_score", 0) or 0)
            rows.append((priority + discovery, username))
    except Exception as exc:
        print("SOURCE_DISCOVERY_SEED_LOAD_ERROR", exc)
    rows.sort(reverse=True)
    out = []
    seen = set()
    for _, username in rows:
        key = username.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(username)
        if len(out) >= limit:
            break
    return out


def _seed_usernames():
    out = []
    seen = set()
    for value in list(KNOWN_GROUPS) + _load_dynamic_seeds(int(os.getenv("SOURCE_DISCOVERY_DYNAMIC_SEEDS", "220"))):
        u = _clean_username(value)
        if not u or u.lower() in seen:
            continue
        seen.add(u.lower())
        out.append(u)
    return out


async def _member_count(client, chat):
    try:
        if isinstance(chat, Channel):
            full = await client(GetFullChannelRequest(chat))
            return int(getattr(getattr(full, "full_chat", None), "participants_count", 0) or 0)
    except Exception:
        pass
    return int(getattr(chat, "participants_count", 0) or 0)


async def _sample_group(client, chat, limit: int, cutoff):
    human = 0
    nc_hits = 0
    buyer_hits = 0
    promo_hits = 0
    newest = None

    async for msg in client.iter_messages(chat, limit=limit):
        dt = getattr(msg, "date", None)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt and dt < cutoff:
            break
        text = str(getattr(msg, "message", "") or "").strip()
        if not text:
            continue
        sender = None
        try:
            sender = await msg.get_sender()
        except Exception:
            pass
        if isinstance(sender, User) and getattr(sender, "bot", False):
            continue
        human += 1
        newest = dt if dt and (newest is None or dt > newest) else newest
        if NC_HINTS.search(text):
            nc_hits += 1
        if BUYERISH.search(text):
            buyer_hits += 1
        if PROMO.search(text):
            promo_hits += 1

    return {
        "sample_human_messages": human,
        "sample_nc_hits": nc_hits,
        "sample_buyer_hits": buyer_hits,
        "sample_promo_hits": promo_hits,
        "sample_latest_message_at": newest.isoformat() if newest else "",
    }


def _score(mentions: int, source_count: int, member_count: int, sample: dict):
    human = int(sample.get("sample_human_messages", 0) or 0)
    nc_hits = int(sample.get("sample_nc_hits", 0) or 0)
    buyer_hits = int(sample.get("sample_buyer_hits", 0) or 0)
    promo_hits = int(sample.get("sample_promo_hits", 0) or 0)

    score = min(35, source_count * 8) + min(20, mentions * 2)
    if member_count:
        if member_count >= 10000:
            score += 12
        elif member_count >= 2000:
            score += 9
        elif member_count >= 300:
            score += 5
    if human:
        score += min(12, human / 5)
        score += min(18, buyer_hits * 4)
        score += min(10, nc_hits * 1.5)
        score -= min(15, promo_hits * 1.5)
    return round(max(0.0, min(100.0, score)), 2)


async def discover():
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    session = os.getenv("TELEGRAM_STRING_SESSION", "").strip()
    if not api_id or not api_hash or not session:
        print("SOURCE_DISCOVERY_DISABLED missing Telegram credentials")
        return {}

    seed_limit = int(os.getenv("SOURCE_DISCOVERY_SEED_LIMIT", "120"))
    messages_per_seed = int(os.getenv("SOURCE_DISCOVERY_MESSAGES_PER_SEED", "160"))
    verify_limit = int(os.getenv("SOURCE_DISCOVERY_VERIFY_LIMIT", "220"))
    sample_messages = int(os.getenv("SOURCE_DISCOVERY_SAMPLE_MESSAGES", "80"))
    lookback_days = int(os.getenv("SOURCE_DISCOVERY_LOOKBACK_DAYS", "21"))
    cutoff = now_utc() - timedelta(days=lookback_days)

    seeds = _seed_usernames()[:seed_limit]
    mentions = Counter()
    source_sets = defaultdict(set)
    invites = Counter()
    seen_seed_ids = set()
    errors = []

    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        print("SOURCE_DISCOVERY_UNAUTHORIZED")
        return {}

    try:
        for idx, seed in enumerate(seeds, 1):
            try:
                chat = await client.get_entity(seed)
                if not isinstance(chat, (Channel, Chat)) or isinstance(chat, User):
                    continue
                seen_seed_ids.add(int(getattr(chat, "id", 0) or 0))
                scanned = 0
                found = 0
                async for msg in client.iter_messages(chat, limit=messages_per_seed):
                    dt = getattr(msg, "date", None)
                    if dt and dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt and dt < cutoff:
                        break
                    text = str(getattr(msg, "message", "") or "")
                    if not text:
                        continue
                    scanned += 1
                    users, inv = extract_refs(text, getattr(msg, "entities", None) or [])
                    for user in users:
                        if user.lower() == seed.lower():
                            continue
                        mentions[user] += 1
                        source_sets[user].add(seed.lower())
                        found += 1
                    for link in inv:
                        invites[link] += 1
                print(f"SOURCE_DISCOVERY_SEED [{idx}/{len(seeds)}] @{seed} scanned={scanned} refs={found}")
            except FloodWaitError as exc:
                errors.append(f"flood:{seed}:{exc.seconds}")
                print(f"SOURCE_DISCOVERY_FLOOD_WAIT seed={seed} seconds={exc.seconds}")
                break
            except Exception as exc:
                errors.append(f"seed:{seed}:{type(exc).__name__}:{exc}")
                print("SOURCE_DISCOVERY_SEED_ERROR", seed, exc)

        ranked = sorted(
            mentions,
            key=lambda u: (len(source_sets[u]), mentions[u]),
            reverse=True,
        )[:verify_limit]

        db = main.firestore_client()
        now = now_utc().isoformat()
        verified = []
        for idx, username in enumerate(ranked, 1):
            try:
                entity = await client.get_entity(username)
                if not isinstance(entity, Channel) or not getattr(entity, "megagroup", False):
                    continue
                if not getattr(entity, "username", None):
                    continue
                title = str(getattr(entity, "title", "") or username)
                title_nc = bool(NC_HINTS.search(title))
                sample = await _sample_group(client, entity, sample_messages, cutoff)
                # A group must either look NC-related by title or demonstrate NC content in sample.
                if not title_nc and int(sample.get("sample_nc_hits", 0) or 0) == 0:
                    continue
                members = await _member_count(client, entity)
                score = _score(mentions[username], len(source_sets[username]), members, sample)
                status = "active" if score >= 28 else "candidate"
                row = {
                    "type": "telegram_public",
                    "market": "north_cyprus",
                    "username": str(entity.username),
                    "title": title,
                    "url": f"https://t.me/{entity.username}",
                    "status": status,
                    "discovered_by": "telegram_source_discovery_radar",
                    "discovery_score": score,
                    "mention_count": int(mentions[username]),
                    "mention_source_count": len(source_sets[username]),
                    "mention_sources": sorted(source_sets[username])[:20],
                    "members": members,
                    "last_seen": now,
                    **sample,
                }
                verified.append(row)
                if db:
                    db.collection(COLLECTION).document(_source_doc_id("telegram_public", str(entity.username))).set(row, merge=True)
                print(
                    f"SOURCE_DISCOVERY_VERIFY [{idx}/{len(ranked)}] @{entity.username} "
                    f"score={score} sources={len(source_sets[username])} mentions={mentions[username]} "
                    f"buyer_hits={sample['sample_buyer_hits']}"
                )
            except FloodWaitError as exc:
                errors.append(f"verify_flood:{username}:{exc.seconds}")
                print(f"SOURCE_DISCOVERY_VERIFY_FLOOD_WAIT username={username} seconds={exc.seconds}")
                break
            except Exception as exc:
                errors.append(f"verify:{username}:{type(exc).__name__}:{exc}")

        if db:
            for link, count in invites.most_common(100):
                db.collection(COLLECTION).document(_source_doc_id("telegram_private_invite", link)).set({
                    "type": "telegram_private_invite",
                    "market": "north_cyprus",
                    "url": link,
                    "status": "join_candidate",
                    "discovered_by": "telegram_source_discovery_radar",
                    "mention_count": int(count),
                    "last_seen": now,
                }, merge=True)

        verified.sort(key=lambda x: x.get("discovery_score", 0), reverse=True)
        stats = {
            "started_at": now,
            "seed_groups": len(seeds),
            "unique_public_refs": len(mentions),
            "verified_groups": len(verified),
            "active_groups": sum(1 for x in verified if x.get("status") == "active"),
            "invite_candidates": len(invites),
            "errors": errors[:50],
            "top": [
                {
                    "username": x.get("username"),
                    "title": x.get("title"),
                    "score": x.get("discovery_score"),
                    "sources": x.get("mention_source_count"),
                    "mentions": x.get("mention_count"),
                    "buyer_hits": x.get("sample_buyer_hits"),
                    "members": x.get("members"),
                }
                for x in verified[:20]
            ],
        }
        if db:
            scan_id = now_utc().strftime("%Y%m%d%H%M%S")
            db.collection(SCAN_COLLECTION).document(scan_id).set(stats, merge=True)

        print("SOURCE_DISCOVERY_COMPLETE", stats)
        if verified:
            lines = [f"🕸 BAY-S SOURCE DISCOVERY | {len(verified)} DOĞRULANMIŞ GRUP"]
            for row in verified[:10]:
                lines.append(
                    f"\n@{row['username']} | skor {row['discovery_score']} | "
                    f"{row['mention_source_count']} kaynak/{row['mention_count']} mention"
                    f"\n{row['title'][:100]} | üyeler {row['members']} | buyer-hit {row['sample_buyer_hits']}"
                    f"\n{row['url']}"
                )
            main.notify_telegram("\n".join(lines)[:3900])
        return stats
    finally:
        await client.disconnect()


def run():
    try:
        return asyncio.run(discover())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(discover())
        finally:
            loop.close()


if __name__ == "__main__":
    run()
