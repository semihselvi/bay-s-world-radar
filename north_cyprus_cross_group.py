from datetime import timedelta

import main
import north_cyprus_focus as nf


def identity_key(item):
    """Return a stable Telegram person key when available.

    Numeric Telegram user ids are preferred because usernames can change and
    display names are not safe cross-group identifiers. Public @usernames are a
    fallback for older collector rows that do not yet carry telegram_user_id.
    """
    user_id = str(item.get("telegram_user_id") or "").strip()
    if user_id and user_id.isdigit() and user_id != "0":
        return f"telegram_user:{user_id}"
    author = " ".join(str(item.get("author") or "").strip().casefold().split())
    if author.startswith("@") and len(author) > 2:
        return f"telegram_username:{author}"
    return ""


def _chat_key(item):
    chat_id = str(item.get("telegram_chat_id") or "").strip()
    if chat_id and chat_id != "0":
        return f"id:{chat_id}"
    chat = " ".join(str(item.get("telegram_chat") or "").strip().casefold().split())
    return f"name:{chat}" if chat else ""


def _buyer_like(text):
    return bool(
        nf._matches(text, nf.STRONG_BUYER_PATTERNS)
        or nf._matches(text, nf.REQUEST_BUYER_PATTERNS)
        or nf._matches(text, nf.EARLY_BUYER_PATTERNS)
    )


def stitch_cross_group_identity(items, max_gap_hours=72, max_parts=8):
    """Combine signals from the same Telegram user across different groups.

    Example: one group contains "Long Beach düşünüyorum", another "budget £100k",
    and a third "2+1 sahibinden var mı?". No single message has to carry the full
    buying story. A synthetic item is emitted only when at least two distinct
    chats are involved, which keeps ordinary same-thread conversation stitching
    separate from this layer.
    """
    groups = {}
    for item in items:
        ident = identity_key(item)
        chat = _chat_key(item)
        published = main.parse_dt(item.get("published", ""))
        if not ident or not chat or not published:
            continue
        groups.setdefault(ident, []).append((published, chat, item))

    out = []
    gap = timedelta(hours=max(6, min(int(max_gap_hours), 24 * 14)))
    for ident, entries in groups.items():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda x: x[0])
        latest_dt = entries[-1][0]
        window = [row for row in entries if latest_dt - row[0] <= gap]
        chats = {row[1] for row in window}
        if len(window) < 2 or len(chats) < 2:
            continue

        chunk = window[-max(2, int(max_parts)):]
        texts = []
        parts = []
        buyer_like_count = 0
        explicit_strong_count = 0
        concrete_count = 0
        property_count = 0
        suspected_agent = False
        for dt, chat, item in chunk:
            body = " ".join(str(item.get("text") or "").split())
            if not body:
                continue
            texts.append(body)
            if _buyer_like(body):
                buyer_like_count += 1
            if nf._matches(body, nf.STRONG_BUYER_PATTERNS):
                explicit_strong_count += 1
            if nf._matches(body, nf.CONCRETE_PATTERNS):
                concrete_count += 1
            if nf._matches(body, nf.PROPERTY_PATTERNS):
                property_count += 1
            suspected_agent = suspected_agent or bool(item.get("suspected_agent"))
            parts.append({
                "url": item.get("url", ""),
                "published": dt.isoformat(),
                "telegram_chat": item.get("telegram_chat", ""),
                "text": body[:700],
            })

        if len(texts) < 2:
            continue
        combined = " | ".join(texts)
        # Do not create arbitrary person profiles from unrelated chat traffic.
        # Require genuine buyer/request language, or a concrete property pattern
        # split across messages.
        if buyer_like_count < 1 and not (concrete_count >= 1 and property_count >= 1):
            continue

        latest = chunk[-1][2]
        distinct_chats = []
        seen_chats = set()
        for _, _, item in chunk:
            label = str(item.get("telegram_chat") or "").strip()
            key = label.casefold()
            if label and key not in seen_chats:
                seen_chats.add(key)
                distinct_chats.append(label)

        repeated = buyer_like_count >= 2 and len(distinct_chats) >= 2
        synthetic = dict(latest)
        synthetic.update({
            "source": "Cross-Group Buyer Profile",
            "title": "Cross-Group Buyer Profile | " + (latest.get("author") or ident),
            "text": combined[:7000],
            "published": latest_dt.isoformat(),
            "source_bucket": "north_cyprus_cross_group_identity",
            # Use a dedicated synthetic chat name so the normal same-chat stitcher
            # does not stitch this profile back into the original chat messages.
            "telegram_chat": "Cross-Group Buyer Profile",
            "conversation_cross_group": True,
            "cross_group_identity": ident,
            "cross_group_chats": distinct_chats[:12],
            "cross_group_parts": parts,
            "repeated_demand": repeated,
            "repeated_demand_count": buyer_like_count,
            "cross_group_strong_count": explicit_strong_count,
            "suspected_agent": suspected_agent,
        })
        out.append(synthetic)

    print(f"NC_CROSS_GROUP_IDENTITY raw={len(items)} profiles={len(out)} repeated={sum(1 for x in out if x.get('repeated_demand'))}")
    return out
