import os
import re
from datetime import datetime, timezone

import youtube_radar as yr
import north_cyprus_focus as nf
import north_cyprus_language_expansion
import north_cyprus_farsi_expansion
import north_cyprus_spam_guard

_BASE_LOAD_WATCHLIST = yr.load_watchlist
_BASE_SCAN_COMMENTS = yr.scan_comments
_BASE_CLASSIFY = yr.classify_comment

ENGAGEMENT = [
    r"^\s*interested\s*[.!?]*$", r"details please", r"send details", r"still available", r"is this available",
    r"fiyat nedir", r"detay", r"ilgileniyorum", r"mevcut mu", r"görebilir miyim",
    r"интересует", r"интересно", r"актуально", r"можно подробнее", r"какая цена", r"можно посмотреть",
    r"interessiert", r"noch verfügbar", r"je suis intéress", r"toujours disponible",
    r"jestem zainteresowan", r"czy aktualne", r"зацікав", r"ще актуально",
    r"قیمت", r"اطلاعات بیشتر", r"موجوده", r"علاقه.?مندم",
]


def _parse(value):
    try: return yr._parse_dt(value)
    except Exception: return None


def _freshness_score(data):
    now=datetime.now(timezone.utc); score=0.0
    for field,weight in (("last_lead_at",90),("last_comment_seen_at",50),("discovered_at",15)):
        dt=_parse(data.get(field))
        if not dt: continue
        age_days=max(0.0,(now-dt).total_seconds()/86400); score+=weight/(1.0+age_days)
    if data.get("last_lead_classification")=="HOT": score+=25
    elif data.get("last_lead_classification")=="WARM": score+=12
    return score


def load_watchlist_ranked():
    db=yr.main.firestore_client()
    if not db: return []
    limit=max(20,int(os.getenv("YOUTUBE_WATCHLIST_LIMIT","160"))); pool_limit=min(800,max(limit*4,limit)); pool=[]
    try:
        for doc in db.collection(yr.WATCHLIST_COLLECTION).limit(pool_limit).stream():
            data=doc.to_dict() or {}
            if data.get("status")!="active" or data.get("market")!="north_cyprus" or not data.get("video_id"): continue
            pool.append(data)
    except Exception as exc:
        print("YOUTUBE_WATCHLIST_RANK_ERROR",exc); return _BASE_LOAD_WATCHLIST()
    if len(pool)<=limit:
        pool.sort(key=_freshness_score,reverse=True); print(f"YOUTUBE_WATCHLIST_RANKED pool={len(pool)} selected={len(pool)}"); return pool
    ranked=sorted(pool,key=_freshness_score,reverse=True); priority_count=max(1,int(limit*0.80)); priority=ranked[:priority_count]; remainder=ranked[priority_count:]
    explore_count=limit-len(priority); now=datetime.now(timezone.utc)
    if remainder and explore_count>0:
        slot=now.timetuple().tm_yday*8+now.hour//3; start=(slot*explore_count)%len(remainder)
        exploration=[remainder[(start+i)%len(remainder)] for i in range(min(explore_count,len(remainder)))]
    else: exploration=[]
    selected=priority+exploration
    print(f"YOUTUBE_WATCHLIST_RANKED pool={len(pool)} priority={len(priority)} explore={len(exploration)} selected={len(selected)}")
    return selected


def _comment_item(comment,video,uploader_channel_id,reply_context=""):
    snippet=comment.get("snippet") or {}; published=_parse(snippet.get("publishedAt"))
    if not published: return None
    author_channel=((snippet.get("authorChannelId") or {}).get("value") or "")
    if uploader_channel_id and author_channel==uploader_channel_id: return None
    comment_id=str(comment.get("id") or ""); text=str(snippet.get("textDisplay") or "").strip()
    if not comment_id or not text: return None
    return {"comment_id":comment_id,"video_id":video.get("video_id"),"video_title":video.get("title",""),"channel_title":video.get("channel_title",""),"text":text,"author":str(snippet.get("authorDisplayName") or ""),"author_channel_id":author_channel,"published":published.isoformat(),"updated":str(snippet.get("updatedAt") or ""),"url":f"https://www.youtube.com/watch?v={video.get('video_id')}&lc={comment_id}","source":"YouTube Comment","reply_context":" ".join(str(reply_context or "").split())[:1600]}


def _all_replies(parent_id,parent_text,video,uploader_channel_id,cutoff,max_pages):
    token=None
    for _ in range(max_pages):
        params={"part":"snippet","parentId":parent_id,"maxResults":100,"textFormat":"plainText"}
        if token: params["pageToken"]=token
        data=yr._get("comments",params)
        if not data: return
        for comment in data.get("items",[]):
            item=_comment_item(comment,video,uploader_channel_id,parent_text)
            if not item: continue
            published=_parse(item.get("published"))
            if published and published>=cutoff: yield item
        token=data.get("nextPageToken")
        if not token: return


def iter_comments_expanded(video,cutoff):
    """Scan top-level comments and expand missing replies with comments.list(parentId)."""
    video_id=video.get("video_id"); pages=max(1,min(3,int(os.getenv("YOUTUBE_COMMENT_PAGES","1"))))
    reply_thread_limit=max(0,min(20,int(os.getenv("YOUTUBE_FULL_REPLY_THREADS_PER_VIDEO","6")))); reply_pages=max(1,min(3,int(os.getenv("YOUTUBE_FULL_REPLY_PAGES","2"))))
    scan_old=os.getenv("YOUTUBE_SCAN_OLD_THREAD_REPLIES","1").strip()=="1"; uploader_channel_id=str(video.get("channel_id") or "")
    page_token=None; seen=set(); extra_reply_threads=0; recent_seen=[]
    for _ in range(pages):
        params={"part":"snippet,replies","videoId":video_id,"maxResults":100,"order":"time","textFormat":"plainText"}
        if page_token: params["pageToken"]=page_token
        data=yr._get("commentThreads",params)
        if not data: break
        oldest_top=None
        for thread in data.get("items",[]):
            ts=thread.get("snippet") or {}; top=ts.get("topLevelComment") or {}; top_id=str(top.get("id") or ""); top_text=str((top.get("snippet") or {}).get("textDisplay") or "").strip()
            top_item=_comment_item(top,video,uploader_channel_id)
            if top_item:
                top_dt=_parse(top_item.get("published")); oldest_top=top_dt if top_dt and (oldest_top is None or top_dt<oldest_top) else oldest_top
                if top_dt and top_dt>=cutoff and top_item["comment_id"] not in seen:
                    seen.add(top_item["comment_id"]); recent_seen.append(top_dt); yield top_item
            embedded=((thread.get("replies") or {}).get("comments") or [])
            for comment in embedded:
                item=_comment_item(comment,video,uploader_channel_id,top_text)
                if not item or item["comment_id"] in seen: continue
                seen.add(item["comment_id"]); published=_parse(item.get("published"))
                if published and published>=cutoff: recent_seen.append(published); yield item
            total_replies=int(ts.get("totalReplyCount") or 0)
            if top_id and total_replies>len(embedded) and extra_reply_threads<reply_thread_limit:
                extra_reply_threads+=1
                for item in _all_replies(top_id,top_text,video,uploader_channel_id,cutoff,reply_pages):
                    if item["comment_id"] in seen: continue
                    seen.add(item["comment_id"]); published=_parse(item.get("published"))
                    if published: recent_seen.append(published)
                    yield item
        page_token=data.get("nextPageToken")
        if not page_token: break
        if not scan_old and oldest_top and oldest_top<cutoff: break
    if recent_seen:
        latest=max(recent_seen); db=yr.main.firestore_client()
        if db and video_id:
            try: db.collection(yr.WATCHLIST_COLLECTION).document(video_id).set({"last_comment_seen_at":latest.isoformat(),"last_comment_scan_at":yr._now().isoformat()},merge=True)
            except Exception as exc: print("YOUTUBE_ACTIVITY_WRITE_ERROR",video_id,exc)
    if extra_reply_threads: print(f"YOUTUBE_FULL_REPLIES video={video_id} expanded_threads={extra_reply_threads} unique_comments={len(seen)}")


def classify_comment_expanded(item):
    lead=_BASE_CLASSIFY(item)
    if lead: return lead
    own=" ".join(str(item.get("text","")).split())
    if not own or nf._promotional_service_ad(own): return None
    video_context=f"{item.get('video_title','')} {item.get('channel_title','')}"; parent=" ".join(str(item.get("reply_context","")).split()); context=f"{video_context} {parent}"
    if not yr._video_context(video_context): return None
    if nf._matches(own,nf.RENTAL_PATTERNS) and not nf._matches(own,nf.STRONG_BUYER_PATTERNS): return None
    strong=nf._matches(own,nf.STRONG_BUYER_PATTERNS); request=nf._matches(own,nf.REQUEST_BUYER_PATTERNS); engagement=any(re.search(p,own,re.I) for p in ENGAGEMENT); question="?" in own or "؟" in own
    property_context=nf._matches(context,nf.PROPERTY_PATTERNS); concrete=nf._matches(f"{own} {context}",nf.CONCRETE_PATTERNS)
    if not (strong or request or engagement or question): return None
    if not (property_context or concrete or parent): return None
    features=sum(bool(x) for x in (strong,request,engagement,question,property_context,concrete,parent))
    if strong or request or engagement: label="WARM"; intent=min(91,64+features*4+(6 if concrete else 0))
    else: label="POTENTIAL"; intent=min(77,52+features*4)
    credibility=min(90,62+(8 if item.get("author") else 0)+features*2)
    return {**item,"classification":label,"intent_score":intent,"credibility_score":credibility,"market_fit_score":95,"market":"north_cyprus","scanned_at":yr._now().isoformat(),"why":"North Cyprus YouTube viewer/reply with multilingual purchase, pricing, availability or engagement intent.","youtube_reply_context_rescue":bool(parent)}


def scan_comments_expanded():
    leads=_BASE_SCAN_COMMENTS(); db=yr.main.firestore_client(); now=yr._now().isoformat(); touched={}
    for lead in leads or []:
        try: yr._mark_notified(db,lead)
        except Exception: pass
        video_id=str(lead.get("video_id") or "")
        if video_id:
            current=touched.get(video_id); rank={"POTENTIAL":1,"WARM":2,"HOT":3}
            if current is None or rank.get(lead.get("classification"),0)>rank.get(current,0): touched[video_id]=lead.get("classification","")
    if db:
        for video_id,label in touched.items():
            try: db.collection(yr.WATCHLIST_COLLECTION).document(video_id).set({"last_lead_at":now,"last_lead_classification":label},merge=True)
            except Exception as exc: print("YOUTUBE_LEAD_ACTIVITY_WRITE_ERROR",video_id,exc)
    return leads


yr.load_watchlist=load_watchlist_ranked
yr._iter_comments=iter_comments_expanded
yr.classify_comment=classify_comment_expanded
yr.scan_comments=scan_comments_expanded
