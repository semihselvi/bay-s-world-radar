import os,re,hashlib
from datetime import datetime,timezone,timedelta
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET
import requests
import main

QUERIES=[
'Северный Кипр хочу купить квартиру','Северный Кипр ищу квартиру купить','Северный Кипр куплю недвижимость',
'Северный Кипр бюджет квартира','Искеле хочу купить квартиру','Искеле куплю 1+1','Искеле куплю 2+1',
'Лонг Бич Кипр хочу купить квартиру','Гирне хочу купить квартиру','Гирне хочу купить виллу',
'Северный Кипр инвестиции ищу квартиру','Северный Кипр недвижимость нужен вариант'
]
NC=re.compile(r'(северн\w*\s+кипр\w*|искеле|лонг\s*бич|гирне|эсентепе|фамагуст|бафра|лапта|алсанджак)',re.I)
BUY=re.compile(r'(хочу\s+купить|куплю|ищу.{0,30}(?:купить|квартир|вилл|недвиж)|бюджет|нужн\w*.{0,20}(?:квартир|вилл|недвиж))',re.I|re.S)
SELL=re.compile(r'(прода[её]тся|продаю|на продажу|цена продажи|агентств|риелтор|риэлтор)',re.I)
RENT=re.compile(r'(сниму|аренд|снять|сдается|сдаётся)',re.I)

def _text(item,tag):
    node=item.find(tag)
    return ''.join(node.itertext()).strip() if node is not None else ''

def bing(q):
    url='https://www.bing.com/search?q='+quote_plus('site:vk.com '+q)+'&format=rss'
    r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=20); r.raise_for_status()
    root=ET.fromstring(r.content); out=[]
    for it in root.findall('.//item'):
        out.append({'title':_text(it,'title'),'text':_text(it,'description'),'url':_text(it,'link'),'published':_text(it,'pubDate')})
    return out

def score(row):
    text=f"{row['title']} {row['text']}"
    if not NC.search(text) or not BUY.search(text): return None
    if RENT.search(text) and not BUY.search(text): return None
    if SELL.search(text) and not re.search(r'ищу|хочу|куплю|нужн|бюджет',text,re.I): return None
    s=72
    if re.search(r'бюджет|£|€|\$|\d{4,}',text,re.I): s+=10
    if re.search(r'хочу купить|куплю',text,re.I): s+=10
    if re.search(r'искеле|лонг\s*бич|гирне|эсентепе',text,re.I): s+=5
    return min(s,97)

def run():
    seen={}; leads=[]
    for q in QUERIES:
        try:
            rows=bing(q); print(f'VK_QUERY {q!r} rows={len(rows)}')
            for row in rows:
                if 'vk.com' not in row['url']: continue
                key=hashlib.sha1((row['url'] or row['title']).encode()).hexdigest()
                if key in seen: continue
                seen[key]=1; s=score(row)
                if s: row.update(intent=s,query=q); leads.append(row)
        except Exception as e: print('VK_QUERY_ERROR',q,type(e).__name__,e)
    leads.sort(key=lambda x:x['intent'],reverse=True)
    print(f'VK_RADAR_COMPLETE candidates={len(seen)} leads={len(leads)}')
    if leads:
        lines=[f'🔥 VK RADAR | {len(leads)} BUYER ADAYI']
        for x in leads[:10]: lines += ['',f"Intent {x['intent']} | {x['title'][:140]}",x['url']]
        main.notify_telegram('\n'.join(lines))
    else: print('VK_RADAR no buyer candidate')
if __name__=='__main__': run()
