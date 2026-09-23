from __future__ import annotations
import asyncio, json, os, re
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, User

TARGETS = [
    {"key":"C16_1+1","block":["c","с"],"floor":"16","room":"1+1","queries":[
        "Grand Sapphire 16 этаж","Гранд Сапфир 16 этаж","Grand Sapphire Block C 16","Grand Sapphire Блок С 16"
    ]},
    {"key":"B19_1+1","block":["b","в"],"floor":"19","room":"1+1","queries":[
        "Grand Sapphire 19 этаж","Гранд Сапфир 19 этаж","Grand Sapphire Block B 19","Grand Sapphire Блок В 19"
    ]},
]

def link(chat, mid):
    u=getattr(chat,"username",None)
    if u: return f"https://t.me/{u}/{mid}"
    cid=abs(int(getattr(chat,"id",0) or 0))
    return f"https://t.me/c/{cid}/{mid}" if cid else ""

def author(sender):
    if not isinstance(sender,User) or getattr(sender,"bot",False): return ""
    u=getattr(sender,"username",None)
    if u: return "@"+u
    return " ".join(x for x in ((getattr(sender,"first_name","") or ""),(getattr(sender,"last_name","") or "")) if x).strip()

def norm(s): return " ".join(str(s or "").casefold().replace("ё","е").split())

def prices(text):
    vals=[]
    for m in re.finditer(r"(?:£\s?\d[\d\s,.]*|\b\d[\d\s,.]*\s?£)",text):
        vals.append(m.group(0).strip())
    return vals

def match_target(text,t):
    n=norm(text)
    if "grand sapphire" not in n and "гранд сапфир" not in n: return False
    if not re.search(r"\b1\s*\+\s*1\b",n): return False
    if not re.search(rf"(?:этаж|floor|kat)\s*[:\-]?\s*{t['floor']}\b|\b{t['floor']}\s*(?:этаж|floor|kat)",n): return False
    # Block context: allow latin/cyrillic visually equivalent letters.
    if not any(re.search(rf"(?:блок|block)\s*[:\-]?\s*{re.escape(b)}\b",n) for b in t["block"]): return False
    return True

async def main():
    api_id=os.getenv("TELEGRAM_API_ID","").strip()
    api_hash=os.getenv("TELEGRAM_API_HASH","").strip()
    sess=os.getenv("TELEGRAM_STRING_SESSION","").strip()
    days=int(os.getenv("GS_TARGET_DAYS","120"))
    cutoff=datetime.now(timezone.utc)-timedelta(days=days)
    client=TelegramClient(StringSession(sess),int(api_id),api_hash)
    await client.connect()
    out={t["key"]:{} for t in TARGETS}
    try:
        for t in TARGETS:
            for q in t["queries"]:
                async for msg in client.iter_messages(None,search=q,limit=300):
                    dt=getattr(msg,"date",None)
                    if dt and dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                    if not dt or dt<cutoff: continue
                    text=str(getattr(msg,"message","") or "").strip()
                    if not text or not match_target(text,t): continue
                    try: chat=await msg.get_chat()
                    except Exception: chat=None
                    if not isinstance(chat,(Channel,Chat)): continue
                    try: snd=await msg.get_sender()
                    except Exception: snd=None
                    a=author(snd)
                    if not a: continue
                    u=link(chat,msg.id)
                    out[t["key"]][u]={
                        "published":dt.astimezone(timezone.utc).isoformat(),
                        "group":getattr(chat,"title","") or "",
                        "group_username":getattr(chat,"username","") or "",
                        "author":a,
                        "prices":prices(text),
                        "url":u,
                        "text":text
                    }
    finally:
        await client.disconnect()
    for key,items in out.items():
        rows=sorted(items.values(),key=lambda x:x["published"],reverse=True)
        print("GS_TARGET_SUMMARY",json.dumps({"key":key,"count":len(rows)},ensure_ascii=False))
        for i,row in enumerate(rows,1):
            print("GS_TARGET_LISTING",json.dumps({"key":key,"n":i,**row},ensure_ascii=False))

if __name__=="__main__":
    asyncio.run(main())
