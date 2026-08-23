import hashlib
import os
import re

import main
import north_cyprus_focus as nf

COLLECTION = "bay_s_nc_author_reputation"

PROFESSIONAL_PATTERNS = [
    r"\brealtor\b", r"\breal estate agent\b", r"\bestate agent\b", r"\bproperty consultant\b",
    r"\breal estate consultant\b", r"\bproperty advisor\b", r"\bbroker\b", r"\bsales manager\b",
    r"\bemlak[çc][ıi]\b", r"\bemlak dan[ıi][şs]man", r"\bgayrimenkul dan[ıi][şs]man",
    r"\bsat[ıi][şs] dan[ıi][şs]man", r"\bportf[öo]y y[öo]netic",
    r"\bриелтор\b", r"\bриэлтор\b", r"\bагент по недвижимости\b", r"\bброкер по недвижимости\b",
    r"\bагентство недвижимости\b", r"\bменеджер по продажам недвижимости\b",
    r"\bimmobilienmakler\b", r"\bmakler\b", r"\bagent immobilier\b", r"\bcourtier immobilier\b",
]

CTA_PATTERNS = [
    r"\bcontact (?:me|us)\b", r"\bdm (?:me|us)\b", r"\bpm (?:me|us)\b", r"\bwhatsapp\b",
    r"\bcall (?:me|us)\b", r"\bbook a viewing\b", r"\bfor more (?:info|information|details)\b",
    r"\bileti[şs]im\b", r"\bdetayl[ıi] bilgi\b", r"\bula[şs][ıi]n\b",
    r"\bпишите (?:мне|в лс|в личку)\b", r"\bобращайтесь\b", r"\bдля подробностей\b",
]

LISTING_PATTERNS = [
    r"\bfor sale\b", r"\bavailable (?:unit|units|apartment|villa|property)\b", r"\bnew listing\b",
    r"\bstarting from\b", r"\bready to move\b", r"\boff[- ]plan\b",
    r"\bsat[ıi]l[ıi]k\b", r"\bportf[öo]y\b", r"\bteslime haz[ıi]r\b", r"\bf[ıi]rsat daire\b",
    r"\bпрода[её]тся\b", r"\bпродам\b", r"\bв продаже\b", r"\bновый объект\b", r"\bобъект на продажу\b",
]

PHONE_RE = re.compile(r"(?:\+?90|\+?357|\+?7)?[\s().-]*(?:5\d{2}|\d{3})[\s().-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}")


def _matches(text, patterns):
    return sum(1 for p in patterns if re.search(p, text or "", re.I))


def _author_key(item):
    author = " ".join(str(item.get("author") or "").strip().lower().split())
    chat = " ".join(str(item.get("telegram_chat") or "").strip().lower().split())
    if author.startswith("@") and len(author) > 2:
        return "telegram:" + author, True
    if author and chat:
        # Display names are only reliable inside the current scan/chat. Never use
        # them as a persistent cross-chat identity because names can collide.
        return f"ephemeral:{chat}|{author}", False
    return "", False


def _seller_evidence(item):
    text = str(item.get("text") or "")
    if not text:
        return 0, []
    evidence = []
    score = 0
    professional = _matches(text, PROFESSIONAL_PATTERNS)
    listing = _matches(text, LISTING_PATTERNS)
    cta = _matches(text, CTA_PATTERNS)
    seller_hits = sum(1 for phrase in nf.SELLER_PATTERNS if str(phrase).lower() in text.lower())
    property_signal = nf._matches(text, nf.PROPERTY_PATTERNS)
    has_phone = bool(PHONE_RE.search(text))

    if professional:
        score += 5
        evidence.append("professional_title")
    if listing >= 1 and (cta >= 1 or has_phone):
        score += 3
        evidence.append("listing_with_cta")
    elif listing >= 2:
        score += 2
        evidence.append("listing_language")
    if seller_hits >= 3:
        score += 3
        evidence.append("seller_phrase_cluster")
    elif seller_hits >= 2:
        score += 2
        evidence.append("seller_phrases")
    if property_signal and has_phone and cta:
        score += 2
        evidence.append("property_phone_cta")
    return score, evidence


def _buyer_like(item):
    text = str(item.get("text") or "")
    return bool(nf._matches(text, nf.STRONG_BUYER_PATTERNS) or nf._matches(text, nf.REQUEST_BUYER_PATTERNS))


def _doc_id(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def _load_persistent(keys):
    db = main.firestore_client()
    out = {}
    if not db:
        return out
    for key in keys:
        if not key.startswith("telegram:@"):
            continue
        try:
            snap = db.collection(COLLECTION).document(_doc_id(key)).get()
            if snap.exists:
                out[key] = snap.to_dict() or {}
        except Exception as exc:
            print("NC_AUTHOR_REPUTATION_READ_ERROR", key, exc)
    return out


def annotate_author_reputation(items):
    """Tag buyer-shaped posts from authors who behave like agents/sellers.

    A single wanted/buyer message is not enough to trust the persona. We inspect
    other messages by the same author in the same scan and persist only stable
    @usernames. This catches agents who write 'urgent, looking to buy...' while
    sourcing stock for clients, without globally blocking normal buyer wording.
    """
    if os.getenv("NC_AUTHOR_REPUTATION", "1").strip() != "1":
        return items

    groups = {}
    stable_keys = set()
    for item in items:
        key, stable = _author_key(item)
        if not key:
            continue
        groups.setdefault(key, []).append(item)
        if stable:
            stable_keys.add(key)

    persistent = _load_persistent(stable_keys)
    db = main.firestore_client()
    now = main.now_utc().isoformat()
    flagged = 0

    for key, rows in groups.items():
        current_seller = 0
        current_buyer = 0
        reasons = set()
        seller_messages = 0
        explicit_professional = False
        for row in rows:
            score, evidence = _seller_evidence(row)
            if score:
                current_seller += score
                seller_messages += 1
                reasons.update(evidence)
                if "professional_title" in evidence:
                    explicit_professional = True
            if _buyer_like(row):
                current_buyer += 1

        old = persistent.get(key, {})
        historical_seller = int(old.get("seller_evidence", 0) or 0)
        historical_listing_messages = int(old.get("seller_messages", 0) or 0)
        known_professional = bool(old.get("explicit_professional", False))

        # High-confidence agent persona: explicit occupation OR repeated seller
        # behavior in this scan OR strong accumulated seller history.
        risk = 0
        if explicit_professional or known_professional:
            risk = 100
        elif seller_messages >= 2 and current_seller >= 5:
            risk = 90
        elif current_seller >= 7:
            risk = 88
        elif historical_seller >= 10 and historical_listing_messages >= 3:
            risk = 85
        elif historical_seller + current_seller >= 12:
            risk = 82

        if risk >= 82:
            for row in rows:
                row["suspected_agent"] = True
                row["agent_risk_score"] = risk
                row["agent_evidence"] = sorted(reasons)[:8]
            flagged += 1

        # Persist only stable Telegram usernames. Buyer-like counts are retained
        # for audit, but do not erase a strong seller/agent history.
        if db and key.startswith("telegram:@"):
            try:
                ref = db.collection(COLLECTION).document(_doc_id(key))
                merged = dict(old)
                merged.update({
                    "author_key": key,
                    "author": rows[0].get("author", ""),
                    "last_seen": now,
                    "seller_evidence": historical_seller + current_seller,
                    "seller_messages": historical_listing_messages + seller_messages,
                    "buyer_like_messages": int(old.get("buyer_like_messages", 0) or 0) + current_buyer,
                    "explicit_professional": known_professional or explicit_professional,
                    "last_agent_risk_score": risk,
                })
                ref.set(merged, merge=True)
            except Exception as exc:
                print("NC_AUTHOR_REPUTATION_WRITE_ERROR", key, exc)

    print(f"NC_AUTHOR_REPUTATION authors={len(groups)} flagged_agent_personas={flagged}")
    return items
