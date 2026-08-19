import json
import hashlib
import fresh_runner
import main

captured = []
original_keep = main.keep_candidate


def capture_keep(item, cutoff):
    keep, reason = original_keep(item, cutoff)
    captured.append({
        "keep": keep,
        "reason": reason,
        "url": item.get("url", ""),
        "title": item.get("title", ""),
        "published": item.get("published", ""),
        "verified_published": item.get("verified_published", ""),
        "source_bucket": item.get("source_bucket", ""),
        "source_domain": main.domain_of(item.get("url", "")),
        "text": item.get("text", "")[:4000],
    })
    return keep, reason


main.keep_candidate = capture_keep
main.run()

# Persist raw candidate diagnostics for the scan that just completed.
db = main.firestore_client()
if db:
    scans = list(db.collection(main.SCAN_LOG_COLLECTION).order_by("started_at", direction=main.firestore.Query.DESCENDING).limit(1).stream())
    if scans:
        scan_ref = scans[0].reference
        batch = db.batch()
        for idx, item in enumerate(captured[:120]):
            basis = item.get("url") or f"{item.get('source_bucket')}|{item.get('title')}|{idx}"
            doc_id = hashlib.sha1(basis.encode("utf-8")).hexdigest()
            batch.set(scan_ref.collection("raw_candidates").document(doc_id), item, merge=True)
        batch.set(scan_ref, {
            "raw_candidate_count": len(captured),
            "raw_candidate_debug": True,
        }, merge=True)
        batch.commit()
        print(f"RAW_DEBUG_STORED={min(len(captured),120)}")

print(f"RAW_CAPTURED_TOTAL={len(captured)}")
print("RAW_REASON_COUNTS", json.dumps({
    reason: sum(1 for x in captured if x["reason"] == reason)
    for reason in sorted({x["reason"] for x in captured})
}, ensure_ascii=False))
