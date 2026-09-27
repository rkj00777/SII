"""Free NSE filing-discovery layer.

It deliberately stores filing metadata before attempting document parsing. A
blocked download is a measured data gap, never a fabricated financial value.
"""
from datetime import datetime
from bs4 import BeautifulSoup
from .adapters import NSEAdapter

def discover_financial_results(html:bytes, source_url:str):
    soup=BeautifulSoup(html,'html.parser'); rows=[]
    for tr in soup.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
        if not cells: continue
        links=[a.get('href') for a in tr.find_all('a') if a.get('href')]
        if any(x.lower() in ' '.join(cells).lower() for x in ['financial results','xbrl','broadcast']):
            rows.append({'cells':cells,'links':links,'source_url':source_url,'discovered_at':datetime.utcnow().isoformat()})
    return rows

def fetch_result_page():
    a=NSEAdapter(); r=a.get(a.FILINGS_URL)
    if r.status!='OK': return {'status':r.status,'detail':r.detail,'rows':[]}
    return {'status':'OK','rows':discover_financial_results(r.content,r.url)}
