import os
import re
import json
import html
import time
import hashlib
import xml.etree.ElementTree as ET
from datetime import timedelta
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import main
import world_engine

REDDIT_GROUP = "RealEstate+FirstTimeHomeBuyer+FirstTimeHomeBuying+HousingUK+FirstTimeBuyersUK+propertyinvesting+dubairealestate+AusPropertyChat+orlando"
REDDIT_MAX_ENTRIES = int(os.getenv("WORLD_REDDIT_MAX_ENTRIES", "50"))
HTML_LATEST_SOURCES=[("Expat.com","https://www.expat.com/en/forum/","expat.com"),("ExpatForum","https://www.expatforum.com/whats-new/posts/","expatforum.com")]
DISCOURSE_LATEST=[("Nomad Gate","https://community.nomadgate.com/latest.json","community.nomadgate.com")]
EXA_FALLBACKS=[{"name":"exa_global_gapfill","domains":["reddit.com","expat.com","expatforum.com","nomadgate.com","bogleheads.org","montenegroexpats.com","forum-eu.com","completefrance.com","pim.be","internations.org","t.me","tlgrm.ru","telega.io"],"query":"past 7 days real person first-person property buyer discussion wants to buy house apartment flat villa property mortgage deposit viewing offer budget relocation Golden Visa; exclude listings agents developers guides news articles"},{"name":"exa_russian_cis_gapfill","domains":["reddit.com","forum.awd.ru","expat.com","forum-eu.com","internations.org","t.me","tlgrm.ru","telega.io"],"query":"past 7 days реальный человек хочет купить недвижимость за рубежом хочу купить ищу квартиру ищу дом ищу виллу планирую купить бюджет ипотека взнос просмотр переезд ВНЖ; exclude advertisements agents developers articles"}]

def clean_text(v): return BeautifulSoup(html.unescape(str(v or "")),"html.parser").get_text(" ",strip=True)

def reddit_direct():
    items=[]; url=f"https://www.reddit.com/r/{REDDIT_GROUP}/new/.rss?limit={min(REDDIT_MAX_ENTRIES,100)}"
    try:
        r=main.SESSION.get(url,timeout=20,headers={"Accept":"application/atom+xml,application/rss+xml,text/xml;q=0.9,*/*;q=0.8","User-Agent":"BAY-S-World-Radar/2.1 daily-public-feed-scan"})
        if r.status_code==429:
            print(f"REDDIT_RATE_LIMIT 429 retry_after={r.headers.get('Retry-After','unknown')} SKIP"); return []
        if r.status_code!=200: print(f"DIRECT_ERROR Reddit {r.status_code}"); return []
        root=ET.fromstring(r.content);ns={"a":"http://www.w3.org/2005/Atom"}
        for e in root.findall("a:entry",ns)[:REDDIT_MAX_ENTRIES]:
            link=""
            for n in e.findall("a:link",ns):
                if n.attrib.get("href") and n.attrib.get("rel","alternate") in ("","alternate"):link=n.attrib["href"];break
            if link: items.append({"source":"Reddit","url":link,"title":clean_text(e.findtext("a:title",default="",namespaces=ns)),"text":clean_text(e.findtext("a:content",default="",namespaces=ns) or e.findtext("a:summary",default="",namespaces=ns)),"published":e.findtext("a:published",default="",namespaces=ns) or e.findtext("a:updated",default="",namespaces=ns),"author":clean_text(e.findtext("a:author/a:name",default="",namespaces=ns)),"source_bucket":"direct_reddit"})
    except Exception as exc: print("DIRECT_EXCEPTION Reddit",exc)
    print(f"REDDIT_REQUESTS used=1 entries={len(items)}"); return items

def extract_page_item(url,source_name,title="",bucket="direct_html"):
    try:
        r=main.SESSION.get(url,timeout=20); soup=BeautifulSoup(r.text,"html.parser")
        if r.status_code!=200:return None
        pub=""; node=soup.select_one('meta[property="article:published_time"]') or soup.select_one('time[datetime]')
        if node: pub=node.get("content") or node.get("datetime") or ""
        body=soup.select_one("article") or soup.select_one("main") or soup.body or soup
        return {"source":source_name,"url":r.url,"title":title or clean_text(soup.title.string if soup.title else ""),"text":clean_text(body.get_text(" ",strip=True))[:12000],"published":pub,"author":"","source_bucket":bucket}
    except Exception as exc: print("DIRECT_PAGE_EXCEPTION",source_name,exc);return None

def scrape_latest_links(name,index,domain):
    out=[]
    try:
        r=main.SESSION.get(index,timeout=20); soup=BeautifulSoup(r.text,"html.parser"); links=[]
        for a in soup.find_all("a",href=True):
            href=urljoin(r.url,a["href"]); host=urlparse(href).netloc.lower(); title=clean_text(a.get_text(" ",strip=True)); low=href.lower()
            if domain not in host or len(title)<8:continue
            if name=="Expat.com" and "/forum/" not in low:continue
            if name=="ExpatForum" and not any(x in low for x in ("/threads/","/posts/")):continue
            if href not in [x[0] for x in links]:links.append((href,title))
            if len(links)>=12:break
        for href,title in links:
            x=extract_page_item(href,name,title,"direct_forum")
            if x:out.append(x)
    except Exception as exc:print("DIRECT_EXCEPTION",name,exc)
    return out

def discourse_latest(name,api,host):
    out=[]
    try:
        r=main.SESSION.get(api,timeout=20,headers={"Accept":"application/json"})
        if r.status_code!=200:return []
        for t in r.json().get("topic_list",{}).get("topics",[])[:20]:
            if not t.get("slug") or not t.get("id"):continue
            x=extract_page_item(f"https://{host}/t/{t['slug']}/{t['id']}",name,t.get("title",""),"direct_discourse")
            if x:x["published"]=t.get("created_at","") or x.get("published","");out.append(x)
    except Exception as exc:print("DIRECT_EXCEPTION",name,exc)
    return out

def telegram_public_channels():
    out=[]
    for ch in [x.strip().lstrip("@") for x in os.getenv("WORLD_TELEGRAM_CHANNELS","").split(",") if x.strip()]:
        try:
            r=main.SESSION.get(f"https://t.me/s/{ch}",timeout=20);s=BeautifulSoup(r.text,"html.parser")
            for w in s.select(".tgme_widget_message_wrap")[-30:]:
                l=w.select_one("a.tgme_widget_message_date");b=w.select_one(".tgme_widget_message_text");tm=w.select_one("time[datetime]")
                if l and b:out.append({"source":"Telegram","url":l.get("href",""),"title":f"Telegram @{ch}","text":clean_text(b.get_text(" ",strip=True)),"published":tm.get("datetime","") if tm else "","author":f"@{ch}","source_bucket":"direct_telegram"})
        except Exception as exc:print("DIRECT_EXCEPTION Telegram",ch,exc)
    return out

def direct_discovery():
    all_items=[];counts={};x=reddit_direct();all_items+=x;counts["Reddit"]=len(x)
    for n,u,d in HTML_LATEST_SOURCES:x=scrape_latest_links(n,u,d);all_items+=x;counts[n]=len(x)
    for n,u,h in DISCOURSE_LATEST:x=discourse_latest(n,u,h);all_items+=x;counts[n]=len(x)
    x=telegram_public_channels();all_items+=x;counts["Telegram"]=len(x);print("DIRECT_COUNTS",json.dumps(counts,ensure_ascii=False));return all_items,counts

def exa_gapfill():
    out=[];calls=0
    for b in EXA_FALLBACKS[:min(int(os.getenv("WORLD_EXA_FALLBACK_CALLS","2")),2)]:
        calls+=1;print(f"EXA_FALLBACK [{calls}/2] {b['name']}")
        for x in world_engine.exa_search(b["query"],b["domains"]):x["source_bucket"]=b["name"];out.append(x)
    return out,calls

def run():
    started=main.now_utc(); stats={};direct,counts=direct_discovery();exa,calls=exa_gapfill();cutoff=started-timedelta(hours=main.LOOKBACK_HOURS);seen=set();leads=[]
    for item in direct+exa:
        key=main.dedupe_key(item)
        if key in seen:continue
        seen.add(key);pub=world_engine.resolved_published(item);item["verified_published"]=pub.isoformat() if pub else "";keep,reason=main.keep_candidate(item,cutoff)
        if not keep:stats[reason]=stats.get(reason,0)+1;continue
        market=main.market_for(main.text_of(item),item.get("source_bucket",""),item.get("url",""),item.get("title",""));item["market"]=market;i,c,f,label=main.buyer_scores(item)
        if label not in ("HOT","WARM"):continue
        item.update({"intent_score":i,"credibility_score":c,"market_fit_score":f,"classification":label,"route_to":main.route_for(market),"scanned_at":started.isoformat(),"source_domain":main.domain_of(item.get("url",""))});leads.append(item)
    leads=list({main.dedupe_key(x):x for x in leads}.values());db=main.firestore_client();scan_id=started.strftime("%Y%m%d%H%M%S")
    if db:
        ref=db.collection(main.SCAN_LOG_COLLECTION).document(scan_id);batch=db.batch()
        for lead in leads:batch.set(ref.collection("leads").document(hashlib.sha1(lead.get("url","").encode()).hexdigest()),lead,merge=True)
        batch.set(ref,{"engine":"hybrid_reddit_safe","started_at":started.isoformat(),"direct_counts":counts,"exa_calls":calls,"unique_candidates":len(seen),"hot_warm":len(leads),"filter_stats":stats},merge=True);batch.commit()
    print(f"SCAN_COMPLETE engine=hybrid_reddit_safe candidates={len(seen)} hot_warm={len(leads)} exa_calls={calls}");print("FILTER_STATS",json.dumps(stats,ensure_ascii=False))
    if leads:
        lines=[f"BAY-S WORLD RADAR | {len(leads)} HOT/WARM | Aday: {len(seen)} | Exa: {calls}"]+[f"{x['classification']} | {x['market']} | {x.get('source','')} | I{x['intent_score']} C{x['credibility_score']} F{x['market_fit_score']} | {x.get('title','')[:100]} | {x.get('url','')}" for x in leads[:10]];main.notify_telegram("\n".join(lines))
    else:main.notify_telegram(f"BAY-S WORLD RADAR tamamlandı.\nYeni HOT/WARM lead yok.\nİncelenen aday: {len(seen)}\nDoğrudan kaynaklar: {sum(counts.values())}\nExa çağrısı: {calls}\nTarama: son {main.LOOKBACK_HOURS} saat")
if __name__=="__main__":run()
