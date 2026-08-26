from __future__ import annotations

import hashlib
from typing import Any

import main
from north_cyprus_semantic_dedupe import stable_identity, extract_phones

OWNER_COLLECTION = "bay_s_nc_property_owner_catcher"
AGENT_COLLECTION = "bay_s_nc_agent_sources"

_seen_in_process: set[str] = set()
_db_cache = None
_db_loaded = False


def _db():
    global _db_cache, _db_loaded
    if _db_loaded:
        return _db_cache
    _db_loaded = True
    try:
        _db_cache = main.firestore_client()
    except Exception as exc:
        print("NC_INTENT_ROUTE_DB_ERROR", exc)
        _db_cache = None
    return _db_cache


def _route_key(item: dict[str, Any], intent_class: str) -> str:
    ident = stable_identity(item)
    if not ident:
        phones = extract_phones(item.get("text") or "")
        if phones:
            ident = "phone:" + sorted(phones)[0]
    if not ident:
        ident = str(item.get("url") or "") or str(item.get("author") or "") + "|" + str(item.get("text") or "")[:500]
    return hashlib.sha1((intent_class + "|" + ident).encode("utf-8")).hexdigest()


def route_supply_candidate(item: dict[str, Any], intent: dict[str, Any]) -> None:
    """Persist supply-side candidates without leaking them into Buyer Catcher."""
    intent_class = str(intent.get("intent_class") or "")
    if intent_class not in {"OWNER", "AGENT"}:
        return
    collection = OWNER_COLLECTION if intent_class == "OWNER" else AGENT_COLLECTION
    key = _route_key(item, intent_class)
    process_key = collection + "|" + key + "|" + str(item.get("url") or "")
    if process_key in _seen_in_process:
        return
    _seen_in_process.add(process_key)

    db = _db()
    if not db:
        return
    try:
        ref = db.collection(collection).document(key)
        existing = ref.get()
        old = existing.to_dict() if existing.exists else {}
        urls = list(old.get("source_links") or [])
        for url in list(item.get("source_links") or []) + [item.get("url")]:
            if url and url not in urls:
                urls.append(url)
        chats = list(old.get("source_chats") or [])
        for chat in list(item.get("source_chats") or []) + [item.get("telegram_chat")]:
            if chat and chat not in chats:
                chats.append(chat)
        aliases = list(old.get("author_aliases") or [])
        for author in list(item.get("author_aliases") or []) + [item.get("author")]:
            if author and author not in aliases:
                aliases.append(author)

        now = main.now_utc().isoformat()
        payload = {
            "intent_class": intent_class,
            "intent_confidence": int(intent.get("intent_confidence") or 0),
            "publisher_type": item.get("publisher_type", ""),
            "publisher_confidence": int(item.get("publisher_confidence") or 0),
            "publisher_listing_count": int(item.get("publisher_listing_count") or 0),
            "author": item.get("author", ""),
            "telegram_user_id": item.get("telegram_user_id", ""),
            "telegram_chat": item.get("telegram_chat", ""),
            "latest_url": item.get("url", ""),
            "latest_text": str(item.get("text") or "")[:5000],
            "latest_published": item.get("published", ""),
            "requirements": intent.get("requirements") or {},
            "source_links": urls[:30],
            "source_chats": chats[:30],
            "author_aliases": aliases[:20],
            "first_seen": old.get("first_seen") or now,
            "last_seen": now,
            "evidence_count": int(old.get("evidence_count", 0) or 0) + 1,
        }
        ref.set(payload, merge=True)
    except Exception as exc:
        print("NC_INTENT_ROUTE_WRITE_ERROR", intent_class, exc)
