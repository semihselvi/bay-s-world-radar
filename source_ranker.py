import hashlib
from collections import defaultdict
from datetime import timedelta

import main

PERFORMANCE_COLLECTION = "bay_s_source_performance"


def _key(name):
    return hashlib.sha1(name.encode("utf-8")).hexdigest()


def run(days=7):
    db = main.firestore_client()
    if not db:
        print("SOURCE_RANKER_DISABLED missing Firestore")
        return

    since = main.now_utc() - timedelta(days=days)
    stats = defaultdict(lambda: {
        "scanned": 0,
        "lead_count": 0,
        "hot": 0,
        "warm": 0,
        "last_lead_at": "",
    })

    scans = (
        db.collection(main.SCAN_LOG_COLLECTION)
        .where("started_at", ">=", since.isoformat())
        .limit(250)
        .stream()
    )

    scan_count = 0
    for scan in scans:
        scan_count += 1
        data = scan.to_dict() or {}
        for source_name, count in (data.get("direct_counts") or {}).items():
            try:
                stats[str(source_name)]["scanned"] += int(count or 0)
            except Exception:
                pass

        try:
            for lead_doc in scan.reference.collection("leads").stream():
                lead = lead_doc.to_dict() or {}
                source_name = lead.get("telegram_chat") or lead.get("source") or lead.get("source_domain") or "unknown"
                s = stats[str(source_name)]
                s["lead_count"] += 1
                classification = str(lead.get("classification", "")).upper()
                if classification == "HOT":
                    s["hot"] += 1
                elif classification == "WARM":
                    s["warm"] += 1
                scanned_at = str(lead.get("scanned_at", ""))
                if scanned_at and scanned_at > s["last_lead_at"]:
                    s["last_lead_at"] = scanned_at
        except Exception as exc:
            print("SOURCE_RANKER_LEADS_ERROR", scan.id, exc)

    ranked = []
    batch = db.batch()
    now = main.now_utc().isoformat()
    for source_name, s in stats.items():
        # Lead production matters far more than raw volume.
        score = s["hot"] * 10 + s["warm"] * 5 + s["lead_count"] * 2
        if s["scanned"]:
            score += min(3.0, (s["lead_count"] / max(1, s["scanned"])) * 100)
        score = round(score, 2)
        row = {
            "source": source_name,
            "period_days": days,
            "scanned": s["scanned"],
            "lead_count": s["lead_count"],
            "hot": s["hot"],
            "warm": s["warm"],
            "score": score,
            "last_lead_at": s["last_lead_at"],
            "updated_at": now,
        }
        batch.set(db.collection(PERFORMANCE_COLLECTION).document(_key(source_name)), row, merge=True)
        ranked.append(row)

    if ranked:
        batch.commit()

    ranked.sort(key=lambda x: (x["score"], x["hot"], x["warm"], x["lead_count"]), reverse=True)
    print(f"SOURCE_RANKER_COMPLETE scans={scan_count} sources={len(ranked)}")

    top = [x for x in ranked if x["lead_count"] > 0][:10]
    if top:
        lines = [f"📊 BAY-S RADAR | Son {days} gün kaynak performansı"]
        for i, row in enumerate(top, 1):
            lines.append(
                f"{i}. {row['source'][:60]} | Puan {row['score']} | HOT {row['hot']} | WARM {row['warm']} | Lead {row['lead_count']}"
            )
        main.notify_telegram("\n".join(lines))


if __name__ == "__main__":
    run()
