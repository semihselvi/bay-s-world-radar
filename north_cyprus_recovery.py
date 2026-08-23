import hashlib
import json
import os
from datetime import timedelta

import main
import north_cyprus_catcher as base
import north_cyprus_catcher_expanded  # patches base.collect_global_telegram with expanded sources
from north_cyprus_conversation import stitch_conversations

RECOVERY_NOTIFIED = "bay_s_nc_recovery_notified"
RECOVERY_SCANS = "bay_s_nc_recovery_scans"


def _doc_key(lead):
    return hashlib.sha1((lead.get("url") or main.dedupe_key(lead)).encode("utf-8")).hexdigest()


def _already_seen(db, lead):
    if not db:
        return False
    key = _doc_key(lead)
    try:
        # Do not resend something the live Catcher already surfaced.
        if db.collection(base.NOTIFIED_COLLECTION).document(key).get().exists:
            return True
        return db.collection(RECOVERY_NOTIFIED).document(key).get().exists
    except Exception as exc:
        print("NC_RECOVERY_DEDUPE_ERROR", exc)
        return False


def _mark(db, lead, days):
    if not db:
        return
    try:
        db.collection(RECOVERY_NOTIFIED).document(_doc_key(lead)).set({
            "url": lead.get("url", ""),
            "author": lead.get("author", ""),
            "classification": lead.get("classification", ""),
            "recovery_days": days,
            "notified_at": main.now_utc().isoformat(),
        }, merge=True)
    except Exception as exc:
        print("NC_RECOVERY_MARK_ERROR", exc)


def run():
    days = max(1, min(30, int(os.getenv("NC_RECOVERY_DAYS", "7"))))
    started = main.now_utc()
    cutoff = started - timedelta(days=days)

    # Keep all collectors on the same recovery horizon.
    os.environ["WORLD_LOOKBACK_HOURS"] = str(days * 24)
    global_items = base.collect_global_telegram()
    forum_items = base.collect_forum_replies(cutoff)
    originals = global_items + forum_items
    stitched = stitch_conversations(originals, max_gap_hours=24 if days >= 30 else 12)
    raw_items = originals + stitched

    accepted = []
    stats = {}
    seen = set()
    for item in raw_items:
        key = ("stitch|" + main.dedupe_key(item)) if item.get("conversation_stitched") else (item.get("url") or main.dedupe_key(item))
        if key in seen:
            continue
        seen.add(key)
        lead, reason = base._classify(item, cutoff)
        stats[reason] = stats.get(reason, 0) + 1
        if not lead:
            continue
        published = main.parse_dt(lead.get("published", ""))
        age_days = round((started - published).total_seconds() / 86400, 1) if published else None
        lead["recovery_days"] = days
        lead["recovery_age_days"] = age_days
        accepted.append(lead)

    rank = {"HOT": 3, "WARM": 2, "POTENTIAL": 1}
    accepted.sort(key=lambda x: (rank.get(x.get("classification"), 0), x.get("intent_score", 0), x.get("credibility_score", 0)), reverse=True)

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
                "accepted": len(accepted),
                "new": len(new),
                "stats": stats,
            }, merge=True)
        except Exception as exc:
            print("NC_RECOVERY_FIRESTORE_ERROR", exc)

    print("NC_RECOVERY_COMPLETE", json.dumps({"days": days, "raw": len(raw_items), "stitched": len(stitched), "accepted": len(accepted), "new": len(new), "stats": stats}, ensure_ascii=False))

    if new:
        lines = [f"🕰 BAY-S NC RECOVERY {days}G | {len(new)} ESKİ AMA AKTİF ADAY"]
        for lead in new[:12]:
            author = lead.get("author") or "kullanıcı"
            place = lead.get("telegram_chat") or lead.get("title") or lead.get("source") or ""
            age = lead.get("recovery_age_days")
            excerpt = " ".join(str(lead.get("text", "")).split())[:240]
            lines.append(f"\n{lead.get('classification','POTENTIAL')} | {author} | {place[:70]} | {age}g önce\n{excerpt}\n{lead.get('url','')}")
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(f"🕰 BAY-S NC RECOVERY {days}G tamamlandı.\nYeni recovery adayı yok.\nİncelenen: {len(seen)} | Stitch: {len(stitched)}")


if __name__ == "__main__":
    run()
