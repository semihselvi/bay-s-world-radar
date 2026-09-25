import hashlib
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, unquote, urlparse, parse_qs, urljoin
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

import main
import russian_social_review as rsr

SEARCH_URL="https://otvet.mail.ru/go-proxy/answer_json"
S=requests.Session()
S.headers.update({
    "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36",
    "Referer":"https://otvet.mail.ru/",
    "Accept-Language":"ru-RU,ru;q=0.9,en;q=0.7",
})

QUERIES=[
    "Северный Кипр купить квартиру",
    "Северный Кипр хочу купить",
    "Северный Кипр недвижимость",
    "Северный Кипр переезд жилье",
    "Северный Кипр квартира",
    "Искеле купить квартиру",
    "Лонг Бич купить квартиру",
    "Гирне купить квартиру",
    "Северный Кипр бюджет квартира",
    "Северный Кипр рассрочка квартира",
    "Северный Кипр купить дом",
    "Северный Кипр купить виллу",
]

NC=re.compile(
    r"(северн\w*\s+кипр\w*|турецк\w*\s+кипр\w*|трск|искеле|лонг\s*бич|гирне|"
    r"эсентепе|фамагуст|газимагус|бафра|лапта|алсанджак|north(?:ern)?\s+cyprus)",
    re.I,
)
PROPERTY=re.compile(r"(квартир|апартамент|дом|вилл|студи|недвижимост|жиль[её]|объект|таунхаус)",re.I)
BUY_STRICT=re.compile(
    r"(?:^|[\s.!?,;:])(?:я\s+|мы\s+)?(?:хочу|хотим|хотел(?:а|и)?\s+бы|планирую|планируем|собираюсь|собираемся)\s+.{0,45}(?:купить|приобрести)"
    r"|(?:^|[\s.!?,;:])куплю\s+(?:квартир|апартамент|дом|вилл|студи|недвиж)"
    r"|(?:^|[\s.!?,;:])ищу.{0,90}(?:для\s+покупки|чтобы\s+купить|на\s+покупку)"
    r"|(?:мой|наш)\s+бюджет.{0,120}(?:квартир|апартамент|дом|вилл|недвиж|покуп)"
    r"|(?:продаю|продать|поменять|обменять).{0,120}(?:жиль[её]|квартир|дом).{0,180}(?:кипр|переех|купить|приобрести)"
    r"|(?:хочу|хотим|планирую|планируем|собираюсь|собираемся).{0,100}(?:переех|жить).{0,120}(?:кипр).{0,160}(?:купить|жиль[её]|квартир|дом)",
    re.I|re.S,
)
REQUEST=re.compile(
    r"(как\s+(?:лучше\s+)?купить|где\s+купить|что\s+можно\s+купить|"
    r"какую\s+(?:квартиру|недвижимость|виллу)|какой\s+(?:дом|район)|"
    r"подскажите.{0,100}(?:купить|квартир|вилл|дом|недвиж)|"
    r"есть\s+ли.{0,100}(?:квартир|вилл|дом).{0,80}(?:на\s+продаж|купить))",
    re.I|re.S,
)
RENT=re.compile(r"(аренд|снять|сниму|снимать|посуточ|сдам|сдается|сда[её]тся)",re.I)
SELLER=re.compile(r"(агентств|риелтор|риэлтор|застройщик|предлагаем|наша\s+компания|прода[её]м\s+объект|обращайтесь|пишите\s+в\s+лич)",re.I)
NOISE=re.compile(r"(политик|признать\s+северный\s+кипр|оккупац|войн|турция.{0,50}греци|границ\w*.{0,50}государств)",re.I)

COLLECTION="bay_s_mailru_answers_notified"

def _now():
    return datetime.now(timezone.utc)

def _unwrap_mailru(href):
    href=str(href or "").strip()
    if href.startswith("//"): href="https:"+href
    if href.startswith("/"): href=urljoin("https://otvet.mail.ru",href)
    try:
        host=urlparse(href).netloc.lower()
        if host in ("otvet.mail.ru","www.otvet.mail.ru"):
            return href
        q=parse_qs(urlparse(href).query)
        for key in ("url","u","target","uddg"):
            for val in q.get(key,[]):
                val=unquote(val)
                if urlparse(val).netloc.lower() in ("otvet.mail.ru","www.otvet.mail.ru"):
                    return val
    except Exception:
        pass
    return ""

def _native_search(query):
    out=[]
    urls=[
        "https://otvet.mail.ru/search?q="+quote_plus(query),
        "https://otvet.mail.ru/search/"+quote_plus(query),
    ]
    for url in urls:
        try:
            r=S.get(url,timeout=12)
            print("MAILRU_NATIVE_HTTP",r.status_code,len(r.text),repr(query),url.split("?")[0])
            if r.status_code!=200:
                continue
            soup=BeautifulSoup(r.text,"html.parser")
            for a in soup.find_all("a",href=True):
                link=_unwrap_mailru(a.get("href"))
                m=re.search(r"otvet\.mail\.ru/question/(\d+)",link)
                if not m:
                    continue
                title=" ".join(a.stripped_strings).strip()
                node=a
                for _ in range(2):
                    if getattr(node,"parent",None): node=node.parent
                body=" ".join(getattr(node,"stripped_strings",[]) or [])[:1800]
                out.append({
                    "id":m.group(1),
                    "question":title or body[:300],
                    "qstcomment":body,
                    "time":None,
                    "time_ago":None,
                    "count":None,
                    "catname":"",
                    "author":{},
                    "_provider":"mailru_native",
                })
        except Exception as exc:
            print("MAILRU_NATIVE_ERROR",repr(query),type(exc).__name__,str(exc)[:120])
    dedup={}
    for row in out:
        if row.get("id"): dedup.setdefault(str(row["id"]),row)
    print("MAILRU_NATIVE_QUERY",repr(query),"results",len(dedup))
    return list(dedup.values())

def _question_api(qid):
    if not qid: return {}
    try:
        r=S.get("https://otvet.mail.ru/api/v2/question",params={
            "ajax_id":0,"qid":qid,"sort":1,"n":20,"p":0
        },timeout=12)
        print("MAILRU_QUESTION_API",qid,r.status_code,len(r.text))
        if r.status_code!=200:
            return {}
        data=r.json()
        return data if isinstance(data,dict) else {}
    except Exception as exc:
        print("MAILRU_QUESTION_API_ERROR",qid,type(exc).__name__)
        return {}

def _json_text(obj):
    parts=[]
    def walk(x):
        if isinstance(x,dict):
            for k,v in x.items():
                if str(k).lower() in ("question","qtext","qstcomment","qcomment","text","body","content","title") and isinstance(v,str):
                    if v.strip(): parts.append(v.strip())
                else:
                    walk(v)
        elif isinstance(x,list):
            for y in x: walk(y)
    walk(obj)
    return " ".join(dict.fromkeys(parts))[:12000]

def _bing_rss(query):
    url="https://www.bing.com/search?q="+quote_plus("site:otvet.mail.ru/question "+query)+"&format=rss"
    out=[]
    try:
        r=S.get(url,timeout=20)
        print("MAILRU_BING_HTTP",r.status_code,len(r.text),repr(query))
        if r.status_code!=200:
            return out
        root=ET.fromstring(r.content)
        for it in root.findall(".//item"):
            def get(tag):
                el=it.find(tag)
                return "".join(el.itertext()).strip() if el is not None else ""
            link=get("link")
            m=re.search(r"otvet\.mail\.ru/question/(\d+)",link)
            if not m:
                continue
            out.append({
                "id":m.group(1),
                "question":get("title"),
                "qstcomment":get("description"),
                "time":None,
                "time_ago":None,
                "count":None,
                "catname":"",
                "author":{},
                "_provider":"bing_rss",
            })
        print("MAILRU_BING_QUERY",repr(query),"results",len(out))
    except Exception as exc:
        print("MAILRU_BING_ERROR",repr(query),type(exc).__name__,str(exc)[:160])
    return out

def _search(query):
    days=float(os.getenv("MAILRU_LOOKBACK_DAYS","7"))
    params={
        "num":50,
        "sf":0,
        "q":query,
        "sort":"date",
        "zdts":-int(days*86400),
        "question_only":1,
    }
    try:
        r=S.get(SEARCH_URL,params=params,timeout=5)
        print("MAILRU_HTTP",r.status_code,len(r.text),query)
        if r.status_code!=200:
            return []
        data=r.json()
        rows=data.get("results",[]) if isinstance(data,dict) else []
        print("MAILRU_QUERY",repr(query),"results",len(rows),"keys",list(data.keys())[:12] if isinstance(data,dict) else [])
        return rows
    except Exception as exc:
        print("MAILRU_SEARCH_ERROR",repr(query),type(exc).__name__,str(exc)[:180])
        return []

def _row(row):
    qid=str(row.get("id") or "").strip()
    author=row.get("author") or {}
    title=str(row.get("question") or row.get("qtext") or "").strip()
    text=str(row.get("qstcomment") or row.get("qcomment") or "").strip()
    ts=row.get("time")
    try:
        published=datetime.fromtimestamp(int(ts),timezone.utc).isoformat() if ts else ""
    except Exception:
        published=""
    return {
        "id":qid,
        "title":title,
        "text":text,
        "author":str(author.get("nick") or author.get("name") or author.get("id") or ""),
        "author_id":str(author.get("id") or ""),
        "published":published,
        "age_seconds":row.get("time_ago"),
        "answer_count":row.get("count"),
        "category":str(row.get("catname") or ""),
        "url":f"https://otvet.mail.ru/question/{qid}" if qid else "",
    }

def _score(item):
    text=f"{item.get('title','')} {item.get('text','')}"
    if not NC.search(text) or not PROPERTY.search(text):
        return None
    if RENT.search(text) or SELLER.search(text) or NOISE.search(text):
        return None
    strong=bool(BUY_STRICT.search(text))
    request=bool(REQUEST.search(text))
    personal=bool(re.search(r"\b(?:я|мы|мой|моя|наша|наш|хочу|хотим|планирую|планируем|собираюсь|собираемся|ищу|куплю)\b",text,re.I))
    if not strong and not (request and personal):
        return None
    score=82 if strong else 74
    if re.search(r"(?:мой|наш)\s+бюджет|£|€|\$|₽|\b\d{5,}\b",text,re.I): score+=8
    if re.search(r"искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак",text,re.I): score+=4
    if re.search(r"(?:в\s+октябре|в\s+ноябре|в\s+декабре|в\s+следующем\s+месяце|скоро\s+приед|прие(?:ду|дем)|просмотр)",text,re.I): score+=4
    return min(score,98)

def _seen(db,key):
    if not db: return False
    try: return db.collection(COLLECTION).document(key).get().exists
    except Exception: return False

def _mark(db,key,item):
    if not db: return
    try:
        db.collection(COLLECTION).document(key).set({
            "notified_at":_now().isoformat(),
            "url":item.get("url",""),
            "author":item.get("author",""),
            "title":item.get("title","")[:500],
        },merge=True)
    except Exception: pass

def run():
    unique={}
    api_rows=0; fallback_rows=0
    for query in QUERIES:
        rows=_native_search(query)
        if not rows:
            rows=_bing_rss(query)
            fallback_rows+=len(rows)
        if not rows:
            # Legacy endpoint is now last-resort only; it frequently times out
            # from GitHub Actions and must never dominate the runtime.
            rows=_search(query)
            api_rows+=len(rows)
        for raw in rows:
            item=_row(raw)
            item["provider"]=raw.get("_provider") or "mailru_api"
            if not item["id"] or not item["url"]: continue
            # Enrich known question IDs through Mail.ru's per-question JSON endpoint.
            payload=_question_api(item["id"])
            extra=_json_text(payload) if payload else ""
            if extra:
                item["text"]=" ".join(x for x in (item.get("text",""),extra) if x)[:12000]
                if item["provider"]!="mailru_api":
                    item["provider"]=item["provider"]+"+question_api"
            unique.setdefault(item["id"],item)

    db=main.firestore_client()
    leads=[]; review_saved=0
    for item in unique.values():
        score=_score(item)
        if score:
            key=hashlib.sha1(("mailru|"+item["id"]).encode()).hexdigest()
            if _seen(db,key): continue
            item["intent"]=score
            leads.append(item)
            _mark(db,key,item)
        else:
            context=f"{item.get('title','')} {item.get('text','')}"
            if rsr.save("mailru_answers",context,item.get("url",""),item.get("author",""),context):
                review_saved+=1

    leads.sort(key=lambda x:x["intent"],reverse=True)
    print(f"MAILRU_RADAR_COMPLETE candidates={len(unique)} api_rows={api_rows} fallback_rows={fallback_rows} leads={len(leads)} review_saved={review_saved}")
    if leads:
        lines=[f"✉️ MAIL.RU ANSWERS RADAR | {len(leads)} BUYER ADAYI"]
        for x in leads[:10]:
            body=" ".join(f"{x.get('title','')} {x.get('text','')}".split())[:260]
            lines += [
                "",
                f"Intent {x['intent']} | {x.get('provider','mailru')} | @{x.get('author') or 'kullanıcı'} | {x.get('published','')[:10]}",
                f"❓ {body}",
                x["url"],
            ]
        main.notify_telegram("\n".join(lines))

if __name__=="__main__":
    run()
