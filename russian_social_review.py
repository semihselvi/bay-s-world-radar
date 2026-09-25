import hashlib
import html
import re

import main

COLLECTION="bay_s_russian_social_review"

PROPERTY=re.compile(r"(квартир|апартамент|дом|вилл|студи|недвижимост|объект|1\s*\+\s*[01]|2\s*\+\s*[01]|3\s*\+\s*[01])",re.I)
REQUEST=re.compile(r"(какая\s+цена|сколько\s+стоит|цена\??|можно\s+подробнее|подробнее|какие\s+варианты|что\s+есть|есть\s+ли|актуально|условия|рассроч|первоначальн\w*\s+взнос|ипотек|титул|можно\s+посмотреть|просмотр|показ)",re.I)
MONEY=re.compile(r"(бюджет|£|€|\$|₽|\b\d{4,}\b)",re.I)
TIMING=re.compile(r"(прие(?:ду|дем)|буду\s+на\s+кипре|будем\s+на\s+кипре|в\s+октябре|в\s+ноябре|в\s+декабре|на\s+следующей\s+неделе)",re.I)
NC_CONTEXT=re.compile(r"(северн\w*\s+кипр\w*|искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак|north(?:ern)?\s+cyprus)",re.I)
SELLER=re.compile(r"(прода[её]тся|продаю|агентств|риелтор|риэлтор|застройщик|предлагаем|пишите\s+в\s+лич|обращайтесь|наш\s+проект|наша\s+компания|подбер[её]м)",re.I)


def candidate(text,context=""):
    text=html.unescape(re.sub(r"<[^>]+>"," ",str(text or "")))
    text=" ".join(text.split())
    context=html.unescape(re.sub(r"<[^>]+>"," ",str(context or "")))
    if len(text)<8 or SELLER.search(text) or not NC_CONTEXT.search(context):
        return None
    has_property=bool(PROPERTY.search(text))
    has_request=bool(REQUEST.search(text))
    has_timing=bool(TIMING.search(text))
    # Money alone is never a near-miss. It must be attached to a property,
    # transactional question or concrete arrival/viewing timing.
    if not (has_property or has_request or has_timing):
        return None
    score=0; reasons=[]
    if has_property: score+=2; reasons.append("property")
    if has_request: score+=2; reasons.append("request")
    if MONEY.search(text): score+=4; reasons.append("money")
    if has_timing: score+=3; reasons.append("timing")
    if score<4:
        return None
    return score,reasons


def save(platform,text,url="",author="",context="",extra=None):
    result=candidate(text,context)
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
        "text":" ".join(html.unescape(re.sub(r"<[^>]+>"," ",str(text))).split())[:3000],
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
