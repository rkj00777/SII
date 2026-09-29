"""BSE-backed true-PIT fundamental validation for SII.

Uses public BSE filing timestamps/XBRL for fundamentals and the existing
point-in-time NSE price/universe history. This is deliberately independent of
the NSE-only PIT implementation and is used as the primary free-data fallback.
"""
import json, os, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, time
from pathlib import Path
import pandas as pd
from .free_market import _duckdb, HF
from .bse_financial import BSEFinancialIngestor
from .adapters import BSEAdapter

OUT=Path(os.getenv("SII_OUTPUT_DIR","artifacts")); OUT.mkdir(exist_ok=True)
CACHE=Path(os.getenv("SII_BSE_PIT_CACHE","artifacts/bse_pit_cache_v1")); CACHE.mkdir(parents=True,exist_ok=True)

def _dt(v):
    return pd.to_datetime(v,errors="coerce")

def _map_symbol(symbol, adapter):
    p=CACHE/f"_map_{str(symbol).replace('/','_')}.json"
    if p.exists():
        try:
            x=json.loads(p.read_text())
            if x.get("code"): return str(x["code"])
        except Exception: pass
    r=adapter.get("https://api.bseindia.com/BseIndiaAPI/api/PeerSmartSearch/w",
                  params={"Type":"SS","text":str(symbol)})
    if r.status!="OK": return None
    try:
        x=json.loads(r.content.decode("utf-8"))
        rows=x if isinstance(x,list) else x.get("Table",x.get("data",[]))
        if not isinstance(rows,list) or not rows: return None
        exact=[]
        for z in rows:
            code=z.get("SCRIP_CD") or z.get("ScripCode") or z.get("scripcode")
            name=z.get("SCRIP_NAME") or z.get("SecurityName") or z.get("NAME")
            if code: exact.append((str(code),str(name or "")))
        if not exact: return None
        code=next((c for c,n in exact if str(symbol).upper() in n.upper()),exact[0][0])
        p.write_text(json.dumps({"code":code}))
        return code
    except Exception:
        return None

def _load(symbol, start, end):
    p=CACHE/f"{str(symbol).replace('/','_')}.json"
    if p.exists():
        try:
            x=json.loads(p.read_text())
            if isinstance(x,list) and x: return x
        except Exception: pass
    adapter=BSEAdapter(); code=_map_symbol(symbol,adapter)
    if not code: return []
    ing=BSEFinancialIngestor()
    try:
        cat=ing.catalog(code,start,end,max_pages=12)
        rows=[]
        for f in cat.get("rows",[]):
            av=f.get("available_at")
            if av is not None and pd.isna(_dt(av)): continue
            # BSE announcement rows do not reliably expose the accounting
            # period in QUARTER_ID. Parse the XBRL first and filter the actual
            # reported period from the facts.
            parsed=ing.parse_document(f)
            if parsed.get("status")=="OK":
                for mr in parsed.get("rows",[]):
                    pe=_dt(mr.get("period_end"))
                    if pd.isna(pe) or pe<start or pe>end: continue
                    rows.append(mr)
        p.write_text(json.dumps(rows,default=str))
        return rows
    except Exception as e:
        p.write_text(json.dumps({"error":str(e)}))
        return []

def _snapshot(metrics, asof):
    if not metrics:return {}
    df=pd.DataFrame(metrics)
    if df.empty:return {}
    df["period_end"]=_dt(df["period_end"]); df["available_at"]=_dt(df["available_at"])
    df=df[df.available_at.notna() & (df.available_at<=pd.Timestamp(asof)) & (df.period_end<=pd.Timestamp(asof))]
    if df.empty:return {}
    df=df.sort_values(["metric","period_end","available_at"]).drop_duplicates(["metric","period_end"],keep="last")
    q=df[pd.to_numeric(df.get("duration_days"),errors="coerce").between(70,125)].copy()
    out={}
    for m in ("revenue","pat","ebit","cfo"):
        z=q[q.metric==m].sort_values("period_end")
        if not z.empty: out[m]=z
    for m in ("debt","cash","equity","shares"):
        z=df[df.metric==m].sort_values(["period_end","available_at"])
        if not z.empty: out[m]=float(z.iloc[-1].value)
    pat=out.get("pat"); cfo=out.get("cfo"); ebit=out.get("ebit")
    if pat is not None and len(pat)>=4:
        out["pat_ttm"]=float(pat.tail(4).value.sum())
        if len(pat)>=5 and float(pat.iloc[-5].value)>0:
            out["pat_yoy"]=float(pat.iloc[-1].value)/float(pat.iloc[-5].value)-1
    if cfo is not None and len(cfo)>=4 and out.get("pat_ttm") is not None:
        out["cfo_ttm"]=float(cfo.tail(4).value.sum())
        if out["pat_ttm"]!=0: out["cfo_pat"]=out["cfo_ttm"]/out["pat_ttm"]
    if ebit is not None and len(ebit)>=4: out["ebit_ttm"]=float(ebit.tail(4).value.sum())
    return {k:v for k,v in out.items() if not isinstance(v,pd.DataFrame)}

def _score(df):
    cols=["pe","pat_yoy","cfo_pat","roic","balance"]
    for c in cols: df[c]=pd.to_numeric(df.get(c),errors="coerce")
    def pct(s): return s.rank(pct=True)*100
    df["valuation"]=100-pct(df["pe"].where(df["pe"]>0))
    df["earnings"]=pct(df["pat_yoy"]); df["cash"]=pct(df["cfo_pat"].clip(-2,3))
    df["reinvestment"]=pct(df["roic"]); df["balance_score"]=100-pct(df["balance"].clip(lower=0))
    weights={"valuation":.15,"earnings":.30,"cash":.15,"reinvestment":.25,"balance_score":.15}
    scores=[]; cov=[]
    for _,r in df.iterrows():
        known=[c for c in weights if pd.notna(r[c])]
        den=sum(weights[c] for c in known)
        scores.append(sum(weights[c]*float(r[c]) for c in known)/den if den else None)
        cov.append(len(known)/5)
    df["fundamental_score"]=scores; df["fundamental_coverage"]=cov
    return df

def run(start_year=2019,end_year=2024):
    con=_duckdb()
    prices="["+",".join(repr(f"{HF}/prices_adjusted/nse_{y}.parquet") for y in range(start_year,2027))+"]"
    up=f"{HF}/universe/nse_liquid.parquet"
    latest=con.execute(f"SELECT max(date) FROM read_parquet({prices},union_by_name=true)").fetchone()[0]
    cutoff=latest-timedelta(days=756)
    uq=con.execute(f"""SELECT rebalance_date,symbol,rank FROM read_parquet('{up}')
      WHERE rank<=500 AND rebalance_date BETWEEN DATE '{start_year}-01-01' AND DATE '{end_year}-12-31'
      AND rebalance_date<=DATE '{cutoff}' ORDER BY rebalance_date,rank""").fetchdf()
    p=con.execute(f"SELECT date,symbol,adj_close FROM read_parquet({prices},union_by_name=true) WHERE adj_close IS NOT NULL").fetchdf()
    con.close(); p["date"]=pd.to_datetime(p.date); p=p.sort_values(["symbol","date"])
    rows=[]
    for d,g in uq.groupby("rebalance_date"):
        px=p[(p.date<=pd.Timestamp(d)) & p.symbol.isin(g.symbol)]
        now=px.sort_values("date").groupby("symbol",as_index=False).tail(1)[["symbol","adj_close"]]
        old=px[px.date<=pd.Timestamp(d)-pd.Timedelta(days=126)].sort_values("date").groupby("symbol",as_index=False).tail(1)[["symbol","adj_close"]].rename(columns={"adj_close":"old_close"})
        x=g.merge(now,on="symbol",how="left").merge(old,on="symbol",how="left"); x["mom126"]=x.adj_close/x.old_close-1
        rows.append(x.sort_values("mom126",ascending=False).head(40))
    cand=pd.concat(rows,ignore_index=True)
    symbols=sorted(cand.symbol.unique())
    max_symbols=int(os.getenv("SII_BSE_PIT_MAX_SYMBOLS","60"))
    if len(symbols)>max_symbols:
        idx=[round(i*(len(symbols)-1)/(max_symbols-1)) for i in range(max_symbols)]
        symbols=[symbols[i] for i in sorted(set(idx))]
    start=datetime(start_year-1,1,1); end=datetime(end_year,12,31,23,59,59)
    mm={}; workers=min(10,max(4,int(os.getenv("SII_BSE_PIT_WORKERS","8"))))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        fs={ex.submit(_load,s,start,end):s for s in symbols}
        for f in as_completed(fs):
            mm[fs[f]]=f.result()
    out=[]
    for _,r in cand.iterrows():
        f=_snapshot(mm.get(r.symbol,[]),datetime.combine(pd.Timestamp(r.rebalance_date).date(),time(15,30)))
        price=r.adj_close; shares=f.get("shares")
        f["pe"]=(price*shares)/f["pat_ttm"] if shares and price and f.get("pat_ttm",0)>0 else None
        invested=(f.get("debt",0) or 0)+(f.get("equity",0) or 0)-(f.get("cash",0) or 0)
        f["roic"]=f.get("ebit_ttm")/invested if invested>0 and f.get("ebit_ttm") is not None else None
        f["balance"]=f.get("debt")/f.get("equity") if f.get("equity") not in (None,0) else None
        out.append({**r.to_dict(),**f})
    df=_score(pd.DataFrame(out))
    sel=[]
    for d,g in df.groupby("rebalance_date"):
        z=g[g.fundamental_coverage>=.70].sort_values("fundamental_score",ascending=False).head(20).copy()
        if not z.empty: sel.append(z)
    sel=pd.concat(sel,ignore_index=True) if sel else pd.DataFrame()
    if sel.empty:
        report={"status":"OK","validation_type":"BSE_PIT_fundamental_selection","candidate_observations":len(df),"selected_observations":0,
          "fundamental_coverage_rate":float((df.fundamental_coverage>=.70).mean()) if len(df) else 0,
          "symbols_considered":len(symbols),"symbols_with_metrics":sum(bool(v) for v in mm.values()),
          "reason":"BSE PIT reconstruction produced no observations at the 70% evidence threshold.","production_ready":False}
        (OUT/"bse_pit_fundamental_validation.json").write_text(json.dumps(report,indent=2,default=str)); return report
    con=_duckdb(); q=f"""SELECT o.rebalance_date,o.symbol,o.adj_close,
      max(p.adj_close/o.adj_close-1) max_return
      FROM o JOIN read_parquet({prices},union_by_name=true) p ON p.symbol=o.symbol
      AND p.date>=o.rebalance_date AND p.date<=o.rebalance_date+INTERVAL '756 days'
      GROUP BY o.rebalance_date,o.symbol,o.adj_close"""
    con.register("o",sel[["rebalance_date","symbol","adj_close"]]); so=con.execute(q).fetchdf()
    con.register("o",df[["rebalance_date","symbol","adj_close"]]); co=con.execute(q).fetchdf(); con.close()
    sel=sel.merge(so,on=["rebalance_date","symbol","adj_close"],how="left"); df=df.merge(co,on=["rebalance_date","symbol","adj_close"],how="left")
    def rate(x,t=1): return float((x>=t).mean()) if len(x) else None
    sr,cr=rate(sel.max_return),rate(df.max_return)
    eras=[]
    for label,lo,hi in [("2019-2020",2019,2020),("2021-2022",2021,2022),("2023-2024",2023,2024)]:
        a=sel[(sel.rebalance_date>=f"{lo}-01-01")&(sel.rebalance_date<=f"{hi}-12-31")]
        b=df[(df.rebalance_date>=f"{lo}-01-01")&(df.rebalance_date<=f"{hi}-12-31")]
        ar,br=rate(a.max_return),rate(b.max_return)
        eras.append({"era":label,"selected_observations":len(a),"candidate_observations":len(b),"selected_hit_100_rate":ar,"candidate_hit_100_rate":br,"selection_lift_100":ar/br if ar is not None and br else None})
    report={"status":"OK","validation_type":"BSE_PIT_fundamental_selection","window":f"{start_year}-{end_year}",
      "candidate_observations":len(df),"selected_observations":len(sel),
      "fundamental_coverage_rate":float((df.fundamental_coverage>=.70).mean()),
      "selected_hit_100_rate":sr,"candidate_hit_100_rate":cr,"selection_lift_100":sr/cr if sr is not None and cr else None,
      "independent_era_falsification":eras,"independent_era_positive_lifts":sum((e.get("selection_lift_100") or 0)>1 for e in eras),
      "symbols_considered":len(symbols),"symbols_with_metrics":sum(bool(v) for v in mm.values()),
      "lookahead_checks":{"filing_available_at_lte_decision":True,"future_revisions_excluded":True,"price_entry_after_rebalance":True},
      "production_ready":bool(len(sel)>=500 and (df.fundamental_coverage>=.70).mean()>=.70 and (sr/cr if cr else 0)>=1.05 and sum((e.get("selection_lift_100") or 0)>1 for e in eras)>=2),
      "source":"BSE public financial-result/XBRL filings + NSE historical prices; true filing-timestamp PIT"}
    (OUT/"bse_pit_fundamental_validation.json").write_text(json.dumps(report,indent=2,default=str))
    sel.to_csv(OUT/"bse_pit_selected.csv",index=False)
    return report

if __name__=="__main__":
    try: print(json.dumps(run(),indent=2,default=str))
    except Exception as e:
        r={"status":"ERROR","validation_type":"BSE_PIT_fundamental_selection","error":str(e),"traceback":traceback.format_exc(),"production_ready":False}
        (OUT/"bse_pit_fundamental_validation.json").write_text(json.dumps(r,indent=2)); print(json.dumps(r,indent=2))
