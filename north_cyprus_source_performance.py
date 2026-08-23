import atexit
import hashlib
import math
from datetime import datetime, timezone

import main

COLLECTION = "bay_s_nc_source_performance"
_OBS = {}
_FLUSHED = False


def _norm(value):
    return " ".join(str(value or "").strip().lower().split())


def source_key(item):
    username = _norm(item.get("source_username"))
    if username:
        return f"telegram:@{username.lstrip('@')}"
    parent = _norm(item.get("telegram_parent_channel"))
    if parent:
        return f"telegram_parent:{parent}"
    chat = _norm(item.get("telegram_chat"))
    if chat:
        return f"telegram_chat:{chat}"
    bucket = _norm(item.get("source_bucket"))
    source = _norm(item.get("source"))
    title = _norm(item.get("title"))
    if bucket:
        return f"bucket:{bucket}"
    if source:
        return f"source:{source}"
    return f"title:{title[:120]}" if title else "unknown"


def _doc_id(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def observe(item, lead, reason):
    key = source_key(item)
    row = _OBS.setdefault(key, {
        "messages": 0, "accepted": 0, "hot": 0, "warm": 0, "potential": 0,
        "promo": 0, "rental": 0, "no_intent": 0,
        "source_key": key,
        "source_username": _norm(item.get("source_username")).lstrip("@"),
        "telegram_chat": str(item.get("telegram_chat") or "")[:180],
        "source": str(item.get("source") or "")[:180],
    })
    row["messages"] += 1
    if reason in ("promotional_or_seller", "seller_agent", "promotional_service_ad"):
        row["promo"] += 1
    elif reason == "rental":
        row["rental"] += 1
    elif reason in ("no_request_shape", "no_buyer_intent", "not_enough_user_discussion_signal"):
        row["no_intent"] += 1
    if lead:
        row["accepted"] += 1
        label = str(lead.get("classification") or "").lower()
        if label in ("hot", "warm", "potential"):
            row[label] += 1
        row["last_lead_at"] = main.now_utc().isoformat()


def _parse(value):
    try:
        return main.parse_dt(value)
    except Exception:
        return None


def score_doc(data):
    messages = max(0, int(data.get("messages", 0) or 0))
    hot = max(0, int(data.get("hot", 0) or 0))
    warm = max(0, int(data.get("warm", 0) or 0))
    potential = max(0, int(data.get("potential", 0) or 0))
    accepted = max(0, int(data.get("accepted", 0) or 0))
    promo = max(0, int(data.get("promo", 0) or 0))

    # Reward actual buyer yield much more than raw traffic. Use sqrt(message count)
    # so huge noisy groups do not automatically beat smaller productive groups.
    lead_value = hot * 32 + warm * 15 + potential * 6 + accepted * 2
    yield_score = (lead_value * 10.0) / math.sqrt(messages + 25)
    activity = min(10.0, math.log1p(messages) * 1.6)
    promo_penalty = min(18.0, (promo * 12.0) / (messages + 10))

    recency = 0.0
    last = _parse(data.get("last_lead_at"))
    if last:
        age_days = max(0.0, (datetime.now(timezone.utc) - last).total_seconds() / 86400)
        if age_days <= 2:
            recency = 18.0
        elif age_days <= 7:
            recency = 12.0
        elif age_days <= 30:
            recency = 6.0

    return round(yield_score + activity + recency - promo_penalty, 3)


def flush():
    global _FLUSHED
    if _FLUSHED or not _OBS:
        return
    _FLUSHED = True
    db = main.firestore_client()
    if not db:
        return
    now = main.now_utc().isoformat()
    try:
        for key, delta in _OBS.items():
            ref = db.collection(COLLECTION).document(_doc_id(key))
            existing = ref.get().to_dict() or {}
            merged = dict(existing)
            for field in ("messages", "accepted", "hot", "warm", "potential", "promo", "rental", "no_intent"):
                merged[field] = int(existing.get(field, 0) or 0) + int(delta.get(field, 0) or 0)
            for field in ("source_key", "source_username", "telegram_chat", "source"):
                if delta.get(field):
                    merged[field] = delta[field]
            if delta.get("last_lead_at"):
                merged["last_lead_at"] = delta["last_lead_at"]
            merged["last_scanned_at"] = now
            merged["priority_score"] = score_doc(merged)
            ref.set(merged, merge=True)
        print(f"NC_SOURCE_PERFORMANCE_FLUSH sources={len(_OBS)}")
    except Exception as exc:
        print("NC_SOURCE_PERFORMANCE_FLUSH_ERROR", exc)


def ranked_usernames(usernames):
    """Rank known Telegram usernames by observed buyer yield, without starving exploration."""
    names = []
    seen = set()
    for value in usernames:
        name = str(value or "").strip().lstrip("@")
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
    if len(names) <= 1:
        return names

    db = main.firestore_client()
    scores = {}
    if db:
        try:
            for doc in db.collection(COLLECTION).limit(300).stream():
                data = doc.to_dict() or {}
                username = str(data.get("source_username") or "").strip().lstrip("@").lower()
                if username:
                    scores[username] = float(data.get("priority_score", score_doc(data)) or 0)
        except Exception as exc:
            print("NC_SOURCE_PERFORMANCE_LOAD_ERROR", exc)

    productive = sorted(names, key=lambda x: (scores.get(x.lower(), 0.0), x.lower()), reverse=True)

    # 75% performance-ranked + 25% rotating exploration. This means a source with
    # zero historical leads keeps getting chances and can climb later.
    keep = max(1, int(len(names) * 0.75))
    top = productive[:keep]
    rest = [x for x in names if x not in top]
    if rest:
        now = datetime.now(timezone.utc)
        slot = now.timetuple().tm_yday * 8 + now.hour // 3
        shift = slot % len(rest)
        rest = rest[shift:] + rest[:shift]
    ranked = top + rest
    print("NC_SOURCE_PRIORITY top=" + ",".join(f"@{x}:{scores.get(x.lower(),0):.1f}" for x in ranked[:10]))
    return ranked


atexit.register(flush)
