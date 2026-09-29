"""Empirical six-module validation for SII.

Modules 1-5 come from the PIT fundamental selector. Module 6 is reconstructed
from NSE corporate announcements using only records disseminated on or before
each decision timestamp. It is an evidence-gated confirmation test.
"""
import json, re
from pathlib import Path
from datetime import timedelta
import pandas as pd
from .adapters import NSEAdapter

CATALYST_RE = re.compile(
    r"order|contract|award|order book|capacity|expansion|commission|"
    r"new plant|production|manufactur|export|strategic|partnership|"
    r"project|approval|commercial production|customer|business win|"
    r"large order|major order|supply agreement|long term agreement|"
    r"acquisition|investment|capex|facility|volume|demand", re.I)

def _pit():
    p=Path("artifacts/pit_fundamental_backtest.json")
    if not p.exists(): p=Path("reports/latest-pit-fundamental-backtest.json")
    return json.loads(p.read_text()) if p.exists() else {}

def _selected():
    p=Path("artifacts/pit_fundamental_selected.csv")
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

def _available(r):
    for k in ("exchdisstime","an_dt","sort_date","broadcastDateTime","broadcastDate"):
        d=pd.to_datetime(r.get(k),errors="coerce")
        if not pd.isna(d): return d.to_pydatetime().replace(tzinfo=None)
    return None

def _fetch(symbol,start,end,adapter):
    cp=Path("artifacts/module6_announcements")/f"{str(symbol).replace('/','_')}.json"
    cp.parent.mkdir(parents=True,exist_ok=True)
    if cp.exists():
        try:
            x=json.loads(cp.read_text())
            if isinstance(x,list): return x
        except Exception: pass
    try:
        params={"index":"equities","symbol":str(symbol),
                "from_date":start.strftime("%d-%m-%Y"),
                "to_date":end.strftime("%d-%m-%Y")}
        r=adapter.get("https://www.nseindia.com/api/corporate-announcements",params=params)
        if r.status!="OK": return []
        x=json.loads(r.content.decode("utf-8"))
        rows=x if isinstance(x,list) else x.get("data",x.get("rows",[]))
        if not isinstance(rows,list): rows=[]
        cp.write_text(json.dumps(rows,default=str))
        return rows
    except Exception:
        return []

def run():
    pit=_pit(); sel=_selected()
    modules={k:{"historical_status":"EMPIRICALLY_TESTED","source":"PIT fundamental selector"}
             for k in ("valuation_gap","earnings_acceleration","cash_conversion",
                       "reinvestment_roic","governance_balance_sheet")}
    modules["industry_catalyst"]={"historical_status":"NOT_VALIDATED",
        "source":"NSE dated corporate-announcement evidence, PIT-filtered"}
    if sel.empty:
        report={"status":"OK","validation_type":"empirical_six_module_validation",
          "modules":modules,"modules_empirically_tested":5,"modules_total":6,
          "module_coverage":5/6,"sixth_module_historical_evidence_available":False,
          "pit_selector_status":pit.get("status"),"selected_observations":pit.get("selected_observations",0),
          "fundamental_coverage_rate":pit.get("fundamental_coverage_rate",0),
          "full_six_module_empirical_validation_ready":False,
          "reason":"No PIT selected-observation CSV was produced."}
    else:
        sel["rebalance_date"]=pd.to_datetime(sel["rebalance_date"],errors="coerce")
        adapter=NSEAdapter(); out=[]
        for symbol,g in sel.groupby("symbol"):
            rows=_fetch(symbol,
                (g.rebalance_date.min()-pd.Timedelta(days=365)).to_pydatetime(),
                g.rebalance_date.max().to_pydatetime(),adapter)
            for _,o in g.iterrows():
                decision=o.rebalance_date.to_pydatetime().replace(hour=15,minute=30,second=0)
                hit=0
                for a in rows:
                    av=_available(a)
                    txt=" ".join(str(a.get(k) or "") for k in ("desc","attchmntText","subject","details"))
                    if av and av<=decision and av>=decision-timedelta(days=365) and CATALYST_RE.search(txt):
                        hit+=1
                out.append({"symbol":symbol,"rebalance_date":o.rebalance_date,
                    "max_return":pd.to_numeric(o.get("max_return"),errors="coerce"),
                    "module6_evidence":hit>0,"module6_evidence_count":hit})
        ev=pd.DataFrame(out)
        base=float(ev.max_return.ge(1).mean()) if len(ev) else None
        pos=ev[ev.module6_evidence] if len(ev) else ev
        posrate=float(pos.max_return.ge(1).mean()) if len(pos) else None
        lift=(posrate/base) if base else None
        evidence_rate=float(ev.module6_evidence.mean()) if len(ev) else 0.0
        status="EMPIRICALLY_TESTED" if len(ev)>=500 and evidence_rate>=0.05 else "NOT_VALIDATED_LOW_EVIDENCE"
        modules["industry_catalyst"].update({
            "historical_status":status,"selected_observations_tested":int(len(ev)),
            "evidence_rate":evidence_rate,"catalyst_positive_100pct_rate":posrate,
            "base_selected_100pct_rate":base,"catalyst_lift_100":lift,
            "lookahead_rule":"announcement dissemination timestamp <= decision timestamp",
            "source":"NSE corporate-announcements API"})
        if len(ev): ev.to_csv("artifacts/module6_empirical_observations.csv",index=False)
        tested=sum(v["historical_status"]=="EMPIRICALLY_TESTED" for v in modules.values())
        pit_ok=(pit.get("status")=="OK" and pit.get("selected_observations",0)>=500
          and pit.get("fundamental_coverage_rate",0)>=.70
          and (pit.get("selection_lift_100") or 0)>=1.05
          and pit.get("independent_era_positive_lifts",0)>=2
          and bool(pit.get("lookahead_checks",{}).get("future_revisions_excluded"))
          and bool(pit.get("lookahead_checks",{}).get("filing_available_at_lte_decision")))
        report={"status":"OK","validation_type":"empirical_six_module_validation",
          "modules":modules,"modules_empirically_tested":tested,"modules_total":6,
          "module_coverage":tested/6,"sixth_module_historical_evidence_available":status=="EMPIRICALLY_TESTED",
          "pit_selector_status":pit.get("status"),"selected_observations":pit.get("selected_observations",0),
          "fundamental_coverage_rate":pit.get("fundamental_coverage_rate",0),
          "selection_lift_100":pit.get("selection_lift_100"),
          "independent_eras":pit.get("independent_era_falsification",[]),
          "lookahead_clean":bool(pit.get("lookahead_checks",{}).get("future_revisions_excluded")) and bool(pit.get("lookahead_checks",{}).get("filing_available_at_lte_decision")),
          "five_module_empirical_validation_ready":pit_ok,
          "full_six_module_empirical_validation_ready":bool(pit_ok and status=="EMPIRICALLY_TESTED" and (lift or 0)>=1.0 and len(ev)>=500),
          "reason":"Module 6 uses only dated exchange disclosures known by each decision timestamp."}
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/six_module_empirical_validation.json").write_text(json.dumps(report,indent=2,default=str))
    return report

if __name__=="__main__": print(json.dumps(run(),indent=2,default=str))
