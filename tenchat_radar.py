import hashlib
import os
import re
from urllib.parse import quote_plus, urljoin, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

import main

UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36"
S=requests.Session()
S.headers.update({"User-Agent":UA,"Accept-Language":"ru-RU,ru;q=0.9,en;q=0.7"})

QUERIES=[
    "Северный Кипр недвижимость",
    "Северный Кипр купить квартиру",
    "Северный Кипр Искеле недвижимость",
    "Северный Кипр Гирне недвижимость",
    "Северный Кипр переезд квартира",
    "Лонг Бич Северный Кипр недвижимость",
    "Северный Кипр рассрочка квартира",
    "Северный Кипр бюджет квартира",
]

NC=re.compile(r"(северн\w*\s+кипр\w*|искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак)",re.I)
BUY=re.compile(
    r"(?:^|[\s.!?,;:])(?:я\s+)?(?:хочу|хотел(?:а)?\s+бы|планирую|собираюсь)\s+(?:себе\s+)?купить"
    r"|(?:^|[\s.!?,;:])куплю\s+(?:квартир|вилл|дом|недвиж)"
    r"|(?:^|[\s.!?,;:])ищу.{0,90}(?:для\s+покупки|чтобы\s+купить|купить\s+(?:квартир|вилл|дом|недвиж))"
    r"|(?:мой|наш)\s+бюджет.{0,100}(?:квартир|вилл|дом|недвиж|покуп)"
    r"|подскажите.{0,100}(?:где|что|какую|какой).{0,80}(?:купить|покуп)"
    r"|нужн[аоы]?.{0,80}(?:квартир|вилл|дом).{0,80}(?:купить|покуп)",
    re.I|re.S,
)
SELL=re.compile(r"(прода[её]тся|продаю|агентств|риелтор|риэлтор|застройщик|предлагаем|цена\s+от|стоимость\s+от|рассрочк|инвестиционн|доходност|пишите\s+в\s+лич|подбер[её]м)",re.I)
SEEN="bay_s_tenchat_seen_comments"


def _valid(url):
    try:
        h=urlparse(url).netloc.lower()
        return h=="tenchat.ru" or h.endswith(".tenchat.ru")
    except Exception:
        return False

def rss(query):
    url="https://www.bing.com/search?q="+quote_plus("site:tenchat.ru/media "+query)+"&format=rss"
    out=[]
    try:
        r=S.get(url,timeout=20); r.raise_for_status()
        root=ET.fromstring(r.content)
        for it in root.findall(".//item"):
            def get(tag):
                el=it.find(tag)
                return "".join(el.itertext()).strip() if el is not None else ""
            u=get("link")
            if _valid(u) and "/media/" in u:
                out.append({"url":u.split("?")[0],"title":get("title"),"text":get("description"),"provider":"bing_rss"})
    except Exception as exc: print("TENCHAT_RSS_ERROR",type(exc).__name__)
    return out

def _extract_comment_nodes(soup):
    nodes=[]; seen_ids=set()
    selectors=(
        '[class*="comment"]',
        '[data-testid*="comment"]',
        '[data-qa*="comment"]',
        '[data-test*="comment"]',
    )
    for sel in selectors:
        try:
            for node in soup.select(sel):
                ident=id(node)
                if ident in seen_ids: continue
                seen_ids.add(ident); nodes.append(node)
        except Exception: pass
    return nodes

def comments_from_page(soup,url):
    out=[]; seen=set()
    for node in _extract_comment_nodes(soup):
        txt=" ".join(node.stripped_strings).strip()
        if len(txt)<18 or len(txt)>3200: continue
        # Avoid treating the whole comment section/container as one comment.
        if txt.count("\n")>10: continue
        key=txt.lower()
        if key in seen: continue
        seen.add(key)
        author=""
        try:
            a=node.find("a",href=re.compile(r"^/[^/]+$|/profile|/user",re.I))
            if a: author=" ".join(a.stripped_strings).strip()[:120]
        except Exception: pass
        cid=""
        for attr in ("data-id","data-comment-id","id"):
            val=str(node.get(attr) or "")
            m=re.search(r"(\d{3,})",val)
            if m: cid=m.group(1); break
        curl=url+("#comment-"+cid if cid else "")
        out.append({"text":txt[:3000],"author":author,"url":curl,"comment_id":cid})
    return out

def enrich(row):
    try:
        r=S.get(row["url"],timeout=22)
        print("TENCHAT_PAGE",r.status_code,len(r.text),row["url"])
        if r.status_code!=200: return row
        soup=BeautifulSoup(r.text,"html.parser")
        pieces=[]
        for attrs in ({"property":"og:description"},{"name":"description"}):
            m=soup.find("meta",attrs=attrs)
            if m and m.get("content"): pieces.append(m.get("content"))
        for sel in ("article","main",'[class*="media"]','[class*="post"]'):
            node=soup.select_one(sel)
            if node:
                pieces.append(" ".join(node.stripped_strings)[:10000]); break
        core=" ".join(x for x in pieces if x)
        row=dict(row)
        row["page_core"]=core[:12000]
        row["comments"]=comments_from_page(soup,row["url"])
        if soup.title: row["title"]=soup.title.get_text(" ",strip=True)[:300]
        return row
    except Exception as exc:
        print("TENCHAT_ENRICH_ERROR",type(exc).__name__)
        return row

def score_comment(text,context):
    text=" ".join(str(text or "").split())
    if len(text)<24 or not NC.search(context): return None
    if SELL.search(text) or not BUY.search(text): return None
    score=84
    if re.search(r"(?:мой|наш)\s+бюджет|£|€|\$|\b\d{4,}\b",text,re.I): score+=6
    if re.search(r"искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак",text,re.I): score+=4
    if re.search(r"прие(?:ду|дем)|в\s+октябре|в\s+ноябре|просмотр|посмотреть",text,re.I): score+=4
    return min(score,98)

def _key(row,com):
    basis=f"{row.get('url','')}|{com.get('comment_id','')}|{com.get('author','')}|{com.get('text','')[:300]}"
    return hashlib.sha1(basis.encode()).hexdigest()

def run():
    unique={}
    for q in QUERIES:
        rows=rss(q)
        print(f"TENCHAT_QUERY {q!r} raw={len(rows)}")
        for row in rows:
            key=row.get("url","").rstrip("/")
            if key and key not in unique: unique[key]=row
    enriched=[enrich(x) for x in list(unique.values())[:100]]
    db=main.firestore_client(); leads=[]; comment_count=0
    for row in enriched:
        context=f"{row.get('title','')} {row.get('page_core','')} {row.get('text','')}"
        for com in row.get("comments",[]) or []:
            comment_count+=1
            score=score_comment(com.get("text",""),context)
            if not score: continue
            key=_key(row,com)
            seen=False
            if db:
                try: seen=db.collection(SEEN).document(key).get().exists
                except Exception: pass
            if seen: continue
            lead={"intent":score,"author":com.get("author",""),"text":com.get("text",""),"url":com.get("url") or row.get("url",""),"title":row.get("title","")}
            leads.append(lead)
            if db:
                try: db.collection(SEEN).document(key).set({"seen_at":main.now_utc().isoformat(),"url":lead["url"],"author":lead["author"]},merge=True)
                except Exception: pass
    leads.sort(key=lambda x:x["intent"],reverse=True)
    print(f"TENCHAT_RADAR_COMPLETE posts={len(unique)} enriched={len(enriched)} comments={comment_count} leads={len(leads)}")
    if leads:
        lines=[f"🟣 TENCHAT COMMENT RADAR | {len(leads)} BUYER ADAYI"]
        for x in leads[:10]:
            excerpt=" ".join(str(x.get("text","")).split())[:230]
            lines += ["",f"Intent {x['intent']} | @{x.get('author') or 'kullanıcı'}",f"💬 {excerpt}",x["url"]]
        main.notify_telegram("\n".join(lines))

if __name__=="__main__":
    run()
