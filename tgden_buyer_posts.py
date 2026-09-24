import hashlib
import json
import os
from datetime import datetime, timezone, timedelta

import requests

import main

MCP_URL="https://tgden.com/api/mcp"
COLLECTION="bay_s_tgden_post_candidates"

BUYER_QUERIES=[
    "North Cyprus looking to buy",
    "North Cyprus want to buy property",
    "North Cyprus cash buyer",
    "North Cyprus property wanted",
    "Kuzey Kıbrıs satın almak istiyorum",
    "Kuzey Kıbrıs daire arıyorum",
    "İskele daire arıyorum satın",
    "Girne villa arıyorum satın",
    "Северный Кипр хочу купить квартиру",
    "Северный Кипр ищу квартиру купить",
    "Искеле хочу купить",
    "Гирне хочу купить виллу",
]

RENT_WORDS=("rent","rental","kiralık","kirala","аренд","сниму","снять")
BUY_WORDS=("buy","purchase","cash buyer","want to buy","looking to buy","satın","almak istiyorum","купить","куплю","покуп")
PROPERTY_WORDS=("property","apartment","flat","villa","house","studio","daire","ev","konut","квартир","вилл","дом","студи")
NC_WORDS=("north cyprus","northern cyprus","kktc","trnc","kuzey kıbrıs","iskele","i̇skele","long beach","girne","kyrenia","esentepe","famagusta","gazimağusa","северный кипр","искеле","гирне")


def _rpc(method, params=None, timeout=20):
    payload={"jsonrpc":"2.0","id":1,"method":method}
    if params is not None:
        payload["params"]=params
    r=requests.post(MCP_URL,json=payload,headers={"Content-Type":"application/json"},timeout=timeout)
    r.raise_for_status()
    return r.json()


def _tool_schema():
    data=_rpc("tools/list")
    for tool in ((data.get("result") or {}).get("tools") or []):
        if tool.get("name")=="search_posts":
            return tool.get("inputSchema") or {}
    return {}


def _build_args(schema, query):
    props=schema.get("properties") or {}
    args={}
    # tolerate common naming changes
    for key in ("query","q","search","text","keyword","keywords"):
        if key in props:
            args[key]=query
            break
    for key in ("limit","size","count","max_results"):
        if key in props:
            args[key]=25
            break
    # Prefer newest when the tool exposes a sort/order knob.
    for key in ("sort","order","sort_by"):
        if key in props:
            enum=(props[key] or {}).get("enum") or []
            for value in ("newest","recent","date","desc"):
                if not enum or value in enum:
                    args[key]=value
                    break
            break
    return args


def _call_search_posts(args):
    return _rpc("tools/call",{"name":"search_posts","arguments":args},timeout=30)


def _extract_text_blocks(payload):
    result=payload.get("result") or {}
    blocks=result.get("content") or []
    out=[]
    for block in blocks:
        if block.get("type")=="text" and block.get("text"):
            out.append(block["text"])
    return out


def _walk_json(value, rows):
    if isinstance(value,dict):
        # capture dicts that look post-ish
        keys=set(value)
        if keys & {"text","message","content","post","title"} and keys & {"url","link","username","channel","chat","id","date","created_at"}:
            rows.append(value)
        for v in value.values():
            _walk_json(v,rows)
    elif isinstance(value,list):
        for v in value:
            _walk_json(v,rows)


def _parse_blocks(blocks):
    rows=[]
    for text in blocks:
        try:
            parsed=json.loads(text)
            _walk_json(parsed,rows)
            continue
        except Exception:
            pass
        # preserve raw text as one candidate only if it contains a Telegram URL
        if "t.me/" in text:
            rows.append({"text":text})
    return rows


def _candidate(row, query):
    text=" ".join(str(row.get(k) or "") for k in ("text","message","content","post","title")).strip()
    low=text.casefold()
    if not text:
        return None
    if not any(x in low for x in NC_WORDS):
        return None
    if any(x in low for x in RENT_WORDS) and not any(x in low for x in BUY_WORDS):
        return None
    if not any(x in low for x in PROPERTY_WORDS):
        return None
    if not any(x in low for x in BUY_WORDS) and not any(x in low for x in ("looking for","arıyorum","ищу","нужна","need")):
        return None

    url=str(row.get("url") or row.get("link") or "")
    username=str(row.get("username") or row.get("channel") or row.get("chat") or "")
    ident=url or f"{username}|{text[:240]}"
    return {
        "source":"tgden search_posts",
        "source_bucket":"tgden_public_posts",
        "url":url,
        "author":str(row.get("author") or row.get("user") or ""),
        "telegram_chat":username,
        "title":str(row.get("title") or username or "tgden Telegram post"),
        "text":text[:4000],
        "published":str(row.get("date") or row.get("created_at") or row.get("published_at") or ""),
        "tgden_query":query,
        "tgden_raw":row,
        "dedupe_id":hashlib.sha1(ident.encode("utf-8")).hexdigest(),
    }


def collect_tgden_buyer_posts():
    if os.getenv("NC_TGDEN_POSTS_ENABLED","1").strip()!="1":
        return []

    schema=_tool_schema()
    if not schema:
        print("TGDEN_POSTS_DISABLED search_posts_schema_missing")
        return []

    query_limit=max(1,min(len(BUYER_QUERIES),int(os.getenv("NC_TGDEN_POST_QUERY_LIMIT","8"))))
    unique={}
    for query in BUYER_QUERIES[:query_limit]:
        try:
            args=_build_args(schema,query)
            if not args:
                print("TGDEN_POSTS_BAD_SCHEMA",json.dumps(schema,ensure_ascii=False)[:1000])
                break
            response=_call_search_posts(args)
            rows=_parse_blocks(_extract_text_blocks(response))
            kept=0
            for row in rows:
                cand=_candidate(row,query)
                if not cand:
                    continue
                unique[cand["dedupe_id"]]=cand
                kept+=1
            print(f"TGDEN_POST_QUERY query={query!r} rows={len(rows)} kept={kept}")
        except Exception as exc:
            print(f"TGDEN_POST_QUERY_ERROR query={query!r} {type(exc).__name__}: {exc}")

    out=list(unique.values())
    db=main.firestore_client()
    if db:
        now=main.now_utc().isoformat()
        for item in out:
            row=dict(item); row["scanned_at"]=now
            db.collection(COLLECTION).document(item["dedupe_id"]).set(row,merge=True)
    print(f"TGDEN_POSTS_COMPLETE queries={query_limit} unique_candidates={len(out)}")
    return out


if __name__=="__main__":
    print(json.dumps(collect_tgden_buyer_posts(),ensure_ascii=False,indent=2))
