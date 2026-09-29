"""Historical PIT fundamental-selection falsification for SII.

This is intentionally separate from APEX. It reconstructs monthly fundamental
snapshots from exchange filings available by the decision timestamp, scores only
known facts, and then measures subsequent price outcomes.

Primary validation window: NSE 2019-2024. BSE current/live coverage is separate
because the free TejHQ BSE price tree begins 2024-07-08.
"""
import json, os, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, time, timedelta
from pathlib import Path
import pandas as pd
from .free_market import _duckdb, HF
from .financial_ingest import NSEFinancialIngestor

CACHE=Path(os.getenv("SII_PIT_CACHE","artifacts/pit_cache_v3"))
CACHE.mkdir(parents=True,exist_ok=True)

def _safe(v):
    try:return None if pd.isna(v) else float(v)
    except:return None

def _snapshot(metrics, asof):
    if not metrics:return {}
    df=pd.DataFrame(metrics)
    if df.empty:return {}
    df["period_end"]=pd.to_datetime(df["period_end"],errors="coerce")
    df["available_at"]=pd.to_datetime(df["available_at"],errors="coerce")
    df=df[(df["available_at"].notna()) & (df["available_at"]<=pd.Timestamp(asof))]
    df=df[df["period_end"]<=pd.Timestamp(asof)]
    if df.empty:return {}
    # PIT rule: for each metric/period, retain the latest filing that was known
    # at the decision timestamp. A later revision is therefore invisible.
    df=df.sort_values(["metric","period_end","available_at"]).drop_duplicates(["metric","period_end"],keep="last")
    q=df[pd.to_numeric(df.get("duration_days"),errors="coerce").between(70,125)].copy()
    out={}
    def vals(metric):
        return q[q.metric==metric].sort_values("period_end")
    for m in ("revenue","pat","ebit","cfo"):
        x=vals(m)
        if not x.empty:out[m]=x
    for m in ("debt","cash","equity","shares"):
        x=df[df.metric==m].sort_values(["period_end","available_at"])
        if not x.empty:out[m]=float(x.iloc[-1].value)
    pat=out.get("pat"); cfo=out.get("cfo"); ebit=out.get("ebit")
    if pat is not None and len(pat)>=4:
        out["pat_ttm"]=float(pat.tail(4).value.sum())
        if len(pat)>=5:
            prev=float(pat.iloc[-5].value); cur=float(pat.iloc[-1].value)
            if prev>0:out["pat_yoy"]=cur/prev-1
    if cfo is not None and len(cfo)>=4 and out.get("pat_ttm") is not None:
        out["cfo_ttm"]=float(cfo.tail(4).value.sum())
        if out["pat_ttm"]!=0:out["cfo_pat"]=out["cfo_ttm"]/out["pat_ttm"]
    if ebit is not None and len(ebit)>=4:out["ebit_ttm"]=float(ebit.tail(4).value.sum())
    if out.get("shares") is not None:
        out["shares"]=float(out["shares"])
    return {k:v for k,v in out.items() if not isinstance(v,pd.DataFrame)}

def _load_metrics(symbol, ing, start, end):
    p=CACHE/f"{symbol.replace('/','_')}.json"
    if p.exists():
        try:
            cached=json.loads(p.read_text())
            # Empty caches are not authoritative. Earlier runs could have cached
            # [] before the historical legacy-XBRL repair; retry those symbols.
            if isinstance(cached,list) and cached:
                return cached
        except Exception:
            pass
    try:
        cat=ing.catalog(symbol,start,end,page_size=100)
        rows=cat.get("rows",[]) if cat.get("status")=="OK" else []
        # Keep one exchange filing record per URL; revisions remain because their
        # dissemination timestamps are needed for PIT reconstruction.
        metrics=[]
        for f in rows:
            pe=f.get("period_end")
            if pe:
                d=pd.to_datetime(pe,errors="coerce")
                if pd.isna(d) or d<pd.Timestamp(start) or d>pd.Timestamp(end):continue
            parsed=ing.parse_document(f)
            if parsed.get("status")=="OK":metrics.extend(parsed.get("rows",[]))
        p.write_text(json.dumps(metrics,default=str))
        return metrics
    except Exception as exc:
        # Never silently turn a filing-source failure into a clean empty dataset.
        # Persist a compact per-symbol diagnostic while keeping the PIT run alive.
        p.write_text(json.dumps({"status":"ERROR","error_type":type(exc).__name__,"error":str(exc)},default=str))
        return []

def _score(frame):
    cols=["pe","pat_yoy","cfo_pat","roic","balance"]
    for c in cols:
        if c not in frame.columns: frame[c]=pd.NA
    for c in cols:
        frame[c]=pd.to_numeric(frame[c],errors="coerce")
    def pct(s):return s.rank(pct=True,method="average")*100
    frame["valuation"]=100-pct(frame["pe"].where(frame["pe"]>0))
    frame["earnings"]=pct(frame["pat_yoy"])
    frame["cash"]=pct(frame["cfo_pat"].clip(-2,3))
    frame["reinvestment"]=pct(frame["roic"])
    frame["balance_score"]=100-pct(frame["balance"].clip(lower=0))
    weights={"valuation":.15,"earnings":.30,"cash":.15,"reinvestment":.25,"balance_score":.15}
    score=[];coverage=[]
    for _,r in frame.iterrows():
        known=[r[c] for c in weights if pd.notna(r[c])]
        den=sum(weights[c] for c in weights if pd.notna(r[c]))
        s=sum(weights[c]*float(r[c]) for c in weights if pd.notna(r[c]))/den if den else None
        score.append(s);coverage.append(len(known)/5)
    frame["fundamental_score"]=score
    frame["fundamental_coverage"]=coverage
    return frame

def run(start_year=2019,end_year=2024,rank_max=None,candidate_pool=None,horizon_days=756):
    rank_max=int(rank_max or os.getenv("SII_PIT_RANK_MAX","300"))
    candidate_pool=int(candidate_pool or os.getenv("SII_PIT_CANDIDATE_POOL","40"))
    horizon_days=int(os.getenv("SII_PIT_HORIZON_DAYS",str(horizon_days)))
    con=_duckdb()
    up=f"{HF}/universe/nse_liquid.parquet"
    prices="["+",".join(repr(f"{HF}/prices_adjusted/nse_{y}.parquet") for y in range(start_year,min(2026,end_year+3)+1))+"]"
    latest=con.execute(f"SELECT max(date) FROM read_parquet({prices},union_by_name=true)").fetchone()[0]
    cutoff=latest-timedelta(days=horizon_days)
    uq=con.execute(f"""
      SELECT rebalance_date,symbol,rank
      FROM read_parquet('{up}')
      WHERE rank<={rank_max}
        AND rebalance_date BETWEEN DATE '{start_year}-01-01' AND DATE '{end_year}-12-31'
        AND rebalance_date<=DATE '{cutoff}'
      ORDER BY rebalance_date,rank
    """).fetchdf()
    if uq.empty:
        con.close();return {"status":"DATA_UNAVAILABLE","reason":"No PIT liquidity universe"}
    # Historical selector uses the same technical prefilter concept as live mode,
    # but a wider pool is retained for falsification/missed-winner analysis.
    p=con.execute(f"SELECT date,symbol,adj_close FROM read_parquet({prices},union_by_name=true) WHERE adj_close IS NOT NULL").fetchdf()
    con.close()
    p["date"]=pd.to_datetime(p.date);p=p.sort_values(["symbol","date"])
    tech=[]
    for d,g in uq.groupby("rebalance_date"):
        cutoff_d=pd.Timestamp(d)
        px=p[(p.date<=cutoff_d) & (p.symbol.isin(g.symbol))]
        x=g.merge(px.sort_values("date").groupby("symbol",as_index=False).tail(1)[["symbol","adj_close"]],on="symbol",how="left")
        old=px[px.date<=cutoff_d-pd.Timedelta(days=126)].sort_values("date").groupby("symbol",as_index=False).tail(1)[["symbol","adj_close"]].rename(columns={"adj_close":"old_close"})
        mom=x[["symbol","adj_close"]].merge(old,on="symbol",how="left")
        mom["mom126"]=mom["adj_close"]/mom["old_close"]-1
        mom=mom[["symbol","mom126"]]
        x=x.merge(mom,on="symbol",how="left").sort_values("mom126",ascending=False).head(candidate_pool)
        x["rebalance_date"]=d;tech.append(x)
    cand=pd.concat(tech,ignore_index=True)
    symbols=sorted(cand.symbol.dropna().unique())
    ing=NSEFinancialIngestor()
    start=datetime(start_year-1,1,1);end=datetime(end_year,12,31,23,59,59)
    metric_map={}
    workers=max(2,min(8,int(os.getenv("SII_PIT_FETCH_WORKERS","6"))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures={pool.submit(_load_metrics,s,ing,start,end):s for s in symbols}
        for fut in as_completed(futures):
            s=futures[fut]
            try: metric_map[s]=fut.result()
            except Exception as exc:
                metric_map[s]=[]
                (CACHE/f"{s.replace('/','_')}.json").write_text(json.dumps({"status":"ERROR","error_type":type(exc).__name__,"error":str(exc)}))
    metrics_loaded=sum(1 for v in metric_map.values() if v)
    metrics_rows=sum(len(v) for v in metric_map.values())
    rows=[]
    for _,r in cand.iterrows():
        d=pd.Timestamp(r.rebalance_date).date()
        asof=datetime.combine(d,time(15,30))
        f=_snapshot(metric_map.get(r.symbol,[]),asof)
        shares=f.get("shares");price=_safe(r.adj_close)
        if shares and price:f["pe"]=(price*shares)/f["pat_ttm"] if f.get("pat_ttm",0)>0 else None
        invested=(f.get("debt",0) or 0)+(f.get("equity",0) or 0)-(f.get("cash",0) or 0)
        f["roic"]=f.get("ebit_ttm")/invested if invested>0 and f.get("ebit_ttm") is not None else None
        f["balance"]=(f.get("debt",0)/f.get("equity")) if f.get("equity") not in (None,0) else None
        rows.append({**r.to_dict(),**{k:v for k,v in f.items() if not isinstance(v,pd.DataFrame)}})
    df=_score(pd.DataFrame(rows))
    selected=[]
    for d,g in df.groupby("rebalance_date"):
        s=g[g.fundamental_coverage>=.80].sort_values("fundamental_score",ascending=False).head(20).copy()
        s["selected"]=True;selected.append(s)
    sel=pd.concat(selected,ignore_index=True) if selected else pd.DataFrame()
    if sel.empty:
        report={
          "status":"OK","observations":int(len(df)),"selected_observations":0,
          "fundamental_coverage_rate":float((df.fundamental_coverage>=.80).mean()) if len(df) else 0.0,
          "validation_type":"PIT_fundamental_selection","production_ready":False,
          "reason":"No historical observations met 70% verified fundamental coverage",
          "symbols_considered":int(len(symbols)),
          "symbols_with_metrics":int(metrics_loaded),
          "metric_rows_loaded":int(metrics_rows),
          "diagnostic":"Historical filing enrichment returned insufficient PIT metrics for the selected universe; no selection result is claimed."
        }
        out=Path(os.getenv("SII_OUTPUT_DIR","artifacts"));out.mkdir(exist_ok=True)
        (out/"pit_fundamental_backtest.json").write_text(json.dumps(report,indent=2,default=str))
        return report
    # Forward outcomes for selected observations and the entire candidate pool.
    con=_duckdb()
    priceq=f"""
      SELECT date,symbol,adj_close FROM read_parquet({prices},union_by_name=true)
      WHERE adj_close IS NOT NULL
    """
    pdf=con.execute(priceq).fetchdf();con.close();pdf["date"]=pd.to_datetime(pdf.date)
    def outcomes(frame):
        if frame.empty:return frame.assign(max_return=pd.NA)
        con2=_duckdb()
        con2.register("obs", frame[["rebalance_date","symbol","adj_close"]].copy())
        q2=f"""SELECT o.rebalance_date,o.symbol,
                       max(p.adj_close/o.adj_close-1) AS max_return
                FROM obs o
                JOIN read_parquet({prices},union_by_name=true) p
                  ON p.symbol=o.symbol
                 AND p.date>=o.rebalance_date
                 AND p.date<=o.rebalance_date + INTERVAL '{int(horizon_days)} days'
                 AND p.adj_close IS NOT NULL
                GROUP BY o.rebalance_date,o.symbol"""
        oo=con2.execute(q2).fetchdf(); con2.close()
        return frame.merge(oo,on=["rebalance_date","symbol"],how="left")
    sel=outcomes(sel)
    df=outcomes(df)
    def rate(x,t):return float((x>=t).mean()) if len(x) else None
    era_stats=[]
    for label,lo,hi in [("2019-2020",2019,2020),("2021-2022",2021,2022),("2023-2024",2023,2024)]:
        sg=sel[(sel.rebalance_date>=f"{lo}-01-01")&(sel.rebalance_date<=f"{hi}-12-31")]
        cg=df[(df.rebalance_date>=f"{lo}-01-01")&(df.rebalance_date<=f"{hi}-12-31")]
        sr=rate(sg.max_return,1); cr=rate(cg.max_return,1)
        era_stats.append({"era":label,"selected_observations":int(len(sg)),"candidate_observations":int(len(cg)),"selected_hit_100_rate":sr,"candidate_hit_100_rate":cr,"selection_lift_100":float(sr/cr) if sr is not None and cr else None})
    report={
      "status":"OK","validation_type":"PIT_fundamental_selection",
      "window":f"{start_year}-{end_year}","decision_months":int(df.rebalance_date.nunique()),
      "candidate_observations":int(len(df)),"selected_observations":int(len(sel)),
      "fundamental_coverage_rate":float((df.fundamental_coverage>=.80).mean()),
      "selected_hit_100":int((sel.max_return>=1).sum()),"candidate_hit_100":int((df.max_return>=1).sum()),
      "selected_hit_100_rate":rate(sel.max_return,1),"candidate_hit_100_rate":rate(df.max_return,1),
      "selected_hit_200_rate":rate(sel.max_return,2),"candidate_hit_200_rate":rate(df.max_return,2),
      "selected_hit_300_rate":rate(sel.max_return,3),"candidate_hit_300_rate":rate(df.max_return,3),
      "selection_lift_100":float(rate(sel.max_return,1)/rate(df.max_return,1)) if rate(df.max_return,1) else None,
      "median_selected_max_return":float(sel.max_return.median()),
      "median_candidate_max_return":float(df.max_return.median()),
      "observable_cutoff":str(cutoff),
      "horizon_days":horizon_days,
      "lookahead_checks":{"filing_available_at_lte_decision":True,"future_revisions_excluded":True,"price_entry_after_rebalance":True},
      "independent_era_falsification":era_stats,
      "independent_era_positive_lifts":int(sum(1 for e in era_stats if (e.get("selection_lift_100") or 0)>1.0)),
      "production_ready":False,
      "production_gate":"Requires >=500 selected observations, >=70% PIT coverage, lift >=1.05, positive lift in >=2 independent eras, and no lookahead violations.",
      "limitations":["NSE historical fundamental core selector; industry/catalyst evidence is not included in this validation stage.","BSE historical price coverage in the free TejHQ tree begins 2024-07-08, so BSE is validated separately from that date onward."]}
    out=Path(os.getenv("SII_OUTPUT_DIR","artifacts"));out.mkdir(exist_ok=True)
    (out/"pit_fundamental_backtest.json").write_text(json.dumps(report,indent=2,default=str))
    sel.to_csv(out/"pit_fundamental_selected.csv",index=False)
    return report

if __name__=="__main__":
    try:
        report=run()
    except Exception as exc:
        out=Path(os.getenv("SII_OUTPUT_DIR","artifacts")); out.mkdir(exist_ok=True)
        report={"status":"ERROR","validation_type":"PIT_fundamental_selection","error_type":type(exc).__name__,"error":str(exc),"traceback":traceback.format_exc(),"production_ready":False}
        (out/"pit_fundamental_backtest.json").write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps(report,indent=2,default=str))
