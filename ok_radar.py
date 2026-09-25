import re,html
from urllib.parse import quote_plus,urlparse,parse_qs,unquote,urljoin
from xml.etree import ElementTree as ET
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
from bs4 import BeautifulSoup
import main

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'ru-RU,ru;q=0.9,en;q=0.7'})
QUERIES=['Северный Кипр хочу купить квартиру','Северный Кипр ищу квартиру купить','Северный Кипр куплю недвижимость','Северный Кипр бюджет квартира','Искеле хочу купить квартиру','Искеле куплю 1+1','Искеле куплю 2+1','Лонг Бич Кипр хочу купить квартиру','Гирне хочу купить квартиру','Гирне хочу купить виллу','Северный Кипр недвижимость нужен вариант','Северный Кипр переезд купить квартиру']
SEEDS=['https://ok.ru/northcyprusinvest','https://ok.ru/cypruslegend','https://ok.ru/group/61172585857171','https://ok.ru/group/54088607531008']
NC=re.compile(r'(северн\w*\s+кипр\w*|искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак)',re.I)
# Buyer intent must be explicit and first-person / request-shaped. Generic words such as
# "budget", "buy property" or our own search query are not sufficient anymore.
BUY_STRICT=re.compile(r'(?:^|[\s.!?,;:])(?:я\s+)?(?:хочу|хотел(?:а)?\s+бы|планирую|собираюсь)\s+(?:себе\s+)?купить|(?:^|[\s.!?,;:])куплю\s+(?:квартир|вилл|дом|недвиж)|(?:^|[\s.!?,;:])ищу.{0,90}(?:для\s+покупки|чтобы\s+купить|купить\s+(?:квартир|вилл|дом|недвиж))|(?:мой|наш)\s+бюджет.{0,100}(?:квартир|вилл|дом|недвиж|покуп)|подскажите.{0,100}(?:где|что|какую|какой).{0,80}(?:купить|покуп)|нужн[аоы]?.{0,80}(?:квартир|вилл|дом).{0,80}(?:купить|покуп)',re.I|re.S)
SELL=re.compile(r'(прода[её]тся|продаю|на\s+продажу|в\s+продаже|агентств|риелтор|риэлтор|застройщик|предлагаем|предлагается|стоимость\s+от|цена\s+от|скидк|акци[яи]|рассрочк|комисси|готовая\s+квартира|готовый\s+объект|инвестиционн|доходност|окупаемост|почему\s+стоит\s+купить|успейте\s+купить|звоните|пишите\s+в\s+(?:лич|директ)|подбер[её]м|подбор\s+недвиж)',re.I)
PROMO=re.compile(r'(курс\s+фунта|историческ\w+\s+минимум|интересный\s+контент\s+в\s+группе|собственная\s+недвижимость.{0,80}позволяет|недвижимость\s+на\s+северном\s+кипре.{0,80}почему|подписывайтесь|наш\s+канал|наша\s+компания)',re.I|re.S)

def valid(u):
    try: h=urlparse(u).netloc.lower(); return h=='ok.ru' or h.endswith('.ok.ru')
    except: return False

def unwrap(href):
    href=html.unescape(href or '')
    if href.startswith('//'): href='https:'+href
    if href.startswith('/'): href=urljoin('https://ok.ru',href)
    if valid(href): return href
    try:
        q=parse_qs(urlparse(href).query)
        for k in ('uddg','url','u','target'):
            for v in q.get(k,[]):
                v=unquote(v)
                if valid(v): return v
    except: pass
    return ''

def parse_page(text,provider):
    soup=BeautifulSoup(text,'html.parser'); out=[]
    for a in soup.find_all('a',href=True):
        u=unwrap(a.get('href'))
        if not u or '/topic/' not in u: continue
        block=a
        for _ in range(3):
            if block.parent: block=block.parent
        out.append({'title':' '.join(a.stripped_strings)[:300],'text':' '.join(block.stripped_strings)[:3000],'url':u,'published':'','provider':provider})
    return out

def native(q):
    out=[]
    for p,u in [('ok_search','https://ok.ru/search?st.query='+quote_plus(q)),('ok_content','https://ok.ru/search/content/'+quote_plus(q.replace(' ','-')))]:
        try:
            r=S.get(u,timeout=25); print('OK_NATIVE',p,r.status_code,len(r.text)); out += parse_page(r.text,p)
        except Exception as e: print('OK_NATIVE_ERROR',p,type(e).__name__)
    return out

def communities():
    out=[]
    for seed in SEEDS:
        for u in (seed,seed.replace('https://ok.ru/','https://m.ok.ru/')):
            try:
                r=S.get(u,timeout=25); print('OK_SEED',u,r.status_code,len(r.text)); out += parse_page(r.text,'ok_community')
            except Exception as e: print('OK_SEED_ERROR',type(e).__name__)
    return out

def rss(q):
    u='https://www.bing.com/search?q='+quote_plus('site:ok.ru '+q)+'&format=rss'; r=S.get(u,timeout=20); r.raise_for_status(); root=ET.fromstring(r.content); out=[]
    for it in root.findall('.//item'):
        get=lambda t: ''.join(it.find(t).itertext()).strip() if it.find(t) is not None else ''
        u=unwrap(get('link'))
        if u and '/topic/' in u: out.append({'title':get('title'),'text':get('description'),'url':u,'published':get('pubDate'),'provider':'bing_rss'})
    return out

def extract_comments(soup, topic_url):
    out=[]; seen=set()
    selectors=('[data-l*="comment"]','[class*="comment"]','[data-module*="comment"]')
    nodes=[]
    for sel in selectors:
        try: nodes += soup.select(sel)
        except Exception: pass
    for node in nodes:
        try:
            txt=' '.join(node.stripped_strings).strip()
        except Exception:
            continue
        if len(txt)<18 or len(txt)>2600:
            continue
        low=txt.lower()
        if low in seen: continue
        seen.add(low)
        author=''
        try:
            a=node.find('a',href=re.compile(r'/profile/'))
            if a: author=' '.join(a.stripped_strings).strip()[:120]
        except Exception: pass
        cid=''
        for attr in ('data-id','data-comment-id','id'):
            val=str(node.get(attr) or '').strip()
            if val:
                m=re.search(r'(\d{4,})',val)
                if m: cid=m.group(1); break
        url=topic_url
        if cid: url=topic_url.split('?')[0]+'#comment-'+cid
        out.append({'author':author,'text':txt[:2600],'url':url,'comment_id':cid})
    return out

def score_comment(comment, topic_context):
    text=str(comment.get('text','')).strip()
    if len(text)<18: return None
    if not NC.search(topic_context): return None
    if PROMO.search(text) or SELL.search(text): return None
    if not BUY_STRICT.search(text): return None
    # Very short engagement such as "price?" is intentionally excluded.
    if len(text)<32 and not re.search(r'(?:я\s+)?(?:хочу|планирую|собираюсь)\s+купить|куплю\s+(?:квартир|вилл|дом)|ищу.{0,70}(?:для\s+покупки|чтобы\s+купить)',text,re.I|re.S):
        return None
    s=84
    if re.search(r'(?:мой|наш)\s+бюджет|£|€|\$|\b\d{4,}\b',text,re.I): s+=6
    if re.search(r'искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак',text,re.I): s+=4
    if re.search(r'прие(?:ду|дем)|буду\s+на\s+кипре|в\s+октябре|в\s+ноябре|смотреть|просмотр',text,re.I): s+=4
    return min(s,98)

def enrich(row):
    try:
        r=requests.get(row['url'],headers={'User-Agent':UA,'Accept-Language':'ru-RU,ru;q=0.9'},timeout=15)
        if r.status_code!=200: return row
        soup=BeautifulSoup(r.text,'html.parser')
        # Do NOT append the whole page. OK search/navigation chrome can contain our query
        # and previously created false buyer intent. Prefer topic metadata and article/main text.
        pieces=[]
        for attrs in ({'property':'og:description'},{'name':'description'}):
            m=soup.find('meta',attrs=attrs)
            if m and m.get('content'): pieces.append(m.get('content'))
        for sel in ('article','main','[data-l*="topic"]'):
            node=soup.select_one(sel)
            if node:
                pieces.append(' '.join(node.stripped_strings)[:6000])
                break
        core=' '.join(x for x in pieces if x)
        row=dict(row)
        row['page_core']=core[:9000]
        row['comments']=extract_comments(soup,row.get('url',''))
        if soup.title and not row.get('title'): row['title']=soup.title.get_text(' ',strip=True)[:300]
    except Exception: pass
    return row

def score(row):
    title=str(row.get('title',''))
    snippet=str(row.get('text',''))
    core=str(row.get('page_core',''))
    text=f'{title} {snippet} {core}'
    if not NC.search(text): return None
    if PROMO.search(text): return None
    # Supply/marketing posts are rejected even when the page contains generic buyer wording.
    # Only keep them if a clearly first-person buyer request exists in the actual topic core.
    strict_core=f'{title} {core or snippet}'
    buyer=BUY_STRICT.search(strict_core)
    if not buyer: return None
    if SELL.search(title) or (SELL.search(strict_core) and not re.search(r'(?:я\s+)?(?:хочу|планирую|собираюсь)\s+купить|куплю\s+(?:квартир|вилл|дом)|ищу.{0,70}(?:для\s+покупки|чтобы\s+купить)',strict_core,re.I|re.S)):
        return None
    s=78
    if re.search(r'(?:мой|наш)\s+бюджет|£|€|\$|\b\d{4,}\b',strict_core,re.I): s+=8
    if re.search(r'(?:я\s+)?(?:хочу|планирую|собираюсь)\s+купить|куплю\s+(?:квартир|вилл|дом)',strict_core,re.I): s+=8
    if re.search(r'искеле|лонг\s*бич|гирне|эсентепе',strict_core,re.I): s+=4
    return min(s,97)

def run():
    unique={}; provider_counts={}; allrows=communities()
    for q in QUERIES:
        rows=native(q)+rss(q); print(f'OK_QUERY {q!r} raw={len(rows)}'); allrows += rows
    for row in allrows:
        if not valid(row['url']): continue
        key=row['url'].split('?')[0].rstrip('/')
        if key not in unique: unique[key]=row; provider_counts[row['provider']]=provider_counts.get(row['provider'],0)+1
    rows=list(unique.values())[:180]; enriched=[]
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs=[ex.submit(enrich,r) for r in rows]
        for f in as_completed(futs): enriched.append(f.result())
    topic_leads=[]; comment_leads=[]; rejected=0
    comment_seen=set()
    for row in enriched:
        s=score(row)
        if s:
            row['intent']=s; row['lead_type']='topic'; topic_leads.append(row)
        else:
            rejected+=1
        topic_context=f"{row.get('title','')} {row.get('page_core','')} {row.get('text','')}"
        for comment in row.get('comments',[]) or []:
            cs=score_comment(comment,topic_context)
            if not cs: continue
            key=(comment.get('url',''),comment.get('author',''),comment.get('text','')[:220])
            if key in comment_seen: continue
            comment_seen.add(key)
            comment_leads.append({
                'intent':cs,'lead_type':'comment','provider':'ok_comment',
                'title':row.get('title',''),'url':comment.get('url') or row.get('url',''),
                'author':comment.get('author',''),'text':comment.get('text',''),
            })
    leads=topic_leads+comment_leads
    leads.sort(key=lambda x:x['intent'],reverse=True)
    print('OK_PROVIDER_COUNTS',provider_counts)
    print(f"OK_COMMENT_RADAR comments={sum(len(r.get('comments',[]) or []) for r in enriched)} leads={len(comment_leads)}")
    print(f'OK_RADAR_COMPLETE candidates={len(unique)} enriched={len(enriched)} topic_leads={len(topic_leads)} comment_leads={len(comment_leads)} leads={len(leads)} rejected={rejected}')
    if leads:
        lines=[f'🔥 OK.RU RADAR | {len(leads)} BUYER ADAYI']
        for x in leads[:10]:
            if x.get('lead_type')=='comment':
                excerpt=' '.join(str(x.get('text','')).split())[:220]
                lines += ['',f"COMMENT | Intent {x['intent']} | @{x.get('author') or 'kullanıcı'}",f"💬 {excerpt}",x['url']]
            else:
                lines += ['',f"TOPIC | Intent {x['intent']} | {x['provider']} | {x['title'][:140]}",x['url']]
        main.notify_telegram('\n'.join(lines))
    else: print('OK_RADAR no buyer candidate')
if __name__=='__main__': run()
