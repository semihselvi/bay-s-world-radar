import atexit
import hashlib
import math
import os
from datetime import datetime, timezone

import main

COLLECTION = "bay_s_nc_query_performance"
_OBS = {}
_FLUSHED = False


def _norm(value):
    return " ".join(str(value or "").strip().lower().split())


def _doc_id(query):
    return hashlib.sha1(_norm(query).encode("utf-8")).hexdigest()


def _queries_of(item):
    values = item.get("telegram_queries")
    if isinstance(values, (list, tuple, set)):
        raw = list(values)
    else:
        raw = [item.get("telegram_query")]
    out=[]; seen=set()
    for value in raw:
        query=str(value or "").strip()
        key=_norm(query)
        if not query or query=="public_group_discovery" or key in seen:
            continue
        seen.add(key); out.append(query)
    return out


def observe(item, lead, reason):
    if os.getenv("NC_QUERY_LEARNING", os.getenv("NC_SOURCE_LEARNING", "1")).strip() != "1":
        return
    for query in _queries_of(item):
        key = _norm(query)
        row = _OBS.setdefault(key, {
            "query": query,
            "messages": 0,
            "accepted": 0,
            "hot": 0,
            "warm": 0,
            "potential": 0,
            "promo": 0,
            "rental": 0,
            "no_intent": 0,
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
    lead_value = hot * 38 + warm * 17 + potential * 6 + accepted * 2
    yield_score = lead_value * 10.0 / math.sqrt(messages + 18)
    exploration_value = min(7.0, math.log1p(messages) * 1.2)
    promo_penalty = min(15.0, promo * 10.0 / (messages + 8))
    recency = 0.0
    last = _parse(data.get("last_lead_at"))
    if last:
        age_days = max(0.0, (datetime.now(timezone.utc) - last).total_seconds() / 86400)
        if age_days <= 2: recency = 20.0
        elif age_days <= 7: recency = 12.0
        elif age_days <= 30: recency = 5.0
    return round(yield_score + exploration_value + recency - promo_penalty, 3)


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
            old = ref.get().to_dict() or {}
            merged = dict(old)
            for field in ("messages", "accepted", "hot", "warm", "potential", "promo", "rental", "no_intent"):
                merged[field] = int(old.get(field, 0) or 0) + int(delta.get(field, 0) or 0)
            merged["query"] = delta.get("query") or old.get("query") or key
            if delta.get("last_lead_at"):
                merged["last_lead_at"] = delta["last_lead_at"]
            merged["last_scanned_at"] = now
            merged["priority_score"] = score_doc(merged)
            ref.set(merged, merge=True)
        print(f"NC_QUERY_PERFORMANCE_FLUSH queries={len(_OBS)}")
    except Exception as exc:
        print("NC_QUERY_PERFORMANCE_FLUSH_ERROR", exc)


def _scores():
    db = main.firestore_client()
    out = {}
    if not db:
        return out
    try:
        for doc in db.collection(COLLECTION).limit(400).stream():
            data = doc.to_dict() or {}
            query = _norm(data.get("query"))
            if query:
                out[query] = float(data.get("priority_score", score_doc(data)) or 0)
    except Exception as exc:
        print("NC_QUERY_PERFORMANCE_LOAD_ERROR", exc)
    return out


def _rotate(values, count):
    if not values or count <= 0:
        return []
    count=min(count,len(values)); now=datetime.now(timezone.utc); slot=now.timetuple().tm_yday*8+now.hour//3
    start=(slot*count)%len(values)
    return [values[(start+i)%len(values)] for i in range(count)]


def ranked_queries(queries, limit, core=None, exploration_ratio=0.30):
    """Rank queries by real lead yield while reserving slots for discovery."""
    unique=[]; seen=set()
    for value in queries:
        q=str(value or "").strip(); key=_norm(q)
        if not q or key in seen: continue
        seen.add(key); unique.append(q)
    limit=max(1,min(int(limit),len(unique))) if unique else 0
    if not unique or limit<=0: return []

    scores=_scores(); core_list=[]; core_keys=set()
    for value in core or []:
        key=_norm(value)
        if key in seen and key not in core_keys:
            core_keys.add(key); core_list.append(next(q for q in unique if _norm(q)==key))
    if len(core_list)>=limit: return core_list[:limit]

    candidates=[q for q in unique if _norm(q) not in core_keys]; remaining=limit-len(core_list)
    positive=[q for q in candidates if scores.get(_norm(q),0.0)>0]

    # Cold start: do not accidentally make alphabetic order the permanent winner.
    # Rotate the entire untested pool until actual buyer-yield evidence exists.
    if not positive:
        result=core_list+_rotate(candidates,remaining)
        print("NC_QUERY_PRIORITY cold_start " + ", ".join(result[:12]))
        return result

    explore=max(1,int(round(remaining*exploration_ratio))) if remaining>=3 else 1 if remaining else 0
    exploit=max(0,remaining-explore)
    ranked=sorted(candidates,key=lambda q:(scores.get(_norm(q),0.0),_norm(q)),reverse=True)
    chosen=ranked[:exploit]; rest=[q for q in candidates if q not in chosen]
    chosen.extend(_rotate(rest,explore))
    if len(chosen)<remaining:
        for q in ranked:
            if q not in chosen: chosen.append(q)
            if len(chosen)>=remaining: break
    result=core_list+chosen[:remaining]
    print("NC_QUERY_PRIORITY " + ", ".join(f"{q}={scores.get(_norm(q),0):.1f}" for q in result[:12]))
    return result


atexit.register(flush)
