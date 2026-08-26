import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

import north_cyprus_catcher as base
import north_cyprus_focus as nf
import north_cyprus_language_expansion  # activates extra buyer languages
import north_cyprus_farsi_expansion     # Iranian North Cyprus community buyer language
import north_cyprus_spam_guard
import north_cyprus_reply_context  # patches base classifier for terse replies under property posts
import telegram_global_search as tgs

from north_cyprus_author_reputation import annotate_author_reputation
from north_cyprus_cross_group import stitch_cross_group_identity
from north_cyprus_intent_classifier import classify_intent, is_buyer_catcher_eligible, display_intent
from north_cyprus_intent_routing import route_supply_candidate
from north_cyprus_publisher_classifier import annotate_publisher_types
from north_cyprus_semantic_dedupe import semantic_dedupe_items, consolidate_buyer_leads
import north_cyprus_notification_dedupe  # patches base notification dedupe by person+text
from north_cyprus_open_web_plus import OPEN_WEB_ALLOWED_DOMAINS, collect_open_web
from north_cyprus_source_performance import observe as observe_source
from north_cyprus_query_performance import observe as observe_query, ranked_queries
from telegram_channel_comments import collect_channel_comments
from telegram_known_public_groups import collect_known_public_groups
from telegram_member_deep_search import collect_member_deep_search
from telegram_network_crawler import crawl_network

for _domain in OPEN_WEB_ALLOWED_DOMAINS:
    nf.ALLOWED_USER_DOMAINS.add(_domain)

CORE_GLOBAL_QUERIES = [
    "North Cyprus property", "Kuzey Kıbrıs daire", "İskele daire", "Long Beach İskele",
    "Северный Кипр квартира", "Северный Кипр недвижимость",
]

EXTRA_GLOBAL_QUERIES = [
    "North Cyprus apartment", "Northern Cyprus property", "North Cyprus looking for apartment",
    "North Cyprus want to buy", "North Cyprus resale", "North Cyprus price", "North Cyprus owner direct",
    "North Cyprus private owner", "Long Beach 1+1", "Long Beach 2+1", "Long Beach resale",
    "İskele arıyorum", "İskele sahibinden", "İskele fiyat", "İskele villa arıyorum",
    "Girne daire", "Girne arıyorum", "Girne sahibinden", "Esentepe villa", "Esentepe arıyorum",
    "Kuzey Kıbrıs ev", "Kuzey Kıbrıs arıyorum", "Kuzey Kıbrıs satın almak", "Kuzey Kıbrıs sahibinden",
    "Kuzey Kıbrıs peşinat", "Kuzey Kıbrıs taksit", "Северный Кипр ищу", "Северный Кипр срочно ищу",
    "Северный Кипр ищу на покупку", "Северный Кипр хочу купить", "Северный Кипр нужна квартира",
    "Северный Кипр ищу виллу", "Северный Кипр только от собственника", "Северный Кипр цена",
    "Северный Кипр рассрочка", "Северный Кипр вторичка", "Северный Кипр от собственника",
    "Искеле ищу виллу", "Боаз ищу виллу", "Отюкен ищу виллу", "Йени Боазичи ищу виллу",
    "Caesar Resort", "Caesar Resort resale", "Grand Sapphire", "Grand Sapphire resale", "Isatis", "Isatis resale",
    "Elysium", "Elysium 2", "Fiora", "Isatis Orchard", "Royal Sun", "Royal Sun resale", "Riverside Life", "K'Saba İskele",
    "Nordzypern Wohnung kaufen", "Nordzypern Immobilie kaufen", "Nordzypern Haus kaufen",
    "Chypre du Nord acheter appartement", "Noord Cyprus woning kopen", "Cypr Północny szukam mieszkania",
    "Cypr Północny chcę kupić", "Північний Кіпр шукаю квартиру", "Північний Кіпр хочу купити",
    "شمال قبرص أبحث عن شقة", "شمال قبرص أريد شراء عقار", "قبرس شمالی خرید ملک", "قبرس شمالی خرید آپارتمان",
    "צפון קפריסין דירה לקנות",
]

PUBLIC_GROUP_DISCOVERY_QUERIES = [
    "North Cyprus", "Northern Cyprus", "North Cyprus property", "North Cyprus expats", "Kuzey Kıbrıs",
    "Kuzey Kıbrıs emlak", "Kuzey Kıbrıs gayrimenkul", "Северный Кипр", "Северный Кипр недвижимость",
    "Северный Кипр чат", "Искеле недвижимость", "İskele", "Long Beach Cyprus", "Girne", "Esentepe",
    "Famagusta Cyprus", "Caesar Resort Cyprus", "Grand Sapphire Cyprus", "Isatis Cyprus", "قبرس شمالی",
]


def _unique(values):
    out=[]; seen=set()
    for value in values:
        key=value.casefold()
        if key in seen: continue
        seen.add(key); out.append(value)
    return out


def _smart_queries():
    all_queries=_unique(list(tgs.GLOBAL_QUERIES)+EXTRA_GLOBAL_QUERIES)
    return ranked_queries(all_queries, 16, core=CORE_GLOBAL_QUERIES, exploration_ratio=0.30)


tgs.GLOBAL_QUERIES=_smart_queries()
tgs.PUBLIC_GROUP_DISCOVERY_QUERIES=_unique(list(tgs.PUBLIC_GROUP_DISCOVERY_QUERIES)+PUBLIC_GROUP_DISCOVERY_QUERIES)
_original_collect_global=base.collect_global_telegram
_original_classify=base._classify


def _decorate_intent(item, intent):
    item["intent_class"] = intent.get("intent_class", "UNKNOWN")
    item["intent_subtypes"] = list(intent.get("intent_subtypes") or [])
    item["intent_confidence"] = int(intent.get("intent_confidence") or 0)
    item["intent_reasons"] = list(intent.get("intent_reasons") or [])
    item["requirements"] = dict(intent.get("requirements") or {})
    item["intent_display"] = display_intent(intent)
    return item


def _direct_tenant_lead(item, intent, cutoff):
    if not item.get("url") or not nf._allowed_source(item):
        return None, "non_user_source"
    published = base.world_engine.resolved_published(item)
    if published is None:
        return None, "date_unverified"
    if published < cutoff:
        return None, "older_than_window"
    confidence = int(intent.get("intent_confidence") or 0)
    subtypes = list(intent.get("intent_subtypes") or [])
    if "SHARED_RENTAL" in subtypes:
        label = "WARM"
    else:
        label = "HOT" if confidence >= 82 else "WARM"
    credibility = min(92, 68 + (8 if item.get("author") else 0) + (5 if item.get("telegram_user_id") else 0) + (4 if item.get("reply_context") else 0))
    lead = _decorate_intent(dict(item), intent)
    lead.update({
        "classification": label,
        "intent_score": confidence,
        "credibility_score": credibility,
        "market_fit_score": 96,
        "market": "north_cyprus",
        "scanned_at": base.main.now_utc().isoformat(),
        "catcher_reason": "direction_first_tenant",
    })
    return lead, "accepted_tenant_intent"


def _classify_and_learn(item, cutoff):
    intent = classify_intent(item)
    _decorate_intent(item, intent)
    intent_class = intent.get("intent_class")

    if intent_class in {"OWNER", "AGENT"}:
        route_supply_candidate(item, intent)
        lead, reason = None, "routed_" + intent_class.lower()
    elif intent_class in {"SERVICE", "FINANCIAL", "SPAM", "UNKNOWN"}:
        lead, reason = None, "intent_" + str(intent_class).lower()
    elif intent_class == "TENANT":
        lead, reason = _direct_tenant_lead(item, intent, cutoff)
    elif intent_class == "BUYER":
        lead, reason = _original_classify(item, cutoff)
        if lead:
            _decorate_intent(lead, intent)
            # Buyer Catcher final output no longer exposes POTENTIAL. A direction-
            # verified buyer that only reached the old rescue lane becomes WARM.
            if lead.get("classification") == "POTENTIAL":
                lead["classification"] = "WARM"
                lead["intent_score"] = max(int(lead.get("intent_score") or 0), int(intent.get("intent_confidence") or 0))
    else:
        lead, reason = None, "intent_unknown"

    observe_source(item, lead, reason)
    observe_query(item, lead, reason)
    return lead, reason


base._classify = _classify_and_learn


def expanded_collect_global():
    network_stats=crawl_network()
    buckets=[]
    normal_global=_original_collect_global(); buckets.append(("telegram_global_public",normal_global))
    known_groups=collect_known_public_groups(); buckets.append(("telegram_verified_groups",known_groups))
    deep_member=collect_member_deep_search(); buckets.append(("telegram_joined_deep",deep_member))
    channel_comments=collect_channel_comments(); buckets.append(("telegram_channel_comments",channel_comments))
    open_web=collect_open_web(); buckets.append(("open_web_reddit_bing_dynamic",open_web))

    unique={}; counts={}
    for name,items in buckets:
        counts[name]=len(items)
        for item in items:
            key=item.get("url") or base.main.dedupe_key(item)
            unique[key]=item

    collected=semantic_dedupe_items(list(unique.values()))
    # Same ad reposted across groups is collapsed before publisher analysis so a
    # genuine single-property owner is not mistaken for an agent just for reposting.
    annotate_author_reputation(collected)
    annotate_publisher_types(collected)

    cross_profiles=stitch_cross_group_identity(collected,max_gap_hours=72,max_parts=8)
    collected.extend(cross_profiles)

    print("NC_EXPANDED_SOURCE_COUNTS",counts,"network",network_stats,"cross_group_profiles",len(cross_profiles),"semantic_unique",len(collected))
    return collected


base.collect_global_telegram=expanded_collect_global


def _format_requirements(lead):
    req = lead.get("requirements") or {}
    bits = []
    regions = req.get("regions") or []
    if regions:
        bits.append("Bölge: " + ", ".join(regions[:3]))
    if req.get("property_type"):
        bits.append("Mülk: " + str(req.get("property_type")))
    if req.get("budget"):
        bits.append("Bütçe: " + str(req.get("budget")))
    if req.get("move_window"):
        bits.append("Tarih: " + str(req.get("move_window")))
    prefs = req.get("preferences") or []
    if prefs:
        bits.append("Tercih: " + ", ".join(prefs[:5]))
    return " | ".join(bits)


def run():
    started=base.main.now_utc(); lookback_hours=int(os.getenv("WORLD_LOOKBACK_HOURS","8")); cutoff=started-timedelta(hours=lookback_hours)
    global_items=base.collect_global_telegram(); forum_items=base.collect_forum_replies(cutoff)
    originals=global_items+forum_items
    stitched=base.stitch_conversations(originals,max_gap_hours=int(os.getenv("NC_STITCH_GAP_HOURS","6")))
    raw_items=semantic_dedupe_items(originals+stitched)

    stats={}; accepted=[]; seen=set()
    for item in raw_items:
        key=item.get("url") or base.main.dedupe_key(item)
        identity_hint=str(item.get("telegram_user_id") or item.get("author") or "")
        key=f"{identity_hint}|{key}" if item.get("conversation_stitched") else key
        if key in seen: continue
        seen.add(key)
        lead,reason=base._classify(item,cutoff)
        stats[reason]=stats.get(reason,0)+1
        if lead and lead.get("intent_class") in {"BUYER","TENANT"}:
            accepted.append(lead)

    # Stitched/cross-group evidence now enriches one canonical person row instead
    # of producing additional Buyer Catcher notifications.
    accepted=consolidate_buyer_leads(accepted)
    rank={"HOT":3,"WARM":2}
    accepted.sort(key=lambda x:(rank.get(x.get("classification"),0),int(x.get("intent_confidence") or x.get("intent_score") or 0),int(x.get("credibility_score") or 0)),reverse=True)

    db=base.main.firestore_client(); new_leads=[]
    for lead in accepted:
        if base._notified_before(db,lead):
            continue
        new_leads.append(lead)
        base._mark_notified(db,lead)

    scan_id=f"{started.strftime('%Y%m%d%H%M%S')}_nc_catcher"
    if db:
        try:
            ref=db.collection(base.SCAN_COLLECTION).document(scan_id); batch=db.batch()
            for lead in accepted[:100]:
                ident=lead.get("canonical_identity") or lead.get("url") or lead.get("title","")
                doc_id=hashlib.sha1(str(ident).encode("utf-8")).hexdigest(); batch.set(ref.collection("leads").document(doc_id),lead,merge=True)
            batch.set(ref,{"started_at":started.isoformat(),"finished_at":base.main.now_utc().isoformat(),"lookback_hours":lookback_hours,"telegram_global_messages":len(global_items),"forum_recent_posts":len(forum_items),"conversation_stitches":len(stitched),"semantic_candidates":len(raw_items),"accepted_people":len(accepted),"new_to_notify":len(new_leads),"filter_stats":stats},merge=True); batch.commit()
        except Exception as exc: print("NC_CATCHER_FIRESTORE_ERROR",exc)

    print("NC_CATCHER_COMPLETE",json.dumps({"lookback_hours":lookback_hours,"telegram_global":len(global_items),"forum_posts":len(forum_items),"conversation_stitches":len(stitched),"semantic_candidates":len(raw_items),"accepted_people":len(accepted),"new":len(new_leads),"stats":stats},ensure_ascii=False))

    if new_leads:
        lines=[f"🎯 BAY-S NC BUYER CATCHER | {len(new_leads)} GERÇEK ADAY"]
        for lead in new_leads[:12]:
            author=lead.get("author") or "kullanıcı"; place=lead.get("telegram_chat") or lead.get("title") or lead.get("source") or ""
            excerpt=" ".join(str(lead.get("text","")).split())[:260]
            intent_label=display_intent(lead)
            req_line=_format_requirements(lead)
            confidence=int(lead.get("intent_confidence") or lead.get("intent_score") or 0)
            evidence=int(lead.get("evidence_count") or 1)
            header=f"{lead.get('classification','WARM')} | {author} | {intent_label}"
            details=f"Intent {confidence}% | Kanıt {evidence} | {place[:70]}"
            if req_line:
                details += "\n" + req_line
            lines.append(f"\n{header}\n{details}\n{excerpt}\n{lead.get('url','')}")
        base.main.notify_telegram("\n".join(lines))
    else:
        base.main.notify_telegram(f"🎯 BAY-S NC BUYER CATCHER tamamlandı.\nYeni gerçek BUYER/TENANT yok.\nGlobal/çoklu kaynak: {len(global_items)}\nForum yeni post: {len(forum_items)}\nStitch kanıtı: {len(stitched)}\nSemantic aday: {len(raw_items)} | Son {lookback_hours} saat")


if __name__=="__main__":
    run()
