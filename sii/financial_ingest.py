"""Free NSE financial/XBRL ingestion."""
from datetime import datetime
from decimal import Decimal
import xml.etree.ElementTree as ET
from .adapters import NSEAdapter
METRIC_ALIASES={"revenue":["RevenueFromOperations","Revenue","IncomeFromOperations","Turnover"],"pat":["ProfitLoss","ProfitForThePeriod","ProfitAfterTax","NetProfit"],"ebit":["ProfitBeforeTax","ProfitBeforeTaxAndExceptionalItems","OperatingProfit"],"ebitda":["EBITDA","EarningsBeforeInterestTaxDepreciationAndAmortisation"],"cfo":["CashFlowsFromUsedInOperatingActivities","NetCashGeneratedFromOperatingActivities","CashGeneratedFromOperations"],"capex":["PurchaseOfPropertyPlantAndEquipment","PaymentsToAcquirePropertyPlantAndEquipment","PurchaseOfTangibleAssets"],"debt":["Borrowings","Debt","BorrowingsCurrentAndNonCurrent"],"cash":["CashAndCashEquivalents","CashAndBankBalances","Cash"],"equity":["Equity","EquityAttributableToOwnersOfParent","ShareholdersEquity"],"interest":["FinanceCosts","InterestExpense","FinanceCost"],"shares":["NumberOfSharesOutstanding","EquitySharesOutstanding","PaidUpEquityShareCapital"],"eps":["BasicEarningsLossPerShare","BasicEarningsPerShare","DilutedEarningsPerShare"]}
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
    for k in ("exchdisstime","exchangeDisseminationTime","sort_date","sortDate","broadcastDateTime","filingDateTime","filedAt"):
        d=_dt(row.get(k))
        if d:return d
    return datetime.utcnow()
def _walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values():yield from _walk(v)
    elif isinstance(obj,list):
        for v in obj:yield from _walk(v)
def extract_filing_rows(payload):
    out=[]
    for d in _walk(payload):
        lower={str(k).lower():v for k,v in d.items()}; xbrl=next((v for k,v in lower.items() if "xbrl" in k and isinstance(v,str) and v.startswith("http")),None)
        if not xbrl:
            for k,v in lower.items():
                if isinstance(v,str) and v.startswith("http") and ("xbrl" in v.lower() or v.lower().endswith(".xml")): xbrl=v; break
        if xbrl:
            isin=next((v for k,v in lower.items() if k in ("isin","sm_isin","isinno")),None); symbol=next((v for k,v in lower.items() if k in ("symbol","sym")),None); period=next((v for k,v in lower.items() if "period" in k and "end" in k),None)
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
        rows.append({"metric":metric,"value":value,"unit":fact.attrib.get("unitRef"),"period_end":period_end,"available_at":filing["available_at"],"source_url":filing["xbrl_url"],"source_type":"NSE_XBRL","isin":filing.get("isin"),"symbol":filing.get("symbol")})
    ded={}
    for r in rows:ded[(r["metric"],r["period_end"],r["isin"],r["symbol"])]=r
    return list(ded.values())
class NSEFinancialIngestor:
    def __init__(self):self.adapter=NSEAdapter()
    def catalog(self,symbol=None,start=None,end=None,page_size=100):
        payload={"type":"Integrated Filing- Financials","page":1,"size":page_size,"index":"equities"}
        if symbol:payload["symbol"]=symbol
        if start and end:payload["from_date"]=start.strftime("%d-%m-%Y");payload["to_date"]=end.strftime("%d-%m-%Y")
        r=self.adapter.get("https://www.nseindia.com/api/integrated-filing-results",params=payload)
        if r.status!='OK':return {"status":r.status,"rows":[],"detail":r.detail}
        import json
        try:data=json.loads(r.content.decode("utf-8"))
        except Exception as e:return {"status":"PARSE_ERROR","rows":[],"detail":str(e)}
        return {"status":"OK","rows":extract_filing_rows(data),"raw":data}
    def parse_document(self,filing):
        r=self.adapter.get(filing["xbrl_url"])
        if r.status!='OK':return {"status":r.status,"rows":[],"detail":r.detail}
        try:return {"status":"OK","rows":parse_xbrl(r.content,filing)}
        except Exception as e:return {"status":"PARSE_ERROR","rows":[],"detail":str(e)}
