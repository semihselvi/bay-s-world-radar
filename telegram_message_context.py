async def reply_context(msg, max_chars=1400):
    """Return the text of the message this Telegram message replies to.

    Best-effort only. It never follows private 1:1 chats or joins anything; it simply
    asks Telethon for the parent of a message we already received from a group/chat.
    """
    if not msg or not getattr(msg, "reply_to_msg_id", None):
        return ""
    try:
        parent = await msg.get_reply_message()
    except Exception:
        return ""
    if not parent or not getattr(parent, "message", None):
        return ""
    text = " ".join(str(parent.message).split())
    return text[:max_chars]
