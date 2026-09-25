import hashlib
import os
import re
from datetime import datetime, timedelta, timezone

import requests

import main
import russian_social_review as rsr

SEARCH_URL="https://api.vc.ru/v2.10/search/posts"
CONTENT_URL="https://api.vc.ru/v2.8/content"
COMMENTS_URL="https://api.vc.ru/v2.5/comments"

S=requests.Session()
S.headers.update({
    "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Accept":"application/json",
    "Accept-Language":"ru-RU,ru;q=0.9,en;q=0.7",
})

QUERIES=[
    "Северный Кипр недвижимость",
    "Северный Кипр квартира",
    "Северный Кипр купить квартиру",
    "Северный Кипр переезд",
    "Искеле Северный Кипр",
    "Лонг Бич Северный Кипр",
    "Гирне недвижимость",
    "Северный Кипр рассрочка",
]

NC=re.compile(
    r"(северн\w*\s+кипр\w*|трск|искеле|лонг\s*бич|гирне|эсентепе|"
    r"фамагуст|газимагус|бафра|лапта|алсанджак|north(?:ern)?\s+cyprus)",
    re.I,
)
BUY=re.compile(
    r"(?:^|[\s.!?,;:])(?:я\s+|мы\s+)?(?:хочу|хотим|хотел(?:а|и)?\s+бы|планирую|планируем|собираюсь|собираемся)\s+.{0,50}(?:купить|приобрести)"
    r"|(?:^|[\s.!?,;:])куплю\s+(?:квартир|апартамент|дом|вилл|студи|недвиж)"
    r"|(?:^|[\s.!?,;:])ищу.{0,90}(?:для\s+покупки|на\s+покупку|чтобы\s+купить)"
    r"|(?:мой|наш)\s+бюджет.{0,110}(?:квартир|апартамент|дом|вилл|недвиж|покуп)"
    r"|подскажите.{0,110}(?:где|что|какую|какой).{0,90}(?:купить|покуп)"
    r"|что\s+можно\s+купить.{0,100}(?:за|на\s+бюджет)"
    r"|нужн[аоы]?.{0,80}(?:квартир|вилл|дом).{0,80}(?:купить|покуп)",
    re.I|re.S,
)
PROPERTY=re.compile(r"(квартир|апартамент|дом|вилл|студи|недвижимост|жиль[её]|объект|1\s*\+\s*[01]|2\s*\+\s*[01]|3\s*\+\s*[01])",re.I)
SELLER=re.compile(r"(агентств|риелтор|риэлтор|застройщик|предлагаем|наш\s+проект|наша\s+компания|обращайтесь|пишите\s+в\s+лич|подбер[её]м|прода[её]м)",re.I)
RENT=re.compile(r"(аренд|снять|сниму|снимать|посуточ|сдам|сдается|сда[её]тся)",re.I)
NOTIFIED="bay_s_vcru_comment_notified"


def _now():
    return datetime.now(timezone.utc)

def _post_id(url):
    path=str(url or "").split("?")[0].rstrip("/")
    for part in reversed(path.split("/")):
        m=re.match(r"(\d{4,})(?:-|$)",part)
        if m: return m.group(1)
    return ""

def _search(query,limit=30):
    try:
        r=S.get(SEARCH_URL,params={"markdown":"false","q":query},timeout=25)
        print("VCRU_SEARCH_HTTP",r.status_code,len(r.text),repr(query))
        if r.status_code!=200: return []
        data=r.json()
        items=((data.get("result") or {}).get("items") or [])
        out=[]
        for item in items:
            if item.get("type") not in ("",None,"entry"): continue
            d=item.get("data") or {}
            url=str(d.get("url") or "")
            pid=str(d.get("id") or _post_id(url))
            if url and pid:
                out.append({"id":pid,"url":url,"search_data":d})
            if len(out)>=limit: break
        print("VCRU_QUERY",repr(query),"items",len(items),"kept",len(out))
        return out
    except Exception as exc:
        print("VCRU_SEARCH_ERROR",repr(query),type(exc).__name__,str(exc)[:180])
        return []

def _content(post):
    try:
        r=S.get(CONTENT_URL,params={"id":post["id"],"markdown":"false"},timeout=20)
        if r.status_code!=200: return post
        data=r.json().get("result") or {}
        row=dict(post)
        row.update({
            "title":str(data.get("title") or ""),
            "description":str(data.get("description") or ""),
            "date":data.get("date"),
            "is_comments_enabled":data.get("isCommentsEnabled",True),
        })
        return row
    except Exception as exc:
        print("VCRU_CONTENT_ERROR",post.get("id"),type(exc).__name__)
        return post

def _comments(post):
    if post.get("is_comments_enabled") is False: return []
    try:
        r=S.get(COMMENTS_URL,params={
            "sorting":"date",
            "contentId":post["id"],
            "firstLoad":"true",
        },timeout=22)
        if r.status_code!=200:
            # Older API examples use hotness; retry if date sorting is unsupported.
            r=S.get(COMMENTS_URL,params={
                "sorting":"hotness",
                "contentId":post["id"],
                "firstLoad":"true",
            },timeout=22)
        print("VCRU_COMMENTS_HTTP",post["id"],r.status_code,len(r.text))
        if r.status_code!=200: return []
        return ((r.json().get("result") or {}).get("items") or [])
    except Exception as exc:
        print("VCRU_COMMENTS_ERROR",post.get("id"),type(exc).__name__)
        return []

def _comment_row(raw,post):
    author=raw.get("author") or {}
    cid=str(raw.get("id") or "")
    ts=raw.get("date")
    try: published=datetime.fromtimestamp(int(ts),timezone.utc)
    except Exception: published=None
    text=str(raw.get("text") or "").strip()
    return {
        "id":cid,
        "author":str(author.get("name") or author.get("id") or ""),
        "author_id":str(author.get("id") or ""),
        "text":text,
        "published":published,
        "url":f"{post.get('url','').split('?')[0]}?comment={cid}" if cid else post.get("url",""),
    }

def _score(comment,context):
    text=" ".join(str(comment.get("text") or "").split())
    if len(text)<20 or not NC.search(context):
        return None
    if RENT.search(text) or SELLER.search(text):
        return None
    if not PROPERTY.search(text) and not BUY.search(text):
        return None
    if not BUY.search(text):
        return None
    s=84
    if re.search(r"(?:мой|наш)\s+бюджет|£|€|\$|₽|\b\d{5,}\b",text,re.I): s+=6
    if re.search(r"искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак",text,re.I): s+=4
    if re.search(r"(?:прие(?:ду|дем)|в\s+октябре|в\s+ноябре|в\s+декабре|просмотр|посмотреть)",text,re.I): s+=4
    return min(s,98)

def _seen(db,key):
    if not db: return False
    try: return db.collection(NOTIFIED).document(key).get().exists
    except Exception: return False

def _mark(db,key,item):
    if not db: return
    try:
        db.collection(NOTIFIED).document(key).set({
            "notified_at":_now().isoformat(),
            "url":item.get("url",""),
            "author":item.get("author",""),
            "text":item.get("text","")[:1000],
        },merge=True)
    except Exception: pass

def run():
    posts={}
    for q in QUERIES:
        for p in _search(q):
            posts.setdefault(p["id"],p)

    enriched=[_content(p) for p in list(posts.values())[:100]]
    cutoff=_now()-timedelta(days=int(os.getenv("VCRU_COMMENT_LOOKBACK_DAYS","30")))
    db=main.firestore_client()
    leads=[]; comments_seen=0; fresh_comments=0; review_saved=0

    for post in enriched:
        context=f"{post.get('title','')} {post.get('description','')}"
        if not NC.search(context):
            continue
        for raw in _comments(post):
            comments_seen+=1
            com=_comment_row(raw,post)
            if not com["text"] or not com["published"] or com["published"]<cutoff:
                continue
            fresh_comments+=1
            score=_score(com,context)
            if not score:
                if rsr.save("vc.ru",com["text"],com["url"],com["author"],context):
                    review_saved+=1
                continue
            basis=f"vc|{post['id']}|{com['id']}|{com['author_id']}|{com['text'][:250]}"
            key=hashlib.sha1(basis.encode()).hexdigest()
            if _seen(db,key): continue
            com["intent"]=score
            com["post_title"]=post.get("title","")
            leads.append(com)
            _mark(db,key,com)

    leads.sort(key=lambda x:x["intent"],reverse=True)
    print(f"VCRU_RADAR_COMPLETE posts={len(posts)} enriched={len(enriched)} comments={comments_seen} fresh_comments={fresh_comments} leads={len(leads)} review_saved={review_saved}")
    if leads:
        lines=[f"🟢 VC.RU COMMENT RADAR | {len(leads)} BUYER ADAYI"]
        for x in leads[:10]:
            excerpt=" ".join(x.get("text","").split())[:240]
            lines += [
                "",
                f"Intent {x['intent']} | @{x.get('author') or 'kullanıcı'}",
                f"💬 {excerpt}",
                x["url"],
            ]
        main.notify_telegram("\n".join(lines))

if __name__=="__main__":
    run()
