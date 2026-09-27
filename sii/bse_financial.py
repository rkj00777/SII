"""Free BSE financial-results/XBRL ingestion.

BSE is used as a second exchange source. The client intentionally uses only
public BSE endpoints and official filing attachments. It records exchange
dissemination time so historical snapshots can be reconstructed PIT.
"""
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from .adapters import BSEAdapter

ALIASES={
 "revenue":["revenuefromoperations","revenue","income","turnover","revenuefromoperation"],
 "pat":["profitloss","profitfortheperiod","profitaftertax","netprofit","profitlossattributable"],
 "ebit":["ebit","earningsbeforeinterestandtax","operatingprofit"],
 "ebitda":["ebitda","earningsbeforeinteresttaxdepreciationandamortisation"],
 "cfo":["cashflowsfromusedinoperatingactivities","netcashgeneratedfromoperatingactivities","cashgeneratedfromoperations"],
 "capex":["purchaseofpropertyplantandequipment","paymentstoacquirepropertyplantandequipment","purchaseoftangibleassets"],
 "debt":["borrowings","debt","borrowingscurrentandnoncurrent","financialliabilities"],
 "cash":["cashandcashequivalents","cashandbankbalances","cash"],
 "equity":["equity","equityattributabletoownersofparent","shareholdersequity"],
 "shares":["numberofsharesoutstanding","equitysharesoutstanding"],
}
def _dt(v):
    if not v:return None
    s=str(v).strip().replace("Z","+00:00")
    for f in ("%Y-%m-%dT%H:%M:%S%z","%Y-%m-%d","%d-%b-%Y %H:%M:%S","%d-%b-%Y"):
        try:return datetime.strptime(s,f).replace(tzinfo=None)
        except ValueError:pass
    try:return datetime.fromisoformat(s).replace(tzinfo=None)
    except:return None
def _num(v,scale=0,sign=""):
    try:
        x=float(Decimal(str(v).replace(",","").strip()))
        if scale: x*=10**int(scale)
        if str(sign).strip()=="-": x=-x
        return x
    except:return None
def _metric(name):
    n=str(name).rsplit("}",1)[-1].replace("_","").lower()
    for m,als in ALIASES.items():
        if any(a in n for a in als): return m
    return None
class BSEFinancialIngestor:
    def __init__(self):
        self.adapter=BSEAdapter()
    def catalog(self,scripcode,start,end,max_pages=10):
        rows=[]
        for page in range(1,max_pages+1):
            r=self.adapter.announcements(scripcode,start,end,page)
        if r.status!="OK":
            try:
                from .bse_browser import BSEBrowser
                r2=BSEBrowser().announcements(scripcode,start,end,page)
                if r2.get("status")=="OK":
                    class R: pass
                    rr=R(); rr.status="OK"; rr.content=json.dumps(r2.get("raw")).encode(); r=rr
            except Exception: pass
            if r.status!="OK": return {"status":r.status,"rows":rows,"detail":r.detail}
            try:data=__import__("json").loads(r.content.decode("utf-8"))
            except Exception as e:return {"status":"PARSE_ERROR","rows":rows,"detail":str(e)}
            page_rows=data.get("Table",[]) if isinstance(data,dict) else []
            if not page_rows: break
            for x in page_rows:
                txt=" ".join(str(x.get(k,"")) for k in ("NEWSSUB","HEADLINE","CATEGORYNAME"))
                if "result" not in txt.lower() and "financial" not in txt.lower(): continue
                news=x.get("NEWSID") or x.get("NewsId")
                sc=x.get("SCRIP_CD") or x.get("ScripCode") or scripcode
                if not news: continue
                url=f"https://www.bseindia.com/Msource/90D/CorpXbrlGen.aspx?Bsenewid={news}&Scripcode={sc}"
                rows.append({"scripcode":str(sc),"news_id":str(news),"period_end":x.get("QUARTER_ID") or x.get("EndDate"),
                             "available_at":_dt(x.get("DissemDT") or x.get("DT_TM") or x.get("News_submission_dt")),
                             "xbrl_url":url,"attachment_url":(f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{x.get('ATTACHMENTNAME')}" if x.get("ATTACHMENTNAME") else None),
                             "raw":x})
            if len(page_rows)<50: break
        return {"status":"OK","rows":rows}
    def parse_document(self,filing):
        r=self.adapter.get(filing["xbrl_url"])
        if r.status!="OK":
            return {"status":r.status,"rows":[],"detail":r.detail}
        raw=r.content.decode("utf-8","replace")
        soup=BeautifulSoup(raw,"html.parser")
        contexts={}
        for el in soup.find_all(["xbrli:context","context"]):
            cid=el.get("id")
            if not cid: continue
            inst=el.find(["xbrli:instant","instant"])
            start=el.find(["xbrli:startdate","startdate"])
            end=el.find(["xbrli:enddate","enddate"])
            contexts[cid]={"instant":_dt(inst.get_text(strip=True)) if inst else None,
                            "start":_dt(start.get_text(strip=True)) if start else None,
                            "end":_dt(end.get_text(strip=True)) if end else None}
        facts=[]
        for el in soup.find_all(["ix:nonfraction","nonfraction","ix:nonnumeric","nonnumeric"]):
            name=el.get("name") or el.get("contextref") or ""
            metric=_metric(name)
            if not metric: continue
            ctx=contexts.get(el.get("contextref"),{})
            val=_num(el.get_text(" ",strip=True),el.get("scale") or 0,el.get("sign") or "")
            if val is None: continue
            end=ctx.get("end") or ctx.get("instant")
            if not end: continue
            facts.append({"metric":metric,"value":val,"unit":el.get("unitref"),
                          "period_end":end,"period_start":ctx.get("start"),
                          "duration_days":((end-ctx["start"]).days if ctx.get("start") else 0),
                          "available_at":filing.get("available_at"),
                          "source_url":filing["xbrl_url"],"source_type":"BSE_XBRL",
                          "scripcode":filing.get("scripcode")})
        return {"status":"OK" if facts else "NO_METRICS","rows":facts,
                "detail":None if facts else "No recognized iXBRL facts"}
