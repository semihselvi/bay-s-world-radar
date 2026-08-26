from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from typing import Any


def _norm(value: Any) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    text = re.sub(r"https?://\S+|t\.me/\S+", " ", text, flags=re.I)
    text = re.sub(r"@\w+", " ", text, flags=re.UNICODE)
    text = re.sub(r"[^\w+£€$]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")
CONTACT_RE = re.compile(r"(?:wa\.me/\d+|t\.me/[A-Za-z0-9_+/-]+)", re.I)
CAMPAIGN_RE = re.compile(
    r"\b(?:whatsapp|contact|dm|пишите|обращайтесь|звоните|доставка|услуг|service|temu|shein|"
    r"satılık|kiralık|продается|сдается|available|starting from|цена|стоимость|воды|filter|"
    r"репетитор|tutor|smm|followers)\b",
    re.I,
)
DEMAND_RE = re.compile(
    r"\b(?:looking to buy|want to buy|looking to rent|want to rent|satın almak istiyorum|kiralık arıyorum|"
    r"хочу купить|куплю|хочу снять|сниму|ищу на покупку|ищу .*в аренду)\b",
    re.I,
)


def stable_identity(item: dict[str, Any]) -> str:
    uid = str(item.get("telegram_user_id") or "").strip()
    if uid.isdigit() and uid != "0":
        return "telegram_user:" + uid
    author = " ".join(str(item.get("author") or "").casefold().split())
    if author.startswith("@") and len(author) > 2:
        return "telegram_username:" + author
    return ""


def extract_phones(text: str) -> set[str]:
    out = set()
    for raw in PHONE_RE.findall(str(text or "")):
        digits = re.sub(r"\D", "", raw)
        if 8 <= len(digits) <= 15:
            out.add(digits)
    return out


def _contacts(text: str) -> set[str]:
    return {x.casefold() for x in CONTACT_RE.findall(str(text or ""))}


def _campaign_like(text: str) -> bool:
    return bool(CAMPAIGN_RE.search(text)) and not bool(DEMAND_RE.search(text))


def _merge_item(primary: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    urls = list(merged.get("source_links") or [])
    for url in [primary.get("url"), extra.get("url")] + list(extra.get("source_links") or []):
        if url and url not in urls:
            urls.append(url)
    chats = list(merged.get("source_chats") or [])
    for chat in [primary.get("telegram_chat"), extra.get("telegram_chat")] + list(extra.get("source_chats") or []):
        if chat and chat not in chats:
            chats.append(chat)
    aliases = list(merged.get("author_aliases") or [])
    for author in [primary.get("author"), extra.get("author")] + list(extra.get("author_aliases") or []):
        if author and author not in aliases:
            aliases.append(author)
    evidence = list(merged.get("evidence_texts") or [])
    for body in [primary.get("text"), extra.get("text")]:
        clean = " ".join(str(body or "").split())
        if clean and clean not in evidence:
            evidence.append(clean[:1400])
    merged["source_links"] = urls[:20]
    merged["source_chats"] = chats[:20]
    merged["author_aliases"] = aliases[:12]
    merged["evidence_texts"] = evidence[:12]
    merged["semantic_merged"] = True
    merged["evidence_count"] = max(int(primary.get("evidence_count") or 1), 1) + max(int(extra.get("evidence_count") or 1), 1)
    if str(extra.get("published") or "") >= str(primary.get("published") or ""):
        for key in ("published", "url", "telegram_chat"):
            if extra.get(key):
                merged[key] = extra.get(key)
    if primary.get("conversation_stitched") and not extra.get("conversation_stitched"):
        merged["url"] = extra.get("url") or merged.get("url")
    return merged


def semantic_dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse same-person repeats and conservative cross-account campaigns.

    Different buyer accounts are never merged merely because their wording looks
    similar. Cross-account fuzzy merging requires ad/service shape or a matching
    phone/contact identity.
    """
    out: list[dict[str, Any]] = []
    by_url: dict[str, int] = {}
    by_person_text: dict[tuple[str, str], int] = {}
    by_person: dict[str, list[int]] = {}
    by_phone: dict[str, int] = {}
    by_contact: dict[str, int] = {}
    campaign_indexes: list[int] = []

    for raw in items:
        item = dict(raw)
        body = _norm(item.get("text"))
        url = str(item.get("url") or "").strip()
        ident = stable_identity(item)
        phones = extract_phones(item.get("text") or "")
        contacts = _contacts(item.get("text") or "")

        idx = by_url.get(url) if url else None
        if idx is None and ident and len(body) >= 20:
            digest = hashlib.sha1(body.encode("utf-8")).hexdigest()
            idx = by_person_text.get((ident, digest))
            if idx is None and len(body) >= 70:
                for cand in reversed(by_person.get(ident, [])[-20:]):
                    other = _norm(out[cand].get("text"))
                    if abs(len(body) - len(other)) <= max(60, int(max(len(body), len(other)) * 0.30)):
                        if SequenceMatcher(None, body[:1800], other[:1800]).ratio() >= 0.90:
                            idx = cand
                            break
        if idx is None:
            for phone in phones:
                if phone in by_phone:
                    cand = by_phone[phone]
                    other = _norm(out[cand].get("text"))
                    if body == other or SequenceMatcher(None, body[:1800], other[:1800]).ratio() >= 0.72:
                        idx = cand
                        break
        if idx is None:
            for contact in contacts:
                if contact in by_contact:
                    cand = by_contact[contact]
                    other = _norm(out[cand].get("text"))
                    if body == other or SequenceMatcher(None, body[:1800], other[:1800]).ratio() >= 0.75:
                        idx = cand
                        break

        if idx is None and len(body) >= 90 and _campaign_like(body):
            for cand in reversed(campaign_indexes[-120:]):
                other = _norm(out[cand].get("text"))
                if abs(len(body) - len(other)) > max(80, int(max(len(body), len(other)) * 0.35)):
                    continue
                if SequenceMatcher(None, body[:2200], other[:2200]).ratio() >= 0.90:
                    idx = cand
                    break

        if idx is None:
            idx = len(out)
            out.append(item)
            if _campaign_like(body):
                campaign_indexes.append(idx)
        else:
            out[idx] = _merge_item(out[idx], item)

        if url:
            by_url[url] = idx
        if ident and len(body) >= 20:
            by_person_text[(ident, hashlib.sha1(body.encode("utf-8")).hexdigest())] = idx
            if idx not in by_person.setdefault(ident, []):
                by_person[ident].append(idx)
        for phone in phones:
            by_phone[phone] = idx
        for contact in contacts:
            by_contact[contact] = idx

    return out


def _lead_strength(lead: dict[str, Any]) -> tuple[int, int, int, str]:
    rank = {"HOT": 3, "WARM": 2, "POTENTIAL": 1}
    return (
        rank.get(str(lead.get("classification") or ""), 0),
        int(lead.get("intent_confidence") or lead.get("intent_score") or 0),
        int(lead.get("credibility_score") or 0),
        str(lead.get("published") or ""),
    )


def consolidate_buyer_leads(leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One person = one final Buyer Catcher candidate.

    Stitched and cross-group rows enrich the canonical lead instead of becoming
    extra final rows.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    anon_counter = 0
    for lead in leads:
        ident = stable_identity(lead)
        if not ident:
            phones = extract_phones(lead.get("text") or "")
            if phones:
                ident = "phone:" + sorted(phones)[0]
        if not ident:
            author = " ".join(str(lead.get("author") or "").casefold().split())
            chat = " ".join(str(lead.get("telegram_chat") or "").casefold().split())
            if author and chat:
                ident = "local:" + chat + "|" + author
        if not ident:
            anon_counter += 1
            ident = "anon:" + str(anon_counter) + "|" + str(lead.get("url") or "")
        groups.setdefault(ident, []).append(lead)

    final = []
    for ident, rows in groups.items():
        best = max(rows, key=_lead_strength)
        merged = dict(best)
        for row in rows:
            if row is best:
                continue
            merged = _merge_item(merged, row)
            for key in ("classification", "intent_score", "credibility_score", "market_fit_score", "intent_class", "intent_confidence", "catcher_reason"):
                if best.get(key) is not None:
                    merged[key] = best.get(key)
        subtypes = []
        for row in rows:
            for subtype in row.get("intent_subtypes") or []:
                if subtype not in subtypes:
                    subtypes.append(subtype)
        if subtypes:
            merged["intent_subtypes"] = subtypes
        req = dict(best.get("requirements") or {})
        for field in ("regions", "preferences"):
            values = []
            for row in rows:
                for value in (row.get("requirements") or {}).get(field) or []:
                    if value not in values:
                        values.append(value)
            if values:
                req[field] = values
        for field in ("property_type", "budget", "move_window"):
            if not req.get(field):
                for row in sorted(rows, key=_lead_strength, reverse=True):
                    value = (row.get("requirements") or {}).get(field)
                    if value:
                        req[field] = value
                        break
        merged["requirements"] = req
        merged["canonical_identity"] = ident
        merged["evidence_count"] = max(len(rows), int(merged.get("evidence_count") or 1))
        merged["stitched_evidence_count"] = sum(1 for row in rows if row.get("conversation_stitched") or row.get("conversation_cross_group"))
        final.append(merged)

    return final
