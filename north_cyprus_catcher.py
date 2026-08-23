import hashlib
import json
import os
import re
from datetime import timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

import main
import world_engine
import north_cyprus_recall as recall
import north_cyprus_focus as nf
from telegram_global_search import collect_global_telegram


NOTIFIED_COLLECTION = "bay_s_nc_catcher_notified"
SCAN_COLLECTION = "bay_s_nc_catcher_scans"

# The existing Recall lane is already permissive, but short Telegram buyer
# questions are even terser in practice: "price?", "Caesar resale?", "2+1?".
# These patterns are intentionally request-shaped rather than generic ad words.
TERSE_REQUEST_PATTERNS = [
    r"\bprice\s*\??$",
    r"\bfiyat\s*\??$",
    r"\bцена\s*\??$",
    r"\bresale\s*\??$",
    r"\bavailable\s*\??$",
    r"\bavailability\s*\??$",
    r"\bany units?\b",
    r"\bany availability\b",
    r"\bwho has\b",
    r"\bwho is selling\b",
    r"\bany owner\b",
    r"\bowner selling\b",
    r"\bdoes anyone know\b",
    r"\bcan someone (?:send|share|recommend|help)\b",
    r"\bplease (?:dm|pm) me\b",
    r"\bdm me if\b",
    r"\bpm me if\b",
    r"\bkimde var\b",
    r"\bsahibinden\b",
    r"\bfiyat bilen\b",
    r"\bvarsa yaz\b",
    r"\bкто прода[её]т\b",
    r"\bесть у кого\b",
    r"\bнапишите если есть\b",
]

TRANSACTION_PATTERNS = [
    r"\bprice\b", r"\bfiyat\b", r"\bцена\b", r"\bresale\b", r"\bsecond hand\b",
    r"\bavailable\b", r"\bavailability\b", r"\bowner\b", r"\bsahibinden\b",
    r"\btitle deed\b", r"\bko[çc]an\b", r"\bpayment plan\b", r"\binstallments?\b",
    r"\bpe[şs]inat\b", r"\btaksit\b", r"\bmortgage\b", r"\bdeposit\b",
    r"\bviewing\b", r"\boffer\b", r"\bproject\b", r"\bdeveloper\b",
    r"\binvest(?:ment|ing)?\b", r"\byat[ıi]r[ıi]m\b", r"\byield\b",
    r"\bрассроч", r"\bвзнос\b", r"\bипотек", r"\bтитул\b", r"\bвторичк",
]

REQUEST_SHAPE_PATTERNS = [
    r"^\s*(?:looking|need|needed|wanted|any|who|where|which|price|fiyat|resale|available)\b",
    r"\b(?:looking for|need a|need an|i need|we need|wanted:)\b",
    r"\b(?:ar[ıi]yorum|ar[ıi]yoruz|laz[ıi]m|kimde var|var m[ıi])\b",
    r"\b(?:ищу|нужна|нужен|нужны|кто прода[её]т|есть ли)\b",
]

GENERIC_AD_PATTERNS = [
    r"\bcontact us\b", r"\bdm\s+@\w+", r"\bwhatsapp\b", r"\bcall us\b",
    r"\bapply now\b", r"\blimited spots\b", r"\bcommission[- ]based\b",
    r"\bjoin (?:our|the) team\b", r"\bwe offer\b", r"\bour services\b",
    r"\bbook now\b", r"\bstarting from\b", r"https?://", r"www\.",
    r"\+?90\s*5\d{2}",
]

# Extend only inside this process. Existing production files remain unchanged.
for _pattern in TERSE_REQUEST_PATTERNS:
    if _pattern not in nf.REQUEST_BUYER_PATTERNS:
        nf.REQUEST_BUYER_PATTERNS.append(_pattern)


def _matches(text, patterns):
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _count(text, patterns):
    return sum(1 for pattern in patterns if re.search(pattern, text, re.I))


def _question_shape(text):
    stripped = " ".join(str(text).split())
    if "?" in stripped or "؟" in stripped:
        return True
    return _matches(stripped, REQUEST_SHAPE_PATTERNS)


def _project_signal(text):
    return _matches(text, recall.PROJECT_CONTEXT_PATTERNS)


def _ad_like(text):
    # north_cyprus_hunter already layers service-ad filters for PulseMarket,
    # transfer, education, vehicle finance, parcel delivery and recruitment.
    if nf._promotional_service_ad(text):
        return True

    strong = nf._matches(text, nf.STRONG_BUYER_PATTERNS)
    request = nf._matches(text, nf.REQUEST_BUYER_PATTERNS)
    seller_hits = sum(1 for phrase in nf.SELLER_PATTERNS if phrase.lower() in text.lower())
    if seller_hits >= 2 and not strong:
        return True

    ad_hits = _count(text, GENERIC_AD_PATTERNS)
    # Require multiple marketing/CTA signals and no genuine buyer request shape.
    return ad_hits >= 3 and not (strong or request or _question_shape(text))


def _classify(item, cutoff):
    if not item.get("url") or not nf._allowed_source(item):
        return None, "non_user_source"

    published = world_engine.resolved_published(item)
    if published is None:
        return None, "date_unverified"
    if published < cutoff:
        return None, "older_than_window"

    text = nf._text(item)
    if not text:
        return None, "empty"
    if _ad_like(text):
        return None, "promotional_or_seller"
    if not nf._nc_context(item, text):
        return None, "not_north_cyprus"
    if nf._matches(text, nf.RENTAL_PATTERNS):
        return None, "rental"

    # First give the existing high-recall engine a chance. Preserve its HOT/WARM.
    keep, reason = recall.recall_keep_candidate(item, cutoff)
    if keep:
        intent, credibility, fit, label = recall.recall_buyer_scores(item)
        if label in ("HOT", "WARM"):
            lead = dict(item)
            lead.update({
                "classification": label,
                "intent_score": intent,
                "credibility_score": credibility,
                "market_fit_score": max(fit, 92),
                "market": "north_cyprus",
                "scanned_at": main.now_utc().isoformat(),
                "catcher_reason": reason,
            })
            return lead, "accepted_existing_recall"

    strong = nf._matches(text, nf.STRONG_BUYER_PATTERNS)
    request = nf._matches(text, nf.REQUEST_BUYER_PATTERNS)
    personal = nf._matches(text, nf.PERSONAL_PATTERNS)
    property_signal = nf._matches(text, nf.PROPERTY_PATTERNS)
    project = _project_signal(text)
    concrete = nf._matches(text, nf.CONCRETE_PATTERNS)
    transaction = _matches(text, TRANSACTION_PATTERNS)
    question = _question_shape(text)

    # Maximum-recall rescue rules. The message must still look like a human
    # request/question; a bare property listing with price is not enough.
    warm = False
    potential = False

    if strong and (property_signal or project or concrete or transaction):
        warm = True
    elif request and (property_signal or project or concrete or transaction):
        warm = True
    elif question and (property_signal or project or concrete or transaction):
        potential = True
    elif personal and concrete and (property_signal or project):
        potential = True

    if not warm and not potential:
        return None, reason or "no_request_shape"

    feature_count = sum(bool(x) for x in (strong, request, personal, property_signal, project, concrete, transaction, question))
    if warm:
        label = "WARM"
        intent = min(86, 64 + feature_count * 3 + (6 if concrete else 0))
        credibility = min(88, 60 + (8 if item.get("author") else 0) + feature_count * 2)
    else:
        label = "POTENTIAL"
        intent = min(76, 54 + feature_count * 3 + (5 if concrete else 0))
        credibility = min(82, 56 + (8 if item.get("author") else 0) + feature_count * 2)

    lead = dict(item)
    lead.update({
        "classification": label,
        "intent_score": intent,
        "credibility_score": credibility,
        "market_fit_score": 94,
        "market": "north_cyprus",
        "scanned_at": main.now_utc().isoformat(),
        "catcher_reason": "terse_request_rescue",
        "catcher_features": {
            "strong": strong,
            "request": request,
            "personal": personal,
            "property": property_signal,
            "project": project,
            "concrete": concrete,
            "transaction": transaction,
            "question": question,
        },
    })
    return lead, "accepted_terse_rescue"


def _forum_thread_links(index_url, property_sales_only=False, max_threads=18):
    try:
        response = main.SESSION.get(index_url, timeout=20, allow_redirects=True)
        if response.status_code != 200:
            print("NC_CATCHER_FORUM_INDEX_ERROR", response.status_code, index_url)
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        pages = [(response.url, soup)]

        if property_sales_only:
            for anchor in soup.find_all("a", href=True):
                label = " ".join(anchor.get_text(" ", strip=True).split()).lower()
                if "property sales" in label or "buy or sell" in label:
                    href = urljoin(response.url, anchor["href"])
                    try:
                        sub = main.SESSION.get(href, timeout=20, allow_redirects=True)
                        if sub.status_code == 200:
                            pages.insert(0, (sub.url, BeautifulSoup(sub.text, "html.parser")))
                    except Exception:
                        pass
                    break

        links = []
        for base_url, page_soup in pages:
            for anchor in page_soup.find_all("a", href=True):
                href = urljoin(base_url, anchor["href"])
                if "viewtopic.php" not in href.lower():
                    continue
                if href not in links:
                    links.append(href)
                if len(links) >= max_threads:
                    return links
        return links
    except Exception as exc:
        print("NC_CATCHER_FORUM_INDEX_EXCEPTION", index_url, exc)
        return []


def _extract_phpbb_posts(thread_url, source_name, cutoff):
    items = []
    try:
        response = main.SESSION.get(thread_url, timeout=20, allow_redirects=True)
        if response.status_code != 200:
            return []
        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.select("div.post")
        for post in posts:
            time_node = post.select_one("time[datetime]")
            if not time_node:
                continue
            published = main.parse_dt(time_node.get("datetime", ""))
            if not published or published < cutoff:
                continue

            content = post.select_one(".content") or post.select_one(".postbody")
            if not content:
                continue
            text = " ".join(content.get_text(" ", strip=True).split())
            if not text:
                continue

            author_node = post.select_one(".username-coloured") or post.select_one(".username")
            author = " ".join(author_node.get_text(" ", strip=True).split()) if author_node else ""
            post_id = str(post.get("id") or "").strip()
            if post_id:
                url = response.url.split("#", 1)[0] + f"#{post_id}"
            else:
                url = response.url

            title_node = soup.select_one("h2 a") or soup.title
            title = " ".join(title_node.get_text(" ", strip=True).split()) if title_node else source_name
            items.append({
                "source": source_name,
                "url": url,
                "title": title,
                "text": text[:7000],
                "published": published.isoformat(),
                "author": author,
                "source_bucket": "nc_catcher_forum_reply",
            })
    except Exception as exc:
        print("NC_CATCHER_FORUM_THREAD_EXCEPTION", thread_url, exc)
    return items


def collect_forum_replies(cutoff):
    if os.getenv("NC_CATCHER_FORUM", "0").strip() != "1":
        return []

    specs = [
        ("Kibkom North Cyprus", "https://kibkomnorthcyprusforum.com/", True),
        ("AWD North Cyprus", "https://forum.awd.ru/viewforum.php?f=1683", False),
    ]
    all_items = {}
    for name, index_url, property_only in specs:
        links = _forum_thread_links(index_url, property_sales_only=property_only)
        count = 0
        for link in links:
            for item in _extract_phpbb_posts(link, name, cutoff):
                all_items[item["url"]] = item
                count += 1
        print(f"NC_CATCHER_FORUM source={name!r} threads={len(links)} recent_posts={count}")
    return list(all_items.values())


def _notified_before(db, lead):
    if not db:
        return False
    key = hashlib.sha1((lead.get("url") or "").encode("utf-8")).hexdigest()
    try:
        return db.collection(NOTIFIED_COLLECTION).document(key).get().exists
    except Exception as exc:
        print("NC_CATCHER_DEDUPE_READ_ERROR", exc)
        return False


def _mark_notified(db, lead):
    if not db:
        return
    key = hashlib.sha1((lead.get("url") or "").encode("utf-8")).hexdigest()
    try:
        db.collection(NOTIFIED_COLLECTION).document(key).set({
            "url": lead.get("url", ""),
            "classification": lead.get("classification", ""),
            "notified_at": main.now_utc().isoformat(),
            "author": lead.get("author", ""),
            "telegram_chat": lead.get("telegram_chat", ""),
        }, merge=True)
    except Exception as exc:
        print("NC_CATCHER_DEDUPE_WRITE_ERROR", exc)


def run():
    started = main.now_utc()
    lookback_hours = int(os.getenv("WORLD_LOOKBACK_HOURS", "8"))
    cutoff = started - timedelta(hours=lookback_hours)

    global_items = collect_global_telegram()
    forum_items = collect_forum_replies(cutoff)
    raw_items = global_items + forum_items

    stats = {}
    accepted = []
    seen = set()
    for item in raw_items:
        key = item.get("url") or main.dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        lead, reason = _classify(item, cutoff)
        stats[reason] = stats.get(reason, 0) + 1
        if lead:
            accepted.append(lead)

    rank = {"HOT": 3, "WARM": 2, "POTENTIAL": 1}
    accepted.sort(
        key=lambda x: (rank.get(x.get("classification"), 0), x.get("intent_score", 0), x.get("credibility_score", 0)),
        reverse=True,
    )

    db = main.firestore_client()
    new_leads = []
    for lead in accepted:
        if _notified_before(db, lead):
            continue
        new_leads.append(lead)
        # Mark all accepted items, not only those fitting in one Telegram message.
        _mark_notified(db, lead)

    scan_id = f"{started.strftime('%Y%m%d%H%M%S')}_nc_catcher"
    if db:
        try:
            ref = db.collection(SCAN_COLLECTION).document(scan_id)
            batch = db.batch()
            for lead in accepted[:100]:
                doc_id = hashlib.sha1((lead.get("url") or lead.get("title", "")).encode("utf-8")).hexdigest()
                batch.set(ref.collection("leads").document(doc_id), lead, merge=True)
            batch.set(ref, {
                "started_at": started.isoformat(),
                "finished_at": main.now_utc().isoformat(),
                "lookback_hours": lookback_hours,
                "telegram_global_messages": len(global_items),
                "forum_recent_posts": len(forum_items),
                "unique_candidates": len(seen),
                "accepted": len(accepted),
                "new_to_notify": len(new_leads),
                "filter_stats": stats,
            }, merge=True)
            batch.commit()
        except Exception as exc:
            print("NC_CATCHER_FIRESTORE_ERROR", exc)

    print(
        "NC_CATCHER_COMPLETE",
        json.dumps({
            "lookback_hours": lookback_hours,
            "telegram_global": len(global_items),
            "forum_posts": len(forum_items),
            "unique": len(seen),
            "accepted": len(accepted),
            "new": len(new_leads),
            "stats": stats,
        }, ensure_ascii=False),
    )

    if new_leads:
        lines = [f"🎯 BAY-S NC BUYER CATCHER | {len(new_leads)} YENİ ADAY"]
        for lead in new_leads[:12]:
            author = lead.get("author") or "kullanıcı"
            place = lead.get("telegram_chat") or lead.get("title") or lead.get("source") or ""
            excerpt = " ".join(str(lead.get("text", "")).split())[:260]
            lines.append(
                f"\n{lead.get('classification','POTENTIAL')} | {author} | {place[:80]}\n"
                f"I{lead.get('intent_score',0)} C{lead.get('credibility_score',0)} F{lead.get('market_fit_score',94)}\n"
                f"{excerpt}\n{lead.get('url','')}"
            )
        main.notify_telegram("\n".join(lines))
    else:
        main.notify_telegram(
            f"🎯 BAY-S NC BUYER CATCHER tamamlandı.\n"
            f"Yeni aday yok.\n"
            f"Global Telegram: {len(global_items)}\n"
            f"Forum yeni post: {len(forum_items)}\n"
            f"İncelenen: {len(seen)} | Son {lookback_hours} saat"
        )


if __name__ == "__main__":
    run()
