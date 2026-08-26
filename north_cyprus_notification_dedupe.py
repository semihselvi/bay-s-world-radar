import hashlib
import os
import re
from datetime import timedelta

import main
import north_cyprus_catcher as base
from north_cyprus_semantic_dedupe import stable_identity, extract_phones


_original_notified_before = base._notified_before
_original_mark_notified = base._mark_notified
PROFILE_COLLECTION = "bay_s_nc_lead_profiles"


def _normalized_text(value):
    text = str(value or "").casefold()
    text = re.sub(r"https?://\S+", " ", text, flags=re.I)
    text = re.sub(r"t\.me/\S+", " ", text, flags=re.I)
    text = re.sub(r"[\W_]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def content_fingerprint(lead):
    """Stable fingerprint for repeated same-person/same-text notifications."""
    body = _normalized_text(lead.get("text"))
    if len(body) < 28:
        return ""

    user_id = str(lead.get("telegram_user_id") or "").strip()
    author = " ".join(str(lead.get("author") or "").strip().casefold().split())
    if user_id.isdigit() and user_id != "0":
        identity = f"telegram_user:{user_id}"
    elif author.startswith("@"):
        identity = author
    else:
        chat = " ".join(str(lead.get("telegram_chat") or "").strip().casefold().split())
        if not author or not chat:
            return ""
        identity = f"{chat}|{author}"

    raw = f"{identity}|{body[:5000]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def person_fingerprint(lead):
    """Canonical person key shared by live Catcher and Recovery."""
    ident = stable_identity(lead)
    if not ident:
        phones = extract_phones(lead.get("text") or "")
        if phones:
            ident = "phone:" + sorted(phones)[0]
    if not ident:
        author = " ".join(str(lead.get("author") or "").strip().casefold().split())
        chat = " ".join(str(lead.get("telegram_chat") or "").strip().casefold().split())
        if author and chat:
            ident = "local:" + chat + "|" + author
    return hashlib.sha1(ident.encode("utf-8")).hexdigest() if ident else ""


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


def _profile_doc_id(lead):
    fp = person_fingerprint(lead)
    return f"person_{fp}" if fp else ""


def _lead_strength(lead):
    rank = {"HOT": 3, "WARM": 2, "POTENTIAL": 1}
    return rank.get(str(lead.get("classification") or ""), 0) * 1000 + int(lead.get("intent_confidence") or lead.get("intent_score") or 0)


def _update_profile(db, lead, mark_notified=False):
    doc_id = _profile_doc_id(lead)
    if not db or not doc_id:
        return
    try:
        ref = db.collection(PROFILE_COLLECTION).document(doc_id)
        snap = ref.get()
        old = snap.to_dict() if snap.exists else {}
        urls = list(old.get("source_links") or [])
        for url in list(lead.get("source_links") or []) + [lead.get("url")]:
            if url and url not in urls:
                urls.append(url)
        chats = list(old.get("source_chats") or [])
        for chat in list(lead.get("source_chats") or []) + [lead.get("telegram_chat")]:
            if chat and chat not in chats:
                chats.append(chat)

        old_strength = int(old.get("best_strength") or 0)
        new_strength = _lead_strength(lead)
        payload = {
            "author": lead.get("author", old.get("author", "")),
            "telegram_user_id": lead.get("telegram_user_id", old.get("telegram_user_id", "")),
            "intent_class": lead.get("intent_class", old.get("intent_class", "")),
            "intent_subtypes": lead.get("intent_subtypes") or old.get("intent_subtypes") or [],
            "intent_confidence": max(int(old.get("intent_confidence") or 0), int(lead.get("intent_confidence") or lead.get("intent_score") or 0)),
            "classification": lead.get("classification", old.get("classification", "")) if new_strength >= old_strength else old.get("classification", ""),
            "requirements": lead.get("requirements") or old.get("requirements") or {},
            "latest_url": lead.get("url", ""),
            "latest_text": str(lead.get("text") or "")[:5000],
            "latest_published": lead.get("published", ""),
            "last_seen": main.now_utc().isoformat(),
            "first_seen": old.get("first_seen") or main.now_utc().isoformat(),
            "source_links": urls[:30],
            "source_chats": chats[:30],
            "best_strength": max(old_strength, new_strength),
            "evidence_count": max(int(old.get("evidence_count") or 0), int(lead.get("evidence_count") or 1)),
        }
        if mark_notified:
            payload["last_notified_at"] = main.now_utc().isoformat()
        ref.set(payload, merge=True)
    except Exception as exc:
        print("NC_LEAD_PROFILE_WRITE_ERROR", exc)


def _recent_person_seen(db, lead):
    if not db:
        return False
    doc_id = _profile_doc_id(lead)
    if not doc_id:
        return False
    try:
        snap = db.collection(PROFILE_COLLECTION).document(doc_id).get()
        if not snap.exists:
            return False
        data = snap.to_dict() or {}
        notified = main.parse_dt(data.get("last_notified_at", ""))
        if notified is None:
            return False
        hours = max(24, min(24 * 60, int(os.getenv("NC_PERSON_DEDUPE_HOURS", "720"))))
        recent = notified >= main.now_utc() - timedelta(hours=hours)
        if recent:
            # Same person is not re-notified; stronger/newer evidence silently
            # updates the canonical lead profile instead.
            _update_profile(db, lead, mark_notified=False)
        return recent
    except Exception as exc:
        print("NC_PERSON_DEDUPE_READ_ERROR", exc)
        return False


def notified_before_with_content(db, lead):
    if _original_notified_before(db, lead):
        _update_profile(db, lead, mark_notified=False)
        return True
    if _recent_content_seen(db, lead):
        _update_profile(db, lead, mark_notified=False)
        return True
    return _recent_person_seen(db, lead)


def mark_notified_with_content(db, lead):
    _original_mark_notified(db, lead)
    if not db:
        return
    doc_id = _content_doc_id(lead)
    if doc_id:
        try:
            db.collection(base.NOTIFIED_COLLECTION).document(doc_id).set({
                "dedupe_type": "same_person_same_text",
                "content_fingerprint": doc_id.removeprefix("content_"),
                "url": lead.get("url", ""),
                "author": lead.get("author", ""),
                "telegram_user_id": lead.get("telegram_user_id", ""),
                "telegram_chat": lead.get("telegram_chat", ""),
                "classification": lead.get("classification", ""),
                "intent_class": lead.get("intent_class", ""),
                "notified_at": main.now_utc().isoformat(),
            }, merge=True)
        except Exception as exc:
            print("NC_CONTENT_DEDUPE_WRITE_ERROR", exc)
    _update_profile(db, lead, mark_notified=True)


base._notified_before = notified_before_with_content
base._mark_notified = mark_notified_with_content
