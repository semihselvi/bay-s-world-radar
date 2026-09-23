from __future__ import annotations
import asyncio, json, os, re
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User

QUERIES=[
 "Grand Sapphire A block 1+1",
 "Grand Sapphire Block A 1+1",
 "Grand Sapphire A блок 1+1",
 "Гранд Сапфир блок А 1+1",
 "Гранд Сапфир А блок 1+1",
]
PROJECT_RE=re.compile(r"(?:grand\s+sapphire|гранд\s+сапфир)",re.I)
ROOM_RE=re.compile(r"\b1\s*\+\s*1\b")
BLOCK_A_RE=re.compile(r"(?:block|блок)\s*[:\-]?\s*(?:a|а)\b",re.I)
SALE_RE=re.compile(r"(?:for\s+sale|sale\b|selling|resale|sat[ıi]l[ıi]k|sat[ıi]yorum|продаю|продам|прода[её]тся|продажа|перепродаж|вторичк)",re.I)
RENT_RE=re.compile(r"(?:аренда|в\s+аренду|сдам|сдаю|сда[её]тся|for\s+rent|rent\b|kiral[ıi]k)",re.I)
BLU_RE=re.compile(r"(?:grand\s+sapphire\s+(?:blu|blue)|гранд\s+сапфир\s+блу)",re.I)

def link(chat,mid):
    u=getattr(chat,"username",None)
    if u:return f"https://t.me/{u}/{mid}"
    cid=abs(int(getattr(chat,"id",0) or 0))
    return f"https://t.me/c/{cid}/{mid}" if cid else ""

def author(sender):
    if not isinstance(sender,User) or getattr(sender,"bot",False): return ""
    u=getattr(sender,"username",None)
    if u:return "@"+u
    return " ".join(x for x in ((getattr(sender,"first_name","") or ""),(getattr(sender,"last_name","") or "")) if x).strip()

def parse(text):
    price=""
    m=re.search(r"(?:£\s?\d[\d\s,.]*|\b\d[\d\s,.]*\s?£)",text)
    if m: price=m.group(0).strip()
    floor=""
    m=re.search(r"(?:этаж|floor|kat)\s*[:\-]?\s*(\d+)|\b(\d+)\s*(?:этаж|floor|kat)",text,re.I)
    if m: floor=m.group(1) or m.group(2) or ""
    return price,floor

async def main():
    api_id=os.getenv("TELEGRAM_API_ID","").strip()
    api_hash=os.getenv("TELEGRAM_API_HASH","").strip()
    sess=os.getenv("TELEGRAM_STRING_SESSION","").strip()
    days=max(1,min(180,int(os.getenv("GS_A1_DAYS","120"))))
    cutoff=datetime.now(timezone.utc)-timedelta(days=days)
    client=TelegramClient(StringSession(sess),int(api_id),api_hash)
    await client.connect()
    found={}
    try:
      for q in QUERIES:
        async for msg in client.iter_messages(None,search=q,limit=300):
            dt=getattr(msg,"date",None)
            if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            if not dt or dt<cutoff: continue
            text=str(getattr(msg,"message","") or "").strip()
            if not text: continue
            if not PROJECT_RE.search(text) or not ROOM_RE.search(text) or not BLOCK_A_RE.search(text): continue
            if BLU_RE.search(text) or RENT_RE.search(text) or not SALE_RE.search(text): continue
            try: chat=await msg.get_chat()
            except Exception: chat=None
            if not isinstance(chat,(Channel,Chat)): continue
            try: snd=await msg.get_sender()
            except Exception: snd=None
            a=author(snd)
            if not a: continue
            price,floor=parse(text)
            u=link(chat,msg.id)
            found[u]={
              "published":dt.astimezone(timezone.utc).isoformat(),
              "group":getattr(chat,"title","") or "",
              "group_username":getattr(chat,"username","") or "",
              "author":a,"price":price,"floor":floor,"url":u,"text":text
            }
    finally:
      await client.disconnect()
    rows=sorted(found.values(),key=lambda x:x["published"],reverse=True)
    print("GS_A1_SUMMARY",json.dumps({"days":days,"count":len(rows)},ensure_ascii=False))
    for i,row in enumerate(rows,1):
      print("GS_A1_LISTING",json.dumps({"n":i,**row},ensure_ascii=False))

if __name__=="__main__": asyncio.run(main())
