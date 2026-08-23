import hashlib
import os
from datetime import datetime, timezone

import youtube_radar as yr

_BASE_LOAD_WATCHLIST = yr.load_watchlist
_BASE_SCAN_COMMENTS = yr.scan_comments


def _parse(value):
    try:
        return yr._parse_dt(value)
    except Exception:
        return None


def _freshness_score(data):
    now = datetime.now(timezone.utc)
    score = 0.0
    for field, weight in (("last_lead_at", 90), ("last_comment_seen_at", 50), ("discovered_at", 15)):
        dt = _parse(data.get(field))
        if not dt:
            continue
        age_days = max(0.0, (now - dt).total_seconds() / 86400)
        score += weight / (1.0 + age_days)
    if data.get("last_lead_classification") == "HOT":
        score += 25
    elif data.get("last_lead_classification") == "WARM":
        score += 12
    return score


def load_watchlist_ranked():
    db = yr.main.firestore_client()
    if not db:
        return []
    limit = max(20, int(os.getenv("YOUTUBE_WATCHLIST_LIMIT", "160")))
    pool_limit = min(800, max(limit * 4, limit))
    pool = []
    try:
        for doc in db.collection(yr.WATCHLIST_COLLECTION).limit(pool_limit).stream():
            data = doc.to_dict() or {}
            if data.get("status") != "active" or data.get("market") != "north_cyprus" or not data.get("video_id"):
                continue
            pool.append(data)
    except Exception as exc:
        print("YOUTUBE_WATCHLIST_RANK_ERROR", exc)
        return _BASE_LOAD_WATCHLIST()

    if len(pool) <= limit:
        pool.sort(key=_freshness_score, reverse=True)
        print(f"YOUTUBE_WATCHLIST_RANKED pool={len(pool)} selected={len(pool)}")
        return pool

    ranked = sorted(pool, key=_freshness_score, reverse=True)
    priority_count = max(1, int(limit * 0.80))
    priority = ranked[:priority_count]
    remainder = ranked[priority_count:]

    # Preserve exploration so new/quiet evergreen videos are never permanently starved.
    explore_count = limit - len(priority)
    now = datetime.now(timezone.utc)
    if remainder and explore_count > 0:
        slot = now.timetuple().tm_yday * 8 + now.hour // 3
        start = (slot * explore_count) % len(remainder)
        exploration = [remainder[(start + i) % len(remainder)] for i in range(min(explore_count, len(remainder)))]
    else:
        exploration = []
    selected = priority + exploration
    print(f"YOUTUBE_WATCHLIST_RANKED pool={len(pool)} priority={len(priority)} explore={len(exploration)} selected={len(selected)}")
    return selected


def _comment_item(comment, video, uploader_channel_id):
    snippet = comment.get("snippet") or {}
    published = _parse(snippet.get("publishedAt"))
    if not published:
        return None
    author_channel = ((snippet.get("authorChannelId") or {}).get("value") or "")
    if uploader_channel_id and author_channel == uploader_channel_id:
        return None
    comment_id = str(comment.get("id") or "")
    text = str(snippet.get("textDisplay") or "").strip()
    if not comment_id or not text:
        return None
    return {
        "comment_id": comment_id,
        "video_id": video.get("video_id"),
        "video_title": video.get("title", ""),
        "channel_title": video.get("channel_title", ""),
        "text": text,
        "author": str(snippet.get("authorDisplayName") or ""),
        "author_channel_id": author_channel,
        "published": published.isoformat(),
        "updated": str(snippet.get("updatedAt") or ""),
        "url": f"https://www.youtube.com/watch?v={video.get('video_id')}&lc={comment_id}",
        "source": "YouTube Comment",
    }


def _all_replies(parent_id, video, uploader_channel_id, cutoff, max_pages):
    token = None
    for _ in range(max_pages):
        params = {
            "part": "snippet",
            "parentId": parent_id,
            "maxResults": 100,
            "textFormat": "plainText",
        }
        if token:
            params["pageToken"] = token
        data = yr._get("comments", params)
        if not data:
            return
        for comment in data.get("items", []):
            item = _comment_item(comment, video, uploader_channel_id)
            if not item:
                continue
            published = _parse(item.get("published"))
            if published and published >= cutoff:
                yield item
        token = data.get("nextPageToken")
        if not token:
            return


def iter_comments_expanded(video, cutoff):
    """Scan top-level comments plus every reply for selected threads.

    YouTube's commentThreads response can contain only a subset of replies. When
    totalReplyCount is larger than the embedded reply list, comments.list(parentId)
    is used to retrieve the missing replies. Calls are capped per video.
    """
    video_id = video.get("video_id")
    pages = max(1, min(3, int(os.getenv("YOUTUBE_COMMENT_PAGES", "1"))))
    reply_thread_limit = max(0, min(20, int(os.getenv("YOUTUBE_FULL_REPLY_THREADS_PER_VIDEO", "6"))))
    reply_pages = max(1, min(3, int(os.getenv("YOUTUBE_FULL_REPLY_PAGES", "2"))))
    scan_old_thread_replies = os.getenv("YOUTUBE_SCAN_OLD_THREAD_REPLIES", "1").strip() == "1"
    uploader_channel_id = str(video.get("channel_id") or "")
    page_token = None
    seen = set()
    extra_reply_threads = 0
    recent_seen = []

    for _ in range(pages):
        params = {
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 100,
            "order": "time",
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token
        data = yr._get("commentThreads", params)
        if not data:
            break

        oldest_top = None
        for thread in data.get("items", []):
            thread_snippet = thread.get("snippet") or {}
            top = (thread_snippet.get("topLevelComment") or {})
            top_id = str(top.get("id") or "")
            top_item = _comment_item(top, video, uploader_channel_id)
            if top_item:
                top_dt = _parse(top_item.get("published"))
                oldest_top = top_dt if top_dt and (oldest_top is None or top_dt < oldest_top) else oldest_top
                if top_dt and top_dt >= cutoff and top_item["comment_id"] not in seen:
                    seen.add(top_item["comment_id"])
                    recent_seen.append(top_dt)
                    yield top_item

            embedded = ((thread.get("replies") or {}).get("comments") or [])
            for comment in embedded:
                item = _comment_item(comment, video, uploader_channel_id)
                if not item or item["comment_id"] in seen:
                    continue
                seen.add(item["comment_id"])
                published = _parse(item.get("published"))
                if published and published >= cutoff:
                    recent_seen.append(published)
                    yield item

            total_replies = int(thread_snippet.get("totalReplyCount") or 0)
            if top_id and total_replies > len(embedded) and extra_reply_threads < reply_thread_limit:
                extra_reply_threads += 1
                for item in _all_replies(top_id, video, uploader_channel_id, cutoff, reply_pages):
                    if item["comment_id"] in seen:
                        continue
                    seen.add(item["comment_id"])
                    published = _parse(item.get("published"))
                    if published:
                        recent_seen.append(published)
                    yield item

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        # If old-thread reply recovery is enabled, do not stop solely because top
        # comments are old: an older top-level thread may have a brand-new reply.
        if not scan_old_thread_replies and oldest_top and oldest_top < cutoff:
            break

    if recent_seen:
        latest = max(recent_seen)
        db = yr.main.firestore_client()
        if db and video_id:
            try:
                db.collection(yr.WATCHLIST_COLLECTION).document(video_id).set({
                    "last_comment_seen_at": latest.isoformat(),
                    "last_comment_scan_at": yr._now().isoformat(),
                }, merge=True)
            except Exception as exc:
                print("YOUTUBE_ACTIVITY_WRITE_ERROR", video_id, exc)
    if extra_reply_threads:
        print(f"YOUTUBE_FULL_REPLIES video={video_id} expanded_threads={extra_reply_threads} unique_comments={len(seen)}")


def scan_comments_expanded():
    leads = _BASE_SCAN_COMMENTS()
    # Base notifier shows only the first 12. Mark every accepted lead as notified
    # so lead #13+ does not repeat on the next pulse.
    db = yr.main.firestore_client()
    now = yr._now().isoformat()
    touched = {}
    for lead in leads or []:
        try:
            yr._mark_notified(db, lead)
        except Exception:
            pass
        video_id = str(lead.get("video_id") or "")
        if video_id:
            current = touched.get(video_id)
            rank = {"POTENTIAL": 1, "WARM": 2, "HOT": 3}
            if current is None or rank.get(lead.get("classification"), 0) > rank.get(current, 0):
                touched[video_id] = lead.get("classification", "")
    if db:
        for video_id, label in touched.items():
            try:
                db.collection(yr.WATCHLIST_COLLECTION).document(video_id).set({
                    "last_lead_at": now,
                    "last_lead_classification": label,
                }, merge=True)
            except Exception as exc:
                print("YOUTUBE_LEAD_ACTIVITY_WRITE_ERROR", video_id, exc)
    return leads


yr.load_watchlist = load_watchlist_ranked
yr._iter_comments = iter_comments_expanded
yr.scan_comments = scan_comments_expanded
