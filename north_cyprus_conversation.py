from datetime import timedelta

import main


def _chat_key(item):
    return str(item.get("telegram_chat") or item.get("title") or item.get("source") or "").strip().lower()


def _author_key(item):
    return str(item.get("author") or "").strip().lower()


def stitch_conversations(items, max_gap_hours=6, max_parts=6):
    """Combine nearby messages by the same human in the same discussion.

    This rescues fragmented intent such as: "moving in October" -> "budget £90k" ->
    "1+1 in Long Beach" where no single message is strong enough by itself.
    """
    groups = {}
    for item in items:
        author = _author_key(item)
        chat = _chat_key(item)
        published = main.parse_dt(item.get("published", ""))
        if not author or not chat or not published:
            continue
        # Channel/bot-like authors are not useful for person-level stitching.
        if author.startswith("@") and author == str(item.get("telegram_parent_channel") or "").strip().lower():
            continue
        groups.setdefault((author, chat), []).append((published, item))

    stitched = []
    gap = timedelta(hours=max_gap_hours)
    for (_, _), entries in groups.items():
        entries.sort(key=lambda x: x[0])
        cluster = []
        previous = None
        for published, item in entries:
            if previous is None or published - previous <= gap:
                cluster.append((published, item))
            else:
                stitched.extend(_cluster_to_items(cluster, max_parts))
                cluster = [(published, item)]
            previous = published
        stitched.extend(_cluster_to_items(cluster, max_parts))

    print(f"NC_CONVERSATION_STITCH raw={len(items)} synthetic={len(stitched)}")
    return stitched


def _cluster_to_items(cluster, max_parts):
    if len(cluster) < 2:
        return []
    # Sliding chunks allow a long conversation to produce more than one useful
    # aggregate while keeping the synthetic item bounded.
    out = []
    for start in range(0, len(cluster), max_parts):
        chunk = cluster[start:start + max_parts]
        if len(chunk) < 2:
            continue
        latest_dt, latest = chunk[-1]
        parts = []
        text_parts = []
        reply_parts = []
        seen_texts = set()
        for dt, item in chunk:
            body = " ".join(str(item.get("text", "")).split())
            body_key = body.casefold()
            if body and body_key not in seen_texts:
                seen_texts.add(body_key)
                text_parts.append(body)
                parts.append({
                    "url": item.get("url", ""),
                    "published": dt.isoformat(),
                    "text": body[:700],
                })
            reply = " ".join(str(item.get("reply_context", "")).split())
            if reply and reply not in reply_parts:
                reply_parts.append(reply)
        # Two copies of the same message are not a conversation. This prevents
        # collector duplicates from creating a synthetic stitched lead.
        if len(text_parts) < 2:
            continue
        synthetic = dict(latest)
        synthetic.update({
            "source": "Conversation Stitch",
            "title": f"Conversation Stitch | {latest.get('telegram_chat') or latest.get('title') or latest.get('source') or ''}",
            "text": " | ".join(text_parts)[:7000],
            "published": latest_dt.isoformat(),
            "source_bucket": "north_cyprus_conversation_stitch",
            "conversation_stitched": True,
            "conversation_parts": parts,
            "reply_context": " | ".join(reply_parts)[:1800],
        })
        out.append(synthetic)
    return out
