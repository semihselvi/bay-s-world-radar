import hashlib
import os
import re

import main
import shard_runner
import source_crawler_v2
import north_cyprus_focus

DYNAMIC_SOURCE_COLLECTION = "bay_s_dynamic_sources"


def _load_dynamic_channels(limit=40):
    db = main.firestore_client()
    if not db:
        return set()
    channels = set()
    try:
        docs = (
            db.collection(DYNAMIC_SOURCE_COLLECTION)
            .where("market", "==", "north_cyprus")
            .where("type", "==", "telegram_public")
            .where("status", "==", "active")
            .limit(limit)
            .stream()
        )
        for doc in docs:
            data = doc.to_dict() or {}
            username = str(data.get("username", "")).strip().lstrip("@")
            if username:
                channels.add(username)
    except Exception as exc:
        print("DYNAMIC_SOURCE_LOAD_FALLBACK", exc)
        try:
            for doc in db.collection(DYNAMIC_SOURCE_COLLECTION).limit(100).stream():
                data = doc.to_dict() or {}
                if data.get("market") != "north_cyprus" or data.get("type") != "telegram_public" or data.get("status") != "active":
                    continue
                username = str(data.get("username", "")).strip().lstrip("@")
                if username:
                    channels.add(username)
                if len(channels) >= limit:
                    break
        except Exception as inner:
            print("DYNAMIC_SOURCE_LOAD_ERROR", inner)
    print(f"DYNAMIC_TELEGRAM_LOADED count={len(channels)}")
    return channels


def _persist_channels(channels, discovered_by):
    if not channels:
        return
    db = main.firestore_client()
    if not db:
        return
    now = main.now_utc().isoformat()
    batch = db.batch()
    count = 0
    for username in sorted(set(channels)):
        username = str(username).strip().lstrip("@")
        if not username:
            continue
        doc_id = hashlib.sha1(username.lower().encode("utf-8")).hexdigest()
        batch.set(
            db.collection(DYNAMIC_SOURCE_COLLECTION).document(doc_id),
            {
                "type": "telegram_public",
                "market": "north_cyprus",
                "username": username,
                "url": f"https://t.me/{username}",
                "status": "active",
                "discovered_by": discovered_by,
                "last_seen": now,
            },
            merge=True,
        )
        count += 1
    if count:
        try:
            batch.commit()
            print(f"DYNAMIC_TELEGRAM_SAVED count={count} by={discovered_by}")
        except Exception as exc:
            # Dynamic-source persistence is an optimisation, never a reason to
            # abort the buyer scan. Keep scanning even during Firestore outages
            # or client-library regressions.
            print(f"DYNAMIC_TELEGRAM_SAVE_ERROR count={count} by={discovered_by} {exc}")


_dynamic_channels = _load_dynamic_channels()

# The dedicated hunter can use community domains that the general World Radar
# intentionally keeps out of its stricter production allow-list.
north_cyprus_focus.ALLOWED_USER_DOMAINS.add("forum.awd.ru")

# High-recall scanning also sees service advertisements in mixed Cyprus groups.
# Keep those out without narrowing genuine property-buyer phrases. A direct
# service phrase is enough; otherwise require several commercial signals.
_original_promotional_service_ad = north_cyprus_focus._promotional_service_ad
TRANSFER_SERVICE_PATTERNS = [
    r"услуги трансфера",
    r"трансфер (?:в|до|из) аэропорт",
    r"трансфер до места проживания",
    r"airport transfer",
    r"transfer service",
    r"licensed (?:car|vehicle)",
    r"лицензированн(?:ых|ые) автомобил",
    r"надежный водитель",
    r"встреч[аи] в аэропорте",
    r"детск(?:ого|ое) кресл",
    r"mercedes vito",
    r"mercedes v[- ]?class",
    r"mercedes e[- ]?class",
]

EDUCATION_SERVICE_PATTERNS = [
    r"study in north cyprus",
    r"\bscholarship(?:s)?\b",
    r"up to 100% scholarship",
    r"university admission",
    r"visa support",
    r"student job access",
    r"settlement support",
    r"accommodation.*settlement",
    r"limited slots",
    r"upcoming semester",
    r"begin your application",
]

# Preserve the remainder of the existing module behavior below.
" + "