import hashlib
import re

import main

COLLECTION="bay_s_russian_social_review"

PROPERTY=re.compile(r"(квартир|апартамент|дом|вилл|студи|недвижимост|объект|1\s*\+\s*[01]|2\s*\+\s*[01]|3\s*\+\s*[01])",re.I)
REQUEST=re.compile(r"(какая\s+цена|сколько\s+стоит|цена\??|можно\s+подробнее|подробнее|какие\s+варианты|что\s+есть|есть\s+ли|актуально|условия|рассроч|первоначальн\w*\s+взнос|ипотек|титул|можно\s+посмотреть|просмотр|показ)",re.I)
MONEY=re.compile(r"(бюджет|£|€|\$|₽|\b\d{4,}\b)",re.I)
TIMING=re.compile(r"(прие(?:ду|дем)|буду\s+на\s+кипре|будем\s+на\s+кипре|в\s+октябре|в\s+ноябре|в\s+декабре|на\s+следующей\s+неделе)",re.I)
SELLER=re.compile(r"(прода[её]тся|продаю|агентств|риелтор|риэлтор|застройщик|предлагаем|пишите\s+в\s+лич|обращайтесь|наш\s+проект|наша\s+компания|подбер[её]м)",re.I)


def candidate(text):
    text=" ".join(str(text or "").split())
    if len(text)<8 or SELLER.search(text):
        return None
    score=0; reasons=[]
    if PROPERTY.search(text): score+=2; reasons.append("property")
    if REQUEST.search(text): score+=2; reasons.append("request")
    if MONEY.search(text): score+=4; reasons.append("money")
    if TIMING.search(text): score+=3; reasons.append("timing")
    if score<4:
        return None
    return score,reasons


def save(platform,text,url="",author="",context="",extra=None):
    result=candidate(text)
    if not result:
        return False
    score,reasons=result
    db=main.firestore_client()
    if not db:
        return False
    basis=f"{platform}|{url}|{author}|{' '.join(str(text).split())[:500]}"
    key=hashlib.sha1(basis.encode("utf-8")).hexdigest()
    row={
        "platform":platform,
        "text":" ".join(str(text).split())[:3000],
        "url":url,
        "author":author,
        "context":str(context)[:1000],
        "review_score":score,
        "review_reasons":reasons,
        "reviewed_at":main.now_utc().isoformat(),
        "status":"review",
    }
    if isinstance(extra,dict):
        row.update(extra)
    try:
        db.collection(COLLECTION).document(key).set(row,merge=True)
        print(f"RUSSIAN_SOCIAL_REVIEW platform={platform} score={score} reasons={','.join(reasons)} author={author!r} text={row['text'][:180]!r}")
        return True
    except Exception as exc:
        print("RUSSIAN_SOCIAL_REVIEW_ERROR",platform,type(exc).__name__)
        return False
