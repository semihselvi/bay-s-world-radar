from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from radar_xl.models import ClassifiedCandidate


def normalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
        host = parts.netloc.lower().replace("www.", "")
        path = re.sub(r"/$", "", parts.path)
        return urlunsplit((parts.scheme.lower() or "https", host, path, "", ""))
    except Exception:
        return url.strip()


def normalize_text(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^\w\s£€$₺₽]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def fingerprint(item: ClassifiedCandidate) -> str:
    c = item.candidate
    url = normalize_url(c.url)
    if url:
        basis = f"url:{url}"
    else:
        author = normalize_text(c.author)
        body = normalize_text(f"{c.title} {c.text}")[:1200]
        basis = f"content:{c.source_kind}:{author}:{body}"
    return hashlib.sha256(basis.encode("utf-8", errors="ignore")).hexdigest()


def dedupe(items: list[ClassifiedCandidate]) -> list[ClassifiedCandidate]:
    by_key: dict[str, ClassifiedCandidate] = {}
    for item in items:
        key = fingerprint(item)
        existing = by_key.get(key)
        if existing is None or item.score > existing.score:
            by_key[key] = item
    return list(by_key.values())
