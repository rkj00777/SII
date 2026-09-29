import csv, io, time, hashlib, json
from dataclasses import dataclass
from datetime import datetime, timezone
import requests
from .config import CONFIG
from .free_sources import assert_free_only

@dataclass
class FetchResult:
    status:str; url:str; http_status:int|None; content:bytes|None; detail:str; retrieved_at:datetime

class HttpAdapter:
    def __init__(self, source):
        assert_free_only(source); self.source=source; self.session=requests.Session(); self.session.headers.update({'User-Agent':CONFIG.user_agent,'Accept':'*/*','Referer':'https://www.nseindia.com/','X-Requested-With':'XMLHttpRequest','Accept-Language':'en-IN,en;q=0.9'})
    def get(self,url,retries=2,delay=0.75,params=None):
        last=''
        for i in range(retries):
            try:
                r=self.session.get(url,timeout=CONFIG.timeout,params=params)
                if r.status_code==200 and r.content:
                    return FetchResult('OK',url,200,r.content,'',datetime.now(timezone.utc).replace(tzinfo=None))
                last=f'HTTP {r.status_code}'
                if r.status_code not in (403,429,500,502,503,504): break
            except Exception as e:last=f'{type(e).__name__}: {e}'
            time.sleep(delay*(i+1))
        return FetchResult('DATA_UNAVAILABLE',url,None,None,last or 'unavailable',datetime.utcnow())

class NSEAdapter(HttpAdapter):
    EQUITY_URL='https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv'; SME_URL='https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv'
    FILINGS_URL='https://www.nseindia.com/companies-listing/corporate-filings-financial-results'; ACTIONS_URL='https://www.nseindia.com/companies-listing/corporate-filings-actions'
    def __init__(self):
        super().__init__('NSE')
        try: self.session.get('https://www.nseindia.com/',timeout=CONFIG.timeout)
        except Exception: pass
    def security_master(self):
        out=[]
        for url,segment in [(self.EQUITY_URL,'MAIN'),(self.SME_URL,'SME')]:
            r=self.get(url)
            if r.status!='OK': out.append((segment,r)); continue
            try: out.append((segment,list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig',errors='replace'))))) )
            except Exception as e: out.append((segment,FetchResult('PARSE_ERROR',url,200,None,str(e),datetime.utcnow())))
        return out
    def public_pages(self): return [(self.FILINGS_URL,'FINANCIAL_RESULTS'),(self.ACTIONS_URL,'CORPORATE_ACTIONS')]

class BSEAdapter(HttpAdapter):
    URL='https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w'
    ANN_URL='https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w'
    def __init__(self):
        super().__init__('BSE')
        self.session.headers.update({
            'Referer':'https://www.bseindia.com/',
            'Accept':'application/json, text/plain, */*',
            'X-Requested-With':'XMLHttpRequest',
        })
        self.session.headers.pop('Origin',None)
    def security_master(self):
        return self.get(self.URL, params={'Group':'','Scripcode':'','industry':'','segment':'Equity','status':'Active'})
    def announcements(self,scripcode=None,start=None,end=None,page=1):
        params={'pageno':page,'strCat':-1,'strSearch':'P','strType':'C'}
        if scripcode: params['strScrip']=str(scripcode)
        if start: params['strPrevDate']=start.strftime('%Y%m%d')
        if end: params['strToDate']=end.strftime('%Y%m%d')
        return self.get(self.ANN_URL, params=params)

class TejHQAdapter(HttpAdapter):
    BASE='https://api.tejhq.dev/v1'
    def __init__(self): super().__init__('TEJHQ')
    def status(self): return self.get(self.BASE+'/status')
    def ohlcv(self,symbol,start,end): return self.get(f'{self.BASE}/ohlcv/nse/{symbol}?from={start}&to={end}')
    def actions(self,exchange='nse',start=None,end=None):
        u=f'{self.BASE}/actions/{exchange}'
        if start:u+=f'?from={start}'
        if end:u+=('&' if '?' in u else '?')+f'to={end}'
        return self.get(u)

def stable_hash(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,default=str).encode()).hexdigest()
