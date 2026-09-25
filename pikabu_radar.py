import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urljoin, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

import main
import russian_social_review as rsr

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36"
S=requests.Session()
S.headers.update({"User-Agent":UA,"Accept-Language":"ru-RU,ru;q=0.9,en;q=0.7"})

QUERIES=[
    "Северный Кипр недвижимость",
    "Северный Кипр купить квартиру",
    "Северный Кипр хочу купить",
    "Северный Кипр переезд недвижимость",
    "Искеле купить квартиру",
    "Лонг Бич Северный Кипр квартира",
    "Гирне купить квартиру",
    "Северный Кипр бюджет квартира",
]

NC=re.compile(r"(северн\w*\s+кипр\w*|искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак|north(?:ern)?\s+cyprus)",re.I)
BUY=re.compile(
    r"(?:^|[\s.!?,;:])(?:я\s+)?(?:хочу|хотел(?:а)?\s+бы|планирую|собираюсь)\s+(?:себе\s+)?купить"
    r"|(?:^|[\s.!?,;:])куплю\s+(?:квартир|вилл|дом|недвиж)"
    r"|(?:^|[\s.!?,;:])ищу.{0,90}(?:для\s+покупки|чтобы\s+купить|купить\s+(?:квартир|вилл|дом|недвиж))"
    r"|(?:мой|наш)\s+бюджет.{0,100}(?:квартир|вилл|дом|недвиж|покуп)"
    r"|подскажите.{0,100}(?:где|что|какую|какой).{0,80}(?:купить|покуп)"
    r"|нужн[аоы]?.{0,80}(?:квартир|вилл|дом).{0,80}(?:купить|покуп)",
    re.I|re.S,
)
SELL=re.compile(r"(прода[её]тся|продаю|на\s+продажу|агентств|риелтор|риэлтор|застройщик|предлагаем|цена\s+от|стоимость\s+от|рассрочк|инвестиционн|доходност|почему\s+стоит\s+купить|пишите\s+в\s+лич|подбер[её]м)",re.I)
NOTIFIED="bay_s_pikabu_notified"


def _now(): return datetime.now(timezone.utc)

def _valid(url):
    try:
        h=urlparse(url).netloc.lower()
        return h=="pikabu.ru" or h.endswith(".pikabu.ru")
    except Exception:
        return False

def _story_id(url):
    m=re.search(r"_(\d+)(?:[/?#]|$)",str(url))
    return m.group(1) if m else ""

def _parse_dt(value):
    if not value: return None
    s=str(value).strip().replace("Z","+00:00")
    for fn in (
        lambda: datetime.fromisoformat(s),
        lambda: datetime.strptime(s,"%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc),
        lambda: parsedate_to_datetime(s),
    ):
        try:
            dt=fn()
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception: pass
    return None

def _parse_search_html(text,provider):
    soup=BeautifulSoup(text,"html.parser"); out=[]
    for a in soup.find_all("a",href=True):
        href=urljoin("https://pikabu.ru",a.get("href"))
        if not _valid(href) or "/story/" not in href or not _story_id(href): continue
        node=a
        for _ in range(3):
            if getattr(node,"parent",None): node=node.parent
        body=" ".join(getattr(node,"stripped_strings",[]) or [])[:3500]
        title=" ".join(a.stripped_strings)[:300]
        out.append({"url":href.split("?")[0],"title":title,"text":body,"provider":provider})
    return out

def native(query):
    urls=[
        "https://pikabu.ru/search?q="+quote_plus(query),
        "https://pikabu.ru/search?st="+quote_plus(query),
    ]
    out=[]
    for url in urls:
        try:
            r=S.get(url,timeout=25)
            print("PIKABU_NATIVE",r.status_code,len(r.text),url.split("?")[0])
            if r.status_code==200: out += _parse_search_html(r.text,"pikabu_native")
        except Exception as exc: print("PIKABU_NATIVE_ERROR",type(exc).__name__)
    return out

def rss(query):
    url="https://www.bing.com/search?q="+quote_plus("site:pikabu.ru/story "+query)+"&format=rss"
    out=[]
    try:
        r=S.get(url,timeout=20); r.raise_for_status()
        root=ET.fromstring(r.content)
        for it in root.findall(".//item"):
            def get(tag):
                el=it.find(tag)
                return "".join(el.itertext()).strip() if el is not None else ""
            u=get("link")
            if _valid(u) and "/story/" in u and _story_id(u):
                out.append({"url":u.split("?")[0],"title":get("title"),"text":get("description"),"published":get("pubDate"),"provider":"bing_rss"})
    except Exception as exc: print("PIKABU_RSS_ERROR",type(exc).__name__)
    return out

def _legacy_comments(story_id):
    out=[]
    if not story_id: return out
    try:
        r=S.get("https://pikabu.ru/generate_xml_comm.php",params={"id":story_id},timeout=18)
        print("PIKABU_LEGACY_COMMENTS",story_id,r.status_code,len(r.text))
        if r.status_code!=200 or not r.text.strip(): return out
        try:
            root=ET.fromstring(r.content)
        except Exception:
            return out
        for node in root.iter("comment"):
            text=" ".join("".join(node.itertext()).split())
            if not text: continue
            out.append({
                "comment_id":str(node.attrib.get("id") or ""),
                "author":str(node.attrib.get("nick") or ""),
                "published":str(node.attrib.get("date") or ""),
                "text":text[:3000],
            })
    except Exception as exc: print("PIKABU_LEGACY_COMMENT_ERROR",story_id,type(exc).__name__)
    return out

def _html_comments(soup):
    out=[]; seen=set()
    selectors=('[data-role*="comment"]','[data-id*="comment"]','[class*="comment"]')
    nodes=[]
    for sel in selectors:
        try: nodes += soup.select(sel)
        except Exception: pass
    for node in nodes:
        txt=" ".join(node.stripped_strings).strip()
        if len(txt)<18 or len(txt)>3200: continue
        key=txt.lower()
        if key in seen: continue
        seen.add(key)
        author=""
        try:
            a=node.find("a",href=re.compile(r"/profile/|/@" ,re.I))
            if a: author=" ".join(a.stripped_strings).strip()[:120]
        except Exception: pass
        published=""
        try:
            t=node.find("time")
            if t: published=str(t.get("datetime") or t.get("title") or t.get_text(" ",strip=True))
        except Exception: pass
        cid=""
        for attr in ("data-id","data-comment-id","id"):
            val=str(node.get(attr) or "")
            m=re.search(r"(\d{4,})",val)
            if m: cid=m.group(1); break
        out.append({"comment_id":cid,"author":author,"published":published,"text":txt[:3000]})
    return out

def enrich(row):
    try:
        r=S.get(row["url"],timeout=22)
        if r.status_code!=200: return row
        soup=BeautifulSoup(r.text,"html.parser")
        title=soup.title.get_text(" ",strip=True)[:300] if soup.title else row.get("title","")
        pieces=[]
        for attrs in ({"property":"og:description"},{"name":"description"}):
            m=soup.find("meta",attrs=attrs)
            if m and m.get("content"): pieces.append(m.get("content"))
        for sel in ("article","main",'[class*="story__content"]','[class*="story"]'):
            node=soup.select_one(sel)
            if node:
                pieces.append(" ".join(node.stripped_strings)[:10000]); break
        core=" ".join(x for x in pieces if x)
        published=row.get("published","")
        try:
            t=soup.find("time")
            if t: published=str(t.get("datetime") or t.get("title") or published)
        except Exception: pass
        comments=_legacy_comments(_story_id(row["url"]))
        if not comments: comments=_html_comments(soup)
        row=dict(row); row.update({"title":title,"page_core":core[:12000],"published":published,"comments":comments})
    except Exception as exc:
        print("PIKABU_ENRICH_ERROR",type(exc).__name__)
    return row

def _score(text,context):
    text=str(text or "").strip(); context=str(context or "")
    if len(text)<24 or not NC.search(context): return None
    if SELL.search(text) or not BUY.search(text): return None
    score=84
    if re.search(r"(?:мой|наш)\s+бюджет|£|€|\$|\b\d{4,}\b",text,re.I): score+=6
    if re.search(r"искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак",text,re.I): score+=4
    if re.search(r"прие(?:ду|дем)|в\s+октябре|в\s+ноябре|просмотр|посмотреть",text,re.I): score+=4
    return min(score,98)

def _seen(db,key):
    if not db: return False
    try: return db.collection(NOTIFIED).document(key).get().exists
    except Exception: return False

def _mark(db,key,item):
    if not db: return
    try: db.collection(NOTIFIED).document(key).set({"notified_at":_now().isoformat(),"url":item.get("url",""),"author":item.get("author","")},merge=True)
    except Exception: pass

def run():
    unique={}
    for q in QUERIES:
        rows=native(q)+rss(q)
        print(f"PIKABU_QUERY {q!r} raw={len(rows)}")
        for row in rows:
            key=row.get("url","").split("?")[0].rstrip("/")
            if key and key not in unique: unique[key]=row
    enriched=[enrich(x) for x in list(unique.values())[:100]]
    cutoff=_now()-timedelta(days=int(os.getenv("PIKABU_LOOKBACK_DAYS","30")))
    db=main.firestore_client(); leads=[]; comments_seen=0
    for row in enriched:
        context=f"{row.get('title','')} {row.get('page_core','')} {row.get('text','')}"
        # Direct first-person buyer posts are allowed only when dated and recent.
        post_dt=_parse_dt(row.get("published"))
        ps=_score(f"{row.get('title','')} {row.get('page_core','')}",context)
        if ps and post_dt and post_dt>=cutoff:
            key=hashlib.sha1(("post|"+row.get("url","")).encode()).hexdigest()
            if not _seen(db,key):
                leads.append({"intent":ps,"kind":"POST","author":"","text":row.get("page_core","")[:500],"url":row.get("url",""),"title":row.get("title","")})
                _mark(db,key,leads[-1])
        for com in row.get("comments",[]) or []:
            comments_seen+=1
            dt=_parse_dt(com.get("published"))
            if not dt or dt<cutoff: continue
            cs=_score(com.get("text",""),context)
            if not cs:
                rsr.save("pikabu",com.get("text",""),row.get("url",""),com.get("author",""),row.get("title",""))
                continue
            url=row.get("url","")
            if com.get("comment_id"): url=url+"#comment-"+com["comment_id"]
            basis=f"{row.get('url','')}|{com.get('comment_id','')}|{com.get('author','')}|{com.get('text','')[:240]}"
            key=hashlib.sha1(basis.encode()).hexdigest()
            if _seen(db,key): continue
            lead={"intent":cs,"kind":"COMMENT","author":com.get("author",""),"text":com.get("text",""),"url":url,"title":row.get("title","")}
            leads.append(lead); _mark(db,key,lead)
    leads.sort(key=lambda x:x["intent"],reverse=True)
    print(f"PIKABU_RADAR_COMPLETE stories={len(unique)} enriched={len(enriched)} comments={comments_seen} leads={len(leads)}")
    if leads:
        lines=[f"🟠 PIKABU RADAR | {len(leads)} BUYER ADAYI"]
        for x in leads[:10]:
            excerpt=" ".join(str(x.get("text","")).split())[:230]
            lines += ["",f"{x['kind']} | Intent {x['intent']} | @{x.get('author') or 'kullanıcı'}",f"💬 {excerpt}",x["url"]]
        main.notify_telegram("\n".join(lines))

if __name__=="__main__":
    run()
