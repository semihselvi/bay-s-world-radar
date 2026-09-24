import os
from datetime import datetime, timezone, timedelta

import requests

PULLPUSH_SUBMISSIONS="https://api.pullpush.io/reddit/search/submission/"
PULLPUSH_COMMENTS="https://api.pullpush.io/reddit/search/comment/"
ARCTIC_POSTS="https://arctic-shift.photon-reddit.com/api/posts/search"
ARCTIC_COMMENTS="https://arctic-shift.photon-reddit.com/api/comments/search"

QUERIES=[
    "North Cyprus buy property",
    "Northern Cyprus buy property",
    "North Cyprus looking to buy",
    "North Cyprus apartment buy",
    "North Cyprus villa buy",
    "North Cyprus property budget",
    "Iskele buy apartment",
    "Long Beach Cyprus buy apartment",
    "Kyrenia buy property",
    "Kuzey Kıbrıs ev almak",
    "Kuzey Kıbrıs daire almak",
    "İskele daire almak",
    "Северный Кипр купить квартиру",
    "Северный Кипр хочу купить",
    "Искеле купить квартиру",
    "Nordzypern Immobilie kaufen",
    "Cypr Północny kupić mieszkanie",
    "Chypre du Nord acheter appartement",
]

SUBREDDITS=[
    "NorthCyprus","cyprus","expats","ExpatFIRE","IWantOut",
    "realestateinvesting","realestate","AskTurkey","Turkey",
]

NC_TERMS=(
    "north cyprus","northern cyprus","north-cyprus","trnc","kktc",
    "kuzey kıbrıs","kuzey kibris","iskele","i̇skele","long beach",
    "kyrenia","girne","esentepe","famagusta","gazimağusa",
    "северный кипр","искеле","гирне","nordzypern","cypr północny","chypre du nord",
)
BUY_TERMS=(
    "looking to buy","want to buy","planning to buy","buy property","buy apartment","buy villa",
    "cash buyer","my budget","budget is","purchase property",
    "ev almak","daire almak","satın almak","bütçem","butcem",
    "хочу купить","купить квартиру","куплю","бюджет",
    "immobilie kaufen","wohnung kaufen","kupić","acheter",
)
RENT_TERMS=("rent","rental","kiralık","kirala","аренд","сниму","снять","miete")


def _get(url, params):
    headers={"User-Agent":"bay-s-north-cyprus-buyer-radar/1.0"}
    r=requests.get(url,params=params,headers=headers,timeout=18)
    r.raise_for_status()
    return r.json()


def _epoch_iso(value):
    try:
        return datetime.fromtimestamp(float(value),tz=timezone.utc).isoformat()
    except Exception:
        return ""


def _buyer_shaped(text):
    low=" ".join(str(text or "").split()).casefold()
    if not low:
        return False
    if not any(term in low for term in NC_TERMS):
        return False
    if any(term in low for term in RENT_TERMS) and not any(term in low for term in BUY_TERMS):
        return False
    return any(term in low for term in BUY_TERMS)


def _pullpush(query, comments=False, size=50):
    endpoint=PULLPUSH_COMMENTS if comments else PULLPUSH_SUBMISSIONS
    params={
        "q":query,
        "size":size,
        "sort":"desc",
        "sort_type":"created_utc",
        "after":"14d",
    }
    data=_get(endpoint,params)
    rows=[]
    for raw in data.get("data",[]) or []:
        if comments:
            text=str(raw.get("body") or "")
            post_id=str(raw.get("link_id") or "").replace("t3_","")
            comment_id=str(raw.get("id") or "")
            sub=str(raw.get("subreddit") or "")
            url=f"https://www.reddit.com/r/{sub}/comments/{post_id}/_/{comment_id}/" if sub and post_id and comment_id else ""
            title=f"Reddit comment | r/{sub}" if sub else "Reddit comment"
        else:
            title=str(raw.get("title") or "")
            text=" ".join(x for x in (title,str(raw.get("selftext") or "")) if x).strip()
            permalink=str(raw.get("permalink") or "")
            url=f"https://www.reddit.com{permalink}" if permalink.startswith("/") else str(raw.get("url") or "")
            sub=str(raw.get("subreddit") or "")
        if not _buyer_shaped(text):
            continue
        rows.append({
            "source":"Reddit PullPush",
            "source_bucket":"reddit_archive_pullpush_comments" if comments else "reddit_archive_pullpush_posts",
            "url":url,
            "title":title,
            "text":text[:8000],
            "published":_epoch_iso(raw.get("created_utc")),
            "author":str(raw.get("author") or ""),
            "reddit_subreddit":sub,
            "reddit_score":raw.get("score"),
            "reddit_id":str(raw.get("id") or ""),
            "discovery_query":query,
        })
    return rows


def _arctic_for_subreddit(subreddit, comments=False, limit=100):
    endpoint=ARCTIC_COMMENTS if comments else ARCTIC_POSTS
    params={"subreddit":subreddit,"limit":limit,"sort":"desc"}
    data=_get(endpoint,params)
    rows=[]
    cutoff=datetime.now(timezone.utc)-timedelta(days=14)
    for raw in data.get("data",[]) or []:
        published=_epoch_iso(raw.get("created_utc"))
        try:
            dt=datetime.fromisoformat(published)
            if dt < cutoff:
                continue
        except Exception:
            continue
        if comments:
            text=str(raw.get("body") or "")
            post_id=str(raw.get("link_id") or "").replace("t3_","")
            comment_id=str(raw.get("id") or "")
            url=f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/_/{comment_id}/" if post_id and comment_id else ""
            title=f"Reddit comment | r/{subreddit}"
        else:
            title=str(raw.get("title") or "")
            text=" ".join(x for x in (title,str(raw.get("selftext") or "")) if x).strip()
            permalink=str(raw.get("permalink") or "")
            url=f"https://www.reddit.com{permalink}" if permalink.startswith("/") else ""
        if not _buyer_shaped(text):
            continue
        rows.append({
            "source":"Reddit Arctic Shift",
            "source_bucket":"reddit_archive_arctic_comments" if comments else "reddit_archive_arctic_posts",
            "url":url,
            "title":title,
            "text":text[:8000],
            "published":published,
            "author":str(raw.get("author") or ""),
            "reddit_subreddit":subreddit,
            "reddit_score":raw.get("score"),
            "reddit_id":str(raw.get("id") or ""),
        })
    return rows


def collect_reddit_archive_buyers():
    if os.getenv("NC_REDDIT_ARCHIVE_ENABLED","1").strip()!="1":
        return []

    try:
        qlimit=max(1,min(len(QUERIES),int(os.getenv("NC_REDDIT_ARCHIVE_QUERY_LIMIT","10"))))
        slimit=max(1,min(len(SUBREDDITS),int(os.getenv("NC_REDDIT_ARCHIVE_SUBREDDIT_LIMIT","7"))))
    except ValueError:
        qlimit=10; slimit=7

    unique={}
    pullpush_ok=False
    for query in QUERIES[:qlimit]:
        for comments in (False,True):
            try:
                rows=_pullpush(query,comments=comments,size=50)
                pullpush_ok=True
                print(f"REDDIT_PULLPUSH query={query!r} kind={'comments' if comments else 'posts'} kept={len(rows)}")
                for item in rows:
                    key=item.get("url") or f"{item.get('reddit_id')}|{item.get('text','')[:120]}"
                    unique[key]=item
            except Exception as exc:
                print(f"REDDIT_PULLPUSH_ERROR query={query!r} kind={'comments' if comments else 'posts'} {type(exc).__name__}: {exc}")

    # Arctic Shift is both a fallback and a subreddit-local net for posts/comments
    # that broad keyword search may miss.
    for sub in SUBREDDITS[:slimit]:
        for comments in (False,True):
            try:
                rows=_arctic_for_subreddit(sub,comments=comments,limit=100)
                print(f"REDDIT_ARCTIC subreddit={sub!r} kind={'comments' if comments else 'posts'} kept={len(rows)}")
                for item in rows:
                    key=item.get("url") or f"{item.get('reddit_id')}|{item.get('text','')[:120]}"
                    unique[key]=item
            except Exception as exc:
                print(f"REDDIT_ARCTIC_ERROR subreddit={sub!r} kind={'comments' if comments else 'posts'} {type(exc).__name__}: {exc}")

    out=list(unique.values())
    out.sort(key=lambda x:x.get("published",""),reverse=True)
    print(f"REDDIT_ARCHIVE_COMPLETE unique={len(out)} pullpush_ok={int(pullpush_ok)}")
    return out


if __name__=="__main__":
    for row in collect_reddit_archive_buyers()[:20]:
        print(row)
