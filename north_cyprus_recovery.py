import hashlib
import json
import os
from datetime import timedelta

import main
import north_cyprus_catcher as base
import north_cyprus_catcher_expanded  # patches base.collect_global_telegram and direction-first classifier
from north_cyprus_conversation import stitch_conversations
from north_cyprus_intent_classifier import display_intent
from north_cyprus_notification_dedupe import content_fingerprint
from north_cyprus_semantic_dedupe import semantic_dedupe_items, consolidate_buyer_leads

RECOVERY_NOTIFIED = "bay_s_nc_recovery_notified"
RECOVERY_SCANS = "bay_s_nc_recovery_scans"


def _doc_key(lead):
    return hashlib.sha1((lead.get("url") or main.dedupe_key(lead)).encode("utf-8")).hexdigest()


def _recovery_keys(lead):
    keys = [_doc_key(lead)]
    fp = content_fingerprint(lead)
    if fp:
        keys.append(f"content_{fp}")
    return keys


def _already_seen(db, lead):
    if not db:
        return False
    try:
        # base._notified_before is now person-aware. This prevents Recovery 7G/30G
        # from re-alerting a person already surfaced by the live Buyer Catcher.
        if base._notified_before(db, lead):
            return True
        for key in _recovery_keys(lead):
            if db.collection(RECOVERY_NOTIFIED).document(key).get().exists:
                return True
        return False
    except Exception as exc:
        print("NC_RECOVERY_DEDUPE_ERROR", exc)
        return False


def _mark(db, lead, days):
    if not db:
        return
    try:
        payload = {
            "url": lead.get("url", ""),
            "author": lead.get("author", ""),
            "classification": lead.get("classification", ""),
            "intent_class": lead.get("intent_class", ""),
            "intent_subtypes": lead.get("intent_subtypes") or [],
            "recovery_days": days,
            "notified_at": main.now_utc().isoformat(),
        }
        for key in _recovery_keys(lead):
            db.collection(RECOVERY_NOTIFIED).document(key).set(payload, merge=True)
        # Mark the shared canonical profile too, so the live Catcher cannot alert
        # the same person again merely because it sees a newer Telegram URL.
        base._mark_notified(db, lead)
    except Exception as exc:
        print("NC_RECOVERY_MARK_ERROR", exc)


def run():
    days = max(1, min(30, int(os.getenv("NC_RECOVERY_DAYS", "7"))))
    started = main.now_utc()
    cutoff = started - timedelta(days=days)

    os.environ["WORLD_LOOKBACK_HOURS"] = str(days * 24)
    global_items = base.collect_global_telegram()
    forum_items = base.collect_forum_replies(cutoff)
    originals = global_items + forum_items
    stitched = stitch_conversations(originals, max_gap_hours=24 if days >= 30 else 12)
    raw_items = semantic_dedupe_items(originals + stitched)

    accepted = []
    stats = {}
    seen = set()
    for item in raw_items:
        key = item.get("url") or main.dedupe_key(item)
        identity_hint = str(item.get("telegram_user_id") or item.get("author") or "")
        key = f"{identity_hint}|{key}" if item.get("conversation_stitched") else key
        if key in seen:
            continue
        seen.add(key)
        lead, reason = base._classify(item, cutoff)
        stats[reason] = stats.get(reason, 0) + 1
        if not lead or lead.get("intent_class") not in {"BUYER", "TENANT"}:
            continue
        published = main.parse_dt(lead.get("published", ""))
        age_days = round((started - published).total_seconds() / 86400, 1) if published else None
        lead["recovery_days"] = days
        lead["recovery_age_days"] = age_days
        accepted.append(lead)

    accepted = consolidate_buyer_leads(accepted)
    rank = {"HOT": 3, "WARM": 2}
    accepted.sort(key=lambda x: (rank.get(x.get("classification"), 0), int(x.get("intent_confidence") or x.get("intent_score") or 0), x.get("credibility_score", 0)), reverse=True)

    db = main.firestore_client()
    new = []
    for lead in accepted:
        if _already_seen(db, lead):
            continue
        new.append(lead)
        _mark(db, lead, days)

    if db:
        try:
            scan_id = f"{started.strftime('%Y%m%d%H%M%S')}_{days}d"
            db.collection(RECOVERY_SCANS).document(scan_id).set({
                "started_at": started.isoformat(),
                "finished_at": main.now_utc().isoformat(),
                "days": days,
                "raw": len(raw_items),
                "conversation_stitches": len(stitched),
                "accepted_people": len(accepted),
                "new": len(new),
                "stats": stats,
            }, merge=True)
        except Exception as exc:
            print("NC_RECOVERY_FIRESTORE_ERROR", exc)

    print("NC_RECOVERY_COMPLETE", json.dumps({"days": days, "raw": len(raw_items), "stitched": len(stitched), "accepted_people": len(accepted), "new": len(new), "stats": stats}, ensure_ascii=False))

    if new:
        lines = [f"🕰 BAY-S NC RECOVERY {days}G | {len(new)} GERÇEK BUYER/TENANT"]
        for lead in new[:12]:
            author = lead.get("author") or "kullanıcı"
            place = lead.get("telegram_chat") or lead.get("title") or lead.get("source") or ""
            age = lead.get("recovery_age_days")
            excerpt = " ".join(str(lead.get("text", "")).split())[:240]
            intent_label = display_intent(lead)
            confidence = int(lead.get("intent_confidence") or lead.get("intent_score") or 0)
            lines.append(f"\n{lead.get('classification','WARM')} | {author} | {intent_label}\nIntent {confidence}% | {place[:65]} | {age}g önce\n{excerpt}\n{lead.get('url','')}")
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(f"🕰 BAY-S NC RECOVERY {days}G tamamlandı.\nYeni gerçek BUYER/TENANT yok.\nİncelenen: {len(seen)} | Stitch kanıtı: {len(stitched)}")


if __name__ == "__main__":
    run()
