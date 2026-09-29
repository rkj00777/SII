"""Free NSE financial/XBRL ingestion."""
from datetime import datetime
from decimal import Decimal
import xml.etree.ElementTree as ET
import re
import html
import os
import pandas as pd
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
def _local(tag):return tag.rsplit("}",1)[-1] if isinstance(tag,str) else ""
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
def _sanitize_html_entities(xml):
    if isinstance(xml, bytes):
        text=xml.decode("utf-8","replace")
    else:
        text=str(xml)
    protected={"amp","lt","gt","quot","apos"}
    def repl(m):
        name=m.group(1)
        if name in protected: return m.group(0)
        val=html.entities.html5.get(name+";")
        if val is None: val=html.entities.html5.get(name)
        return val if val is not None else ""
    return re.sub(r"&([A-Za-z][A-Za-z0-9]+);", repl, text).encode("utf-8")

def parse_xbrl(xml,filing):
    clean=_sanitize_html_entities(xml)
    try:
        root=ET.fromstring(clean)
    except ET.ParseError:
        from lxml import etree as LET
        parser=LET.XMLParser(recover=True, huge_tree=True, resolve_entities=False)
        root=LET.fromstring(clean, parser=parser)
    ctx=_contexts(root);rows=[]
    for fact in root.iter():
        if not isinstance(fact.tag,str): continue
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
        # NSE's Integrated Filing - Financials is the post-2024/25 feed. The
        # 2019-2024 PIT window must use the legacy Financial Results endpoint,
        # which exposes historical XBRL links. Do not depend on the newer feed
        # for the historical validation period.
        historical = bool(start and start.year < 2025)
        try:
            # Prefer the direct NSE API path. It does not require Playwright and
            # avoids the Chromium/NSE ERR_HTTP2_PROTOCOL_ERROR failure seen in CI.
            # Playwright remains a last-resort compatibility fallback only.
            import json
            if historical:
                payload={"index":"equities","period":"Quarterly","page":1,"size":page_size}
                if symbol: payload["symbol"]=symbol
                r=self.adapter.get("https://www.nseindia.com/api/corporates-financial-results",params=payload)
                if r.status=="OK":
                    data=json.loads(r.content.decode("utf-8"))
                    rows=self._filter_filing_rows(extract_filing_rows(data),start,end)
                    if rows:
                        return {"status":"OK","rows":rows,"raw":data,"source":"legacy_financial_results_direct_api"}
                    direct_detail="Direct legacy API returned no XBRL rows in requested window."
                else:
                    direct_detail=f"Direct legacy API status={r.status}"
                # Last resort: browser.
                if self.browser is None:
                    from .nse_browser import NSEBrowserCatalog
                    self.browser=NSEBrowserCatalog()
                legacy=self.browser.fetch_legacy(symbol,period="Quarterly",start=None,end=None,page=1,size=page_size)
                rows=self._filter_filing_rows(extract_filing_rows(legacy.get("raw")),start,end) if legacy.get("status")=="OK" else []
                if rows:return {"status":"OK","rows":rows,"raw":legacy.get("raw"),"source":"legacy_financial_results_browser"}
                return {"status":"NO_XBRL_ROWS","rows":[],"detail":f"{direct_detail}; browser fallback returned no rows"}

            payload={"type":"Integrated Filing- Financials","page":1,"size":page_size,"index":"equities","period_ended":"all"}
            if symbol: payload["symbol"]=symbol
            if issuer: payload["issuer"]=issuer
            if start and end: payload["from_date"]=start.strftime("%d-%m-%Y"); payload["to_date"]=end.strftime("%d-%m-%Y")
            r=self.adapter.get("https://www.nseindia.com/api/integrated-filing-results",params=payload)
            if r.status=="OK":
                try:
                    data=json.loads(r.content.decode("utf-8")); rows=extract_filing_rows(data)
                    if rows: return {"status":"OK","rows":rows,"raw":data,"source":"integrated_filing"}
                except Exception as ex:
                    plain_error=f"plain catalog parse: {type(ex).__name__}: {ex}"
            else: plain_error=f"Direct integrated API status={r.status}"
            # Browser compatibility fallback.
            if self.browser is None:
                from .nse_browser import NSEBrowserCatalog
                self.browser=NSEBrowserCatalog()
            br=self.browser.fetch(symbol,start,end,page=1,size=page_size,issuer=issuer)
            if br.get("status")!="OK":
                return {"status":br.get("status","DATA_UNAVAILABLE"),"rows":[],"detail":f"{plain_error}; {br.get('detail')}"}
            data=br.get("raw"); rows=extract_filing_rows(data)
            try:
                legacy=self.browser.fetch_legacy(symbol,period="Quarterly",start=None,end=None)
                legacy_rows=extract_filing_rows(legacy.get("raw")) if legacy.get("status")=="OK" else []
            except Exception: legacy_rows=[]
            merged={ (x["xbrl_url"],str(x.get("period_end"))):x for x in legacy_rows+rows }
            merged=self._filter_filing_rows(list(merged.values()),start,end)
            if not merged:
                return {"status":"NO_XBRL_ROWS","rows":[],"detail":f"{plain_error}; browser integrated+legacy returned no XBRL rows","raw":data}
            return {"status":"OK","rows":merged,"raw":data}
        except Exception as ex:
            return {"status":"DATA_UNAVAILABLE","rows":[],"detail":f"NSE filing catalog: {type(ex).__name__}: {ex}"}

    @staticmethod
    def _filter_filing_rows(rows,start,end):
        if not rows:return []
        out=[]
        lo=pd.to_datetime(start) if start is not None else None
        hi=pd.to_datetime(end) if end is not None else None
        for row in rows:
            pe=pd.to_datetime(row.get("period_end"),errors="coerce")
            if pd.isna(pe): continue
            if lo is not None and pe < lo: continue
            if hi is not None and pe > hi: continue
            out.append(row)
        return out
    def _parse_financial_html(self, raw, filing):
        soup=BeautifulSoup(raw, "html.parser")
        text_all=soup.get_text(" ",strip=True)
        starts=re.findall(r"Date of start of reporting period\s+(\d{2}-\d{2}-\d{4})",text_all,re.I)
        ends=re.findall(r"Date of end of reporting period\s+(\d{2}-\d{2}-\d{4})",text_all,re.I)
        start=self._parse_date_text(starts[0]) if starts else None
        end=self._parse_date_text(ends[0]) if ends else None
        if not end:return []
        duration=(end-start).days if start and end else 0
        aliases={
            "revenue":["revenue from operations"],
            "pat":["net profit loss for the period from continuing operations","total profit (loss) for period","profit or loss, attributable to owners of parent"],
            "pbt":["total profit before exceptional items and tax"],
            "interest":["finance costs"],
            "depreciation":["depreciation, depletion and amortisation expense","depreciation, depletion and amortisation"],
            "shares_capital":["paid-up equity share capital"],
            "face_value":["face value of equity share capital"],
            "eps":["basic earnings (loss) per share from continuing operations","basic earnings (loss) per share"],
            "debt_equity":["debt equity ratio"],
        }
        rows=[]
        for tr in soup.find_all("tr"):
            cells=[c.get_text(" ",strip=True) for c in tr.find_all(["th","td"])]
            if len(cells)<2: continue
            label=" ".join(cells[:-1]).strip().lower()
            for metric,keys in aliases.items():
                if not any(k in label for k in keys): continue
                nums=[]
                for cell in cells[1:]:
                    for m in re.findall(r"(?<!\w)-?\(?\d[\d,]*(?:\.\d+)?\)?",cell):
                        z=m.replace(",","").replace("(","-").replace(")","")
                        try: nums.append(float(z))
                        except Exception: pass
                if not nums: continue
                value=nums[0]
                rows.append({"metric":metric,"value":value,"unit":"INR_LAKH",
                             "period_end":end,"period_start":start,"duration_days":duration,
                             "available_at":filing.get("available_at"),"source_url":filing["xbrl_url"],
                             "source_type":"NSE_FINANCIAL_RESULTS_HTML","isin":filing.get("isin"),"symbol":filing.get("symbol")})
                break
        # Derive EBIT/EBITDA and shares from the disclosed IndAS table.
        vals={r["metric"]:r["value"] for r in rows}
        if "pbt" in vals and "interest" in vals:
            rows.append({"metric":"ebit","value":vals["pbt"]+vals["interest"],"unit":"INR_LAKH","period_end":end,"period_start":start,"duration_days":duration,
                         "available_at":filing.get("available_at"),"source_url":filing["xbrl_url"],"source_type":"NSE_FINANCIAL_RESULTS_HTML","isin":filing.get("isin"),"symbol":filing.get("symbol")})
        if "pbt" in vals and "interest" in vals and "depreciation" in vals:
            rows.append({"metric":"ebitda","value":vals["pbt"]+vals["interest"]+vals["depreciation"],"unit":"INR_LAKH","period_end":end,"period_start":start,"duration_days":duration,
                         "available_at":filing.get("available_at"),"source_url":filing["xbrl_url"],"source_type":"NSE_FINANCIAL_RESULTS_HTML","isin":filing.get("isin"),"symbol":filing.get("symbol")})
        if "shares_capital" in vals and "face_value" in vals and vals["face_value"]:
            rows.append({"metric":"shares","value":vals["shares_capital"]*100000/vals["face_value"],"unit":"SHARES","period_end":end,"period_start":start,"duration_days":duration,
                         "available_at":filing.get("available_at"),"source_url":filing["xbrl_url"],"source_type":"NSE_FINANCIAL_RESULTS_HTML","isin":filing.get("isin"),"symbol":filing.get("symbol")})
        return rows

    @staticmethod
    def _parse_date_text(v):
        try:return datetime.strptime(v,"%d-%m-%Y")
        except Exception:return None

    def _parse_ixbrl_html(self, raw, filing):
        soup=BeautifulSoup(raw, "html.parser")
        contexts={}
        for el in soup.find_all(re.compile(r"(^|:)context$", re.I)):
            cid=el.get("id")
            if not cid: continue
            def txt(local):
                node=el.find(re.compile(r"(^|:)"+re.escape(local)+r"$", re.I))
                return node.get_text(strip=True) if node else None
            contexts[cid]={"instant":_dt(txt("instant")),"start":_dt(txt("startDate")),"end":_dt(txt("endDate"))}
        rows=[]
        for el in soup.find_all(re.compile(r"(^|:)non(fraction|numeric)$", re.I)):
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
        if os.getenv("SII_DEBUG_FILINGS")=="1":
            from pathlib import Path
            p=Path(os.getenv("SII_OUTPUT_DIR","artifacts")); p.mkdir(parents=True,exist_ok=True)
            safe=re.sub(r"[^A-Za-z0-9_.-]","_",str(filing.get("symbol") or "filing"))
            (p/f"debug_{safe}.html").write_bytes(raw)
        try:
            # Prefer the namespace-aware recoverable XML/XHTML parser; fall back
            # to HTML parsing only when the document is not parseable as XHTML.
            rows=parse_xbrl(raw,filing)
            if rows:return {"status":"OK","rows":rows}
            rows=self._parse_financial_html(raw,filing)
            if rows:return {"status":"OK","rows":rows}
            rows=self._parse_ixbrl_html(raw,filing)
            if rows:return {"status":"OK","rows":rows}
            soup=BeautifulSoup(raw, "html.parser")
            names=[str(t.name).lower() for t in soup.find_all()]
            context_count=sum(1 for n in names if n.endswith(":context") or n=="context")
            fact_count=sum(1 for n in names if n.endswith(":nonfraction") or n=="nonfraction")
            sample=[n for n in names if "fraction" in n or n.endswith(":context")][:20]
            return {"status":"NO_METRICS","rows":[],
                    "detail":f"No iXBRL facts; bytes={len(raw)}; head={raw[:240].decode("utf-8","replace").replace(chr(10)," ")!r}; contexts={context_count}; nonfraction={fact_count}; sample={sample}"}
        except Exception as e:
            try:
                rows=self._parse_ixbrl_html(raw,filing)
                return {"status":"OK" if rows else "PARSE_ERROR","rows":rows,"detail":None if rows else str(e)}
            except Exception:
                return {"status":"PARSE_ERROR","rows":[],"detail":str(e)}
