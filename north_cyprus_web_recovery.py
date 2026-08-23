import hashlib
import json
import os
from datetime import timedelta

import main
import north_cyprus_catcher as catcher
import north_cyprus_catcher_expanded  # applies expanded domains/intent patterns
import north_cyprus_open_web_plus as open_web

COLLECTION = "bay_s_nc_web_recovery_notified"
SCAN_COLLECTION = "bay_s_nc_web_recovery_scans"


def _key(lead):
    return hashlib.sha1((lead.get("url") or main.dedupe_key(lead)).encode("utf-8")).hexdigest()


def _seen(db, lead):
    if not db:
        return False
    key = _key(lead)
    try:
        # Never resend a lead already surfaced by the live Catcher.
        if db.collection(catcher.NOTIFIED_COLLECTION).document(key).get().exists:
            return True
        if db.collection("bay_s_nc_recovery_notified").document(key).get().exists:
            return True
        return db.collection(COLLECTION).document(key).get().exists
    except Exception as exc:
        print("NC_WEB_RECOVERY_DEDUPE_ERROR", exc)
        return False


def _mark(db, lead, days):
    if not db:
        return
    try:
        db.collection(COLLECTION).document(_key(lead)).set({
            "url": lead.get("url", ""),
            "author": lead.get("author", ""),
            "classification": lead.get("classification", ""),
            "days": days,
            "notified_at": main.now_utc().isoformat(),
        }, merge=True)
    except Exception as exc:
        print("NC_WEB_RECOVERY_MARK_ERROR", exc)


def run():
    days = max(30, min(180, int(os.getenv("NC_WEB_RECOVERY_DAYS", "90"))))
    started = main.now_utc()
    cutoff = started - timedelta(days=days)

    # Full mode = all configured Reddit language feeds, more Bing intent queries,
    # and replay of dynamically discovered public communities. Still zero Exa.
    os.environ["NC_OPEN_WEB_ENABLED"] = "1"
    os.environ["NC_OPEN_WEB_MODE"] = "full"
    os.environ.setdefault("NC_REDDIT_RSS_FEED_LIMIT", "16")
    os.environ.setdefault("NC_BING_RSS_QUERY_LIMIT", "20")
    os.environ.setdefault("NC_DYNAMIC_COMMUNITY_LIMIT", "40")

    raw = open_web.collect_open_web()
    accepted = []
    stats = {}
    seen_urls = set()

    for item in raw:
        key = item.get("url") or main.dedupe_key(item)
        if key in seen_urls:
            continue
        seen_urls.add(key)
        lead, reason = catcher._classify(item, cutoff)
        stats[reason] = stats.get(reason, 0) + 1
        if not lead:
            continue
        published = main.parse_dt(lead.get("published", ""))
        lead["web_recovery_days"] = days
        lead["recovery_age_days"] = round((started - published).total_seconds() / 86400, 1) if published else None
        accepted.append(lead)

    rank = {"HOT": 3, "WARM": 2, "POTENTIAL": 1}
    accepted.sort(key=lambda x: (rank.get(x.get("classification"), 0), x.get("intent_score", 0), x.get("credibility_score", 0)), reverse=True)

    db = main.firestore_client()
    new = []
    for lead in accepted:
        if _seen(db, lead):
            continue
        new.append(lead)
        _mark(db, lead, days)

    if db:
        try:
            db.collection(SCAN_COLLECTION).document(started.strftime("%Y%m%d%H%M%S")).set({
                "started_at": started.isoformat(),
                "finished_at": main.now_utc().isoformat(),
                "days": days,
                "raw": len(raw),
                "accepted": len(accepted),
                "new": len(new),
                "stats": stats,
            }, merge=True)
        except Exception as exc:
            print("NC_WEB_RECOVERY_FIRESTORE_ERROR", exc)

    print("NC_WEB_RECOVERY_COMPLETE", json.dumps({"days": days, "raw": len(raw), "accepted": len(accepted), "new": len(new), "stats": stats}, ensure_ascii=False))

    if new:
        lines = [f"🌐 BAY-S NC WEB RECOVERY {days}G | {len(new)} ADAY"]
        for lead in new[:12]:
            age = lead.get("recovery_age_days")
            excerpt = " ".join(str(lead.get("text", "")).split())[:250]
            lines.append(
                f"\n{lead.get('classification','POTENTIAL')} | {lead.get('author') or 'kullanıcı'} | {age}g önce\n"
                f"{str(lead.get('title') or lead.get('source') or '')[:90]}\n{excerpt}\n{lead.get('url','')}"
            )
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(f"🌐 BAY-S NC WEB RECOVERY {days}G tamamlandı.\nYeni aday yok.\nİncelenen: {len(seen_urls)}")


if __name__ == "__main__":
    run()
