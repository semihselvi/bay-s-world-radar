import hashlib
import os
import re
from datetime import timedelta

import main
import north_cyprus_catcher as base


_original_notified_before = base._notified_before
_original_mark_notified = base._mark_notified


def _normalized_text(value):
    text = str(value or "").casefold()
    text = re.sub(r"https?://\S+", " ", text, flags=re.I)
    text = re.sub(r"t\.me/\S+", " ", text, flags=re.I)
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def content_fingerprint(lead):
    """Stable fingerprint for repeated same-person/same-text notifications.

    Public @usernames are safe to compare across groups. Display names are only
    compared inside the same Telegram chat to reduce accidental collisions.
    """
    author = " ".join(str(lead.get("author") or "").strip().casefold().split())
    if not author:
        return ""
    body = _normalized_text(lead.get("text"))
    if len(body) < 28:
        return ""

    if author.startswith("@"):
        identity = author
    else:
        chat = " ".join(str(lead.get("telegram_chat") or "").strip().casefold().split())
        if not chat:
            return ""
        identity = f"{chat}|{author}"

    raw = f"{identity}|{body[:5000]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _content_doc_id(lead):
    fp = content_fingerprint(lead)
    return f"content_{fp}" if fp else ""


def _recent_content_seen(db, lead):
    if not db:
        return False
    doc_id = _content_doc_id(lead)
    if not doc_id:
        return False
    try:
        snap = db.collection(base.NOTIFIED_COLLECTION).document(doc_id).get()
        if not snap.exists:
            return False
        data = snap.to_dict() or {}
        notified = main.parse_dt(data.get("notified_at", ""))
        if notified is None:
            return True
        hours = max(1, min(24 * 30, int(os.getenv("NC_SAME_TEXT_DEDUPE_HOURS", "168"))))
        return notified >= main.now_utc() - timedelta(hours=hours)
    except Exception as exc:
        print("NC_CONTENT_DEDUPE_READ_ERROR", exc)
        return False


def notified_before_with_content(db, lead):
    # Keep legacy URL-based dedupe first, then suppress same-author/same-text
    # reposts even when Telegram assigns a different message URL each time.
    if _original_notified_before(db, lead):
        return True
    return _recent_content_seen(db, lead)


def mark_notified_with_content(db, lead):
    _original_mark_notified(db, lead)
    if not db:
        return
    doc_id = _content_doc_id(lead)
    if not doc_id:
        return
    try:
        db.collection(base.NOTIFIED_COLLECTION).document(doc_id).set({
            "dedupe_type": "same_author_same_text",
            "content_fingerprint": doc_id.removeprefix("content_"),
            "url": lead.get("url", ""),
            "author": lead.get("author", ""),
            "telegram_chat": lead.get("telegram_chat", ""),
            "classification": lead.get("classification", ""),
            "notified_at": main.now_utc().isoformat(),
        }, merge=True)
    except Exception as exc:
        print("NC_CONTENT_DEDUPE_WRITE_ERROR", exc)


base._notified_before = notified_before_with_content
base._mark_notified = mark_notified_with_content
