import os,re,html
from urllib.parse import quote_plus,urlparse,parse_qs,unquote,urljoin
from xml.etree import ElementTree as ET
import requests
from bs4 import BeautifulSoup
import main

UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/153 Safari/537.36'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Language':'ru-RU,ru;q=0.9,en;q=0.7'})
QUERIES=['Северный Кипр хочу купить квартиру','Северный Кипр ищу квартиру купить','Северный Кипр куплю недвижимость','Северный Кипр бюджет квартира','Искеле хочу купить квартиру','Искеле куплю 1+1','Искеле куплю 2+1','Лонг Бич Кипр хочу купить квартиру','Гирне хочу купить квартиру','Гирне хочу купить виллу','Северный Кипр инвестиции ищу квартиру','Северный Кипр недвижимость нужен вариант']
SEEDS=['https://vk.com/northcyprusinvest']
NC=re.compile(r'(северн\w*\s+кипр\w*|искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак)',re.I)
BUY=re.compile(r'(?:^|[\s.!?,;:])(?:я\s+)?(?:хочу|хотел(?:а)?\s+бы|планирую|собираюсь)\s+(?:себе\s+)?купить|(?:^|[\s.!?,;:])куплю\s+(?:квартир|вилл|дом|недвиж)|(?:^|[\s.!?,;:])ищу.{0,90}(?:для\s+покупки|чтобы\s+купить|купить\s+(?:квартир|вилл|дом|недвиж))|(?:мой|наш)\s+бюджет.{0,100}(?:квартир|вилл|дом|недвиж|покуп)|подскажите.{0,100}(?:где|что|какую|какой).{0,80}(?:купить|покуп)|нужн[аоы]?.{0,80}(?:квартир|вилл|дом).{0,80}(?:купить|покуп)',re.I|re.S)
SELL=re.compile(r'(прода[её]тся|продаю|на\s+продажу|в\s+продаже|агентств|риелтор|риэлтор|застройщик|предлагаем|цена\s+от|стоимость\s+от|рассрочк|инвестиционн|доходност|почему\s+стоит\s+купить|пишите\s+в\s+лич|подбер[её]м)',re.I)

def valid(u):
    try:
        h=urlparse(u).netloc.lower(); return h=='vk.com' or h.endswith('.vk.com')
    except: return False

def unwrap(href):
    href=html.unescape(href or '')
    if href.startswith('//'): href='https:'+href
    if href.startswith('/'): href=urljoin('https://vk.com',href)
    if valid(href): return href
    try:
        q=parse_qs(urlparse(href).query)
        for k in ('uddg','url','u','target'):
            for v in q.get(k,[]):
                v=unquote(v)
                if valid(v): return v
    except: pass
    return ''

def parse_vk_page(text,provider):
    soup=BeautifulSoup(text,'html.parser'); out=[]
    for a in soup.find_all('a',href=True):
        u=unwrap(a.get('href'))
        if not u or not re.search(r'/wall-?\d+_\d+|/wall\d+_\d+',u): continue
        block=a
        for _ in range(4):
            if block.parent: block=block.parent
        txt=' '.join(block.stripped_strings)[:3500]; title=' '.join(a.stripped_strings)[:300]
        out.append({'title':title,'text':txt,'url':u,'published':'','provider':provider})
    return out

def native(q):
    try:
        r=S.get('https://vk.com/search',params={'c[q]':q,'c[section]':'news'},timeout=25); print('VK_NATIVE',r.status_code,len(r.text)); return parse_vk_page(r.text,'vk_public_search')
    except Exception as e: print('VK_NATIVE_ERROR',type(e).__name__); return []

def communities():
    out=[]
    for u in SEEDS:
        try:
            r=S.get(u,timeout=25); print('VK_SEED',u,r.status_code,len(r.text)); out += parse_vk_page(r.text,'vk_community')
        except Exception as e: print('VK_SEED_ERROR',type(e).__name__)
    return out

def rss(q):
    u='https://www.bing.com/search?q='+quote_plus('site:vk.com '+q)+'&format=rss'; r=S.get(u,timeout=20); r.raise_for_status(); root=ET.fromstring(r.content); out=[]
    for it in root.findall('.//item'):
        get=lambda t: ''.join(it.find(t).itertext()).strip() if it.find(t) is not None else ''
        u=unwrap(get('link'))
        if u: out.append({'title':get('title'),'text':get('description'),'url':u,'published':get('pubDate'),'provider':'bing_rss'})
    return out

def vk_api(q):
    token=os.getenv('VK_ACCESS_TOKEN','').strip()
    if not token: return []
    try:
        r=S.get('https://api.vk.com/method/newsfeed.search',params={'q':q,'count':100,'extended':1,'access_token':token,'v':'5.199'},timeout=25); data=r.json()
        if 'error' in data: print('VK_API_ERROR',data['error'].get('error_code'),data['error'].get('error_msg')); return []
        out=[]
        for p in data.get('response',{}).get('items',[]):
            owner=p.get('owner_id'); pid=p.get('id'); text=p.get('text','')
            if owner is not None and pid is not None: out.append({'title':text[:220],'text':text,'url':f'https://vk.com/wall{owner}_{pid}','published':str(p.get('date','')),'provider':'vk_api','owner_id':owner,'post_id':pid})
        return out
    except Exception as e: print('VK_API_EXCEPTION',type(e).__name__); return []

def vk_comments(row):
    token=os.getenv('VK_ACCESS_TOKEN','').strip()
    if not token or row.get('provider')!='vk_api' or row.get('owner_id') is None or row.get('post_id') is None:
        return []
    try:
        r=S.get('https://api.vk.com/method/wall.getComments',params={
            'owner_id':row['owner_id'],'post_id':row['post_id'],'count':100,'extended':1,
            'thread_items_count':5,'access_token':token,'v':'5.199'
        },timeout=25)
        data=r.json()
        if 'error' in data:
            print('VK_COMMENT_API_ERROR',data['error'].get('error_code'),data['error'].get('error_msg'))
            return []
        out=[]
        for x in data.get('response',{}).get('items',[]) or []:
            txt=str(x.get('text') or '').strip()
            cid=x.get('id')
            if not txt or cid is None: continue
            out.append({
                'title':'VK comment','text':txt,
                'url':f"https://vk.com/wall{row['owner_id']}_{row['post_id']}?reply={cid}",
                'published':str(x.get('date','')),'provider':'vk_comment',
                'author_id':x.get('from_id')
            })
            for child in ((x.get('thread') or {}).get('items') or []):
                ctxt=str(child.get('text') or '').strip(); ccid=child.get('id')
                if ctxt and ccid is not None:
                    out.append({
                        'title':'VK reply','text':ctxt,
                        'url':f"https://vk.com/wall{row['owner_id']}_{row['post_id']}?reply={ccid}",
                        'published':str(child.get('date','')),'provider':'vk_comment',
                        'author_id':child.get('from_id')
                    })
        return out
    except Exception as e:
        print('VK_COMMENT_API_EXCEPTION',type(e).__name__)
        return []

def score_comment(row,context):
    text=str(row.get('text',''))
    if not NC.search(context) or not BUY.search(text) or SELL.search(text): return None
    s=84
    if re.search(r'(?:мой|наш)\s+бюджет|£|€|\$|\b\d{4,}\b',text,re.I): s+=6
    if re.search(r'искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак',text,re.I): s+=4
    if re.search(r'прие(?:ду|дем)|просмотр|посмотреть|в\s+октябре|в\s+ноябре',text,re.I): s+=4
    return min(s,98)

def score(row):
    text=f"{row.get('title','')} {row.get('text','')}"
    if not NC.search(text) or not BUY.search(text): return None
    if SELL.search(text) and not re.search(r'ищу|хочу|куплю|нужн|бюджет|подскажите|рассматрива',text,re.I): return None
    s=72
    if re.search(r'бюджет|£|€|\$|\d{4,}',text): s+=10
    if re.search(r'хочу\s+купить|куплю',text,re.I): s+=10
    if re.search(r'искеле|лонг\s*бич|гирне|эсентепе',text,re.I): s+=5
    return min(s,97)

def run():
    seen=set(); leads=[]; provider_counts={}; allrows=communities()
    for q in QUERIES:
        rows=vk_api(q)+native(q)+rss(q); print(f'VK_QUERY {q!r} raw={len(rows)}'); allrows += rows
    api_posts=[]
    for row in allrows:
        if not valid(row['url']): continue
        key=row['url'].split('?')[0].rstrip('/')
        if key in seen: continue
        seen.add(key); provider_counts[row['provider']]=provider_counts.get(row['provider'],0)+1
        s=score(row)
        if s: row.update(intent=s); leads.append(row)
        if row.get('provider')=='vk_api' and NC.search(f"{row.get('title','')} {row.get('text','')}"):
            api_posts.append(row)
    comment_rows=0
    for post in api_posts[:50]:
        context=f"{post.get('title','')} {post.get('text','')}"
        for com in vk_comments(post):
            comment_rows+=1
            key=com['url'].split('&')[0]
            if key in seen: continue
            seen.add(key); provider_counts['vk_comment']=provider_counts.get('vk_comment',0)+1
            s=score_comment(com,context)
            if s: com.update(intent=s); leads.append(com)
    leads.sort(key=lambda x:x['intent'],reverse=True)
    print('VK_PROVIDER_COUNTS',provider_counts); print(f'VK_RADAR_COMPLETE candidates={len(seen)} api_posts={len(api_posts)} comments={comment_rows} leads={len(leads)}')
    if leads:
        lines=[f'🔥 VK RADAR | {len(leads)} BUYER ADAYI']
        for x in leads[:10]: lines += ['',f"Intent {x['intent']} | {x['provider']} | {x['title'][:140]}",x['url']]
        main.notify_telegram('\n'.join(lines))
    else: print('VK_RADAR no buyer candidate')
if __name__=='__main__': run()
