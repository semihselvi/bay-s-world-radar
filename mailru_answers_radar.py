import hashlib
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import requests

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
        r=S.get(SEARCH_URL,params=params,timeout=25)
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
        rows=_search(query)
        if rows:
            api_rows+=len(rows)
        else:
            rows=_bing_rss(query)
            fallback_rows+=len(rows)
        for raw in rows:
            item=_row(raw)
            item["provider"]=raw.get("_provider") or "mailru_api"
            if not item["id"] or not item["url"]: continue
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
