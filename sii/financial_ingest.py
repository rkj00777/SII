"""Free NSE financial/XBRL ingestion."""
from datetime import datetime
from decimal import Decimal
import xml.etree.ElementTree as ET
import re
from bs4 import BeautifulSoup
from .adapters import NSEAdapter
from urllib.parse import urljoin

def _normalize_url(v):
    if not isinstance(v,str): return None
    v=v.strip()
    if v.startswith('//'): return 'https:'+v
    if v.startswith('/'): return 'https://www.nseindia.com'+v
    if v.startswith('http'): return v
    return None

def _find_url(obj):
    if isinstance(obj,str):
        return _normalize_url(obj)
    if isinstance(obj,dict):
        for k,v in obj.items():
            u=_normalize_url(v)
            if u and (any(t in u.lower() for t in ('xbrl','ixbrl','.xml')) or '/corporate/ixbrl/' in u.lower()):
                return u
            u=_find_url(v)
            if u: return u
    if isinstance(obj,list):
        for v in obj:
            u=_find_url(v)
            if u: return u
    return None
METRIC_ALIASES={"revenue":["RevenueFromOperations","Revenue","IncomeFromOperations","Turnover"],"pat":["ProfitLoss","ProfitForThePeriod","ProfitAfterTax","NetProfit"],"ebit":["EBIT","EarningsBeforeInterestAndTax","OperatingProfit"],"ebitda":["EBITDA","EarningsBeforeInterestTaxDepreciationAndAmortisation"],"cfo":["CashFlowsFromUsedInOperatingActivities","NetCashGeneratedFromOperatingActivities","CashGeneratedFromOperations"],"capex":["PurchaseOfPropertyPlantAndEquipment","PaymentsToAcquirePropertyPlantAndEquipment","PurchaseOfTangibleAssets"],"debt":["Borrowings","Debt","BorrowingsCurrentAndNonCurrent"],"cash":["CashAndCashEquivalents","CashAndBankBalances","Cash"],"equity":["Equity","EquityAttributableToOwnersOfParent","ShareholdersEquity"],"interest":["FinanceCosts","InterestExpense","FinanceCost"],"shares":["NumberOfSharesOutstanding","EquitySharesOutstanding"],"eps":["BasicEarningsLossPerShare","BasicEarningsPerShare","DilutedEarningsPerShare"]}
def _num(v):
    try:return None if v in (None,"") else float(Decimal(str(v).replace(",","")))
    except:return None
def _dt(v):
    if not v:return None
    if isinstance(v,datetime):return v.replace(tzinfo=None)
    s=str(v).strip().replace("Z","+00:00")
    for fmt in ("%d-%b-%Y %H:%M:%S","%d-%b-%Y","%Y-%m-%dT%H:%M:%S%z","%Y-%m-%d"):
        try:return datetime.strptime(s,fmt).replace(tzinfo=None)
        except ValueError:pass
    try:return datetime.fromisoformat(s).replace(tzinfo=None)
    except:return None
def _availability(row):
    for k in ("exchdisstime","exchangeDisseminationTime","sort_date","sortDate","broadcastDateTime","broadCastDate","broadcastDate","filingDateTime","filingDate","filedAt","submissionDate","submission_date"):
        d=_dt(row.get(k))
        if d:return d
    return None
def _walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values():yield from _walk(v)
    elif isinstance(obj,list):
        for v in obj:yield from _walk(v)
def extract_filing_rows(payload):
    out=[]
    for d in _walk(payload):
        lower={str(k).lower():v for k,v in d.items()}; xbrl=None
        for k,v in lower.items():
            if "xbrl" in k:
                xbrl=_find_url(v)
                if xbrl: break
        if not xbrl:
            for k,v in lower.items():
                if isinstance(v,str):
                    u=_normalize_url(v)
                    if u and ("xbrl" in u.lower() or "ixbrl" in u.lower() or u.lower().endswith(".xml")): xbrl=u; break
        if xbrl:
            isin=next((v for k,v in lower.items() if k in ("isin","sm_isin","isinno")),None)
            symbol=next((v for k,v in lower.items() if k in ("symbol","sym")),None)
            period=next((v for k,v in lower.items() if k in ("periodend","period_end","todate","to_date","quarterend","quarter_end","enddate","end_date")),None)
            if period is None:
                period=next((v for k,v in lower.items() if "period" in k and "end" in k),None)
            if isin or symbol or period:
                out.append({"xbrl_url":xbrl,"isin":isin,"symbol":symbol,"period_end":period,"available_at":_availability(d),"raw":d})
    seen=set();clean=[]
    for r in out:
        key=(r["xbrl_url"],str(r.get("period_end")))
        if key not in seen:seen.add(key);clean.append(r)
    return clean
def _local(tag):return tag.rsplit("}",1)[-1]
def _contexts(root):
    ctx={}
    for c in root.findall('.//{*}context'):
        cid=c.attrib.get('id')
        if not cid:continue
        instant=c.find('.//{*}instant'); start=c.find('.//{*}startDate'); end=c.find('.//{*}endDate')
        ctx[cid]={"instant":_dt(instant.text if instant is not None else None),"start":_dt(start.text if start is not None else None),"end":_dt(end.text if end is not None else None)}
    return ctx
def _metric_for_tag(tag):
    t=_local(tag).lower()
    for metric,aliases in METRIC_ALIASES.items():
        for a in aliases:
            if a.lower() in t:return metric
    return None
def parse_xbrl(xml,filing):
    root=ET.fromstring(xml);ctx=_contexts(root);rows=[]
    for fact in root.iter():
        metric=_metric_for_tag(fact.tag); value=_num(fact.text)
        if not metric or value is None:continue
        c=ctx.get(fact.attrib.get("contextRef"),{}); period_end=c.get("end") or c.get("instant")
        if not period_end:continue
        rows.append({"metric":metric,"value":value,"unit":fact.attrib.get("unitRef"),"period_end":period_end,"period_start":c.get("start"),"duration_days":((c.get("end")-c.get("start")).days if c.get("end") and c.get("start") else 0),"available_at":filing["available_at"],"source_url":filing["xbrl_url"],"source_type":"NSE_XBRL","isin":filing.get("isin"),"symbol":filing.get("symbol")})
    ded={}
    for r in rows:ded[(r["metric"],r["period_end"],r["isin"],r["symbol"])]=r
    return list(ded.values())
class NSEFinancialIngestor:
    def __init__(self):
        self.adapter=NSEAdapter()
        self.browser=None
    def catalog(self,symbol=None,start=None,end=None,page_size=100,issuer=None):
        payload={"type":"Integrated Filing- Financials","page":1,"size":page_size,"index":"equities","period_ended":"all"}
        if symbol: payload["symbol"]=symbol
        if issuer: payload["issuer"]=issuer
        if start and end: payload["from_date"]=start.strftime("%d-%m-%Y"); payload["to_date"]=end.strftime("%d-%m-%Y")
        r=self.adapter.get("https://www.nseindia.com/api/integrated-filing-results",params=payload)
        if r.status=="OK":
            import json
            try:
                data=json.loads(r.content.decode("utf-8")); rows=extract_filing_rows(data)
                if rows: return {"status":"OK","rows":rows,"raw":data}
            except Exception as ex:
                plain_error=f'plain catalog parse: {type(ex).__name__}: {ex}'
        else:
            plain_error='plain catalog returned no usable XBRL rows'
        try:
            if self.browser is None:
                from .nse_browser import NSEBrowserCatalog
                self.browser=NSEBrowserCatalog()
            br=self.browser.fetch(symbol,start,end,page=1,size=page_size,issuer=issuer)
            if br.get("status")!="OK":
                return {"status":br.get("status","DATA_UNAVAILABLE"),"rows":[],"detail":f"{plain_error}; {br.get('detail')}"}
            data=br.get("raw"); rows=extract_filing_rows(data)
            if not rows:
                return {"status":"NO_XBRL_ROWS","rows":[],"detail":f"{plain_error}; browser returned no XBRL rows","raw":data}
            try:
                legacy=self.browser.fetch_legacy(symbol,period="Quarterly")
                legacy_rows=extract_filing_rows(legacy.get("raw")) if legacy.get("status")=="OK" else []
            except Exception:
                legacy_rows=[]
            merged={ (x["xbrl_url"],str(x.get("period_end"))):x for x in legacy_rows+rows }
            return {"status":"OK","rows":list(merged.values()),"raw":data}
        except Exception as ex:
            return {"status":"DATA_UNAVAILABLE","rows":[],"detail":f"{plain_error}; NSE browser fallback: {type(ex).__name__}: {ex}"}
    def _parse_ixbrl_html(self, raw, filing):
        soup=BeautifulSoup(raw, "html.parser")
        contexts={}
        for el in soup.find_all(lambda t: getattr(t, "name", "") and str(t.name).lower().split(":")[-1]=="context"):
            cid=el.get("id")
            if not cid: continue
            def txt(local):
                node=el.find(lambda t: getattr(t,"name","") and str(t.name).lower().split(":")[-1]==local.lower())
                return node.get_text(strip=True) if node else None
            contexts[cid]={"instant":_dt(txt("instant")),"start":_dt(txt("startDate")),"end":_dt(txt("endDate"))}
        rows=[]
        for el in soup.find_all(lambda t: getattr(t, "name", "") and str(t.name).lower().split(":")[-1] in ("nonfraction","nonnumeric")):
            name=el.get("name") or ""
            metric=_metric_for_tag(name)
            if not metric: continue
            ref=el.get("contextref") or el.get("contextRef")
            ctx=contexts.get(ref,{})
            period_end=ctx.get("end") or ctx.get("instant")
            if not period_end: continue
            text=re.sub(r"\s+"," ",el.get_text(" ",strip=True)).strip()
            scale=el.get("scale")
            try: multiplier=10 ** int(scale or 0)
            except Exception: multiplier=1
            sign=el.get("sign") or ""
            if text in ("","-","—","–","N/A","NA"): continue
            value=_num(text.replace("(","-").replace(")",""))
            if value is None: continue
            value*=multiplier
            if sign.strip()=="-" and value>0: value=-value
            rows.append({"metric":metric,"value":value,"unit":el.get("unitref") or el.get("unitRef"),
                         "period_end":period_end,"period_start":ctx.get("start"),
                         "duration_days":((ctx.get("end")-ctx.get("start")).days if ctx.get("end") and ctx.get("start") else 0),
                         "available_at":filing.get("available_at"),"source_url":filing["xbrl_url"],
                         "source_type":"NSE_IXBRL","isin":filing.get("isin"),"symbol":filing.get("symbol")})
        ded={}
        for r in rows: ded[(r["metric"],r["period_end"],r.get("isin"),r.get("symbol"))]=r
        return list(ded.values())

    def parse_document(self,filing):
        r=self.adapter.get(filing["xbrl_url"],retries=4,delay=1.0)
        if r.status!='OK':return {"status":r.status,"rows":[],"detail":r.detail}
        raw=r.content
        try:
            if b"<html" not in raw[:5000].lower() and b"ix:nonfraction" not in raw[:5000].lower():
                rows=parse_xbrl(raw,filing)
                if rows:return {"status":"OK","rows":rows}
            rows=self._parse_ixbrl_html(raw,filing)
            if rows:return {"status":"OK","rows":rows}
            rows=parse_xbrl(raw,filing)
            return {"status":"OK" if rows else "NO_METRICS","rows":rows,"detail":None if rows else "No recognized NSE XBRL/iXBRL facts"}
        except Exception as e:
            try:
                rows=self._parse_ixbrl_html(raw,filing)
                return {"status":"OK" if rows else "PARSE_ERROR","rows":rows,"detail":None if rows else str(e)}
            except Exception:
                return {"status":"PARSE_ERROR","rows":[],"detail":str(e)}
