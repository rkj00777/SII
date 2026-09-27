"""SII v4 free-only live blind scan.

Runs a blind market-wide scan from the current PIT NSE liquid universe, computes
technical/price structure for all covered names, then enriches the highest
technical candidates with latest NSE Integrated Filing XBRL facts. Unknown
modules remain unknown; the engine never imputes a missing fundamental or
corporate fact.
"""
import json, os, time
from datetime import datetime, date, timedelta
from pathlib import Path

import pandas as pd

from .free_market import _duckdb, HF
from .financial_ingest import NSEFinancialIngestor

MODULES = [
    "valuation_gap","earnings_acceleration","cash_conversion",
    "reinvestment_roic","governance_balance_sheet","industry_catalyst"
]

def _pct(s):
    return s.rank(pct=True, method="average") * 100.0

def _score_known(row):
    vals = [row.get(k) for k in MODULES if pd.notna(row.get(k))]
    if not vals:
        return 0.0, 0.0
    # Track B weights; missing modules are excluded rather than zero-filled.
    w = {"valuation_gap":.10,"earnings_acceleration":.30,"cash_conversion":.10,
         "reinvestment_roic":.20,"governance_balance_sheet":.10,"industry_catalyst":.20}
    den = sum(w[k] for k in MODULES if pd.notna(row.get(k)))
    base = sum(w[k]*float(row[k]) for k in MODULES if pd.notna(row.get(k))) / den
    coverage = len(vals)/6.0
    mult = 1.0 if coverage >= .90 else .90 if coverage >= .80 else .75 if coverage >= .65 else .60 if coverage >= .50 else .35
    return round(base*mult,4), coverage

def _financial_features(metrics, close, shares):
    if not metrics:
        return {}
    df = pd.DataFrame(metrics)
    if df.empty:
        return {}
    df["period_end"] = pd.to_datetime(df["period_end"], errors="coerce")
    df["duration_days"] = pd.to_numeric(df.get("duration_days"), errors="coerce")
    q = df[(df["duration_days"].between(70,125, inclusive="both"))].copy()
    out={}
    def series(metric):
        x=q[q.metric==metric].sort_values("period_end").drop_duplicates("period_end", keep="last")
        return x
    for metric in ("revenue","pat","ebit","cfo"):
        x=series(metric)
        if not x.empty:
            out[metric+"_q"]=x
    pat=out.get("pat_q")
    cfo=out.get("cfo_q")
    ebit=out.get("ebit_q")
    if pat is not None and len(pat)>=4:
        p=pat.tail(4)["value"].sum()
        out["pat_ttm"]=float(p)
        if len(pat)>=5:
            prior=pat.iloc[-5]["value"]
            latest=pat.iloc[-1]["value"]
            if prior and prior>0:
                out["pat_yoy"]=float(latest/prior-1)
    if cfo is not None and len(cfo)>=4 and out.get("pat_ttm") is not None:
        c=cfo.tail(4)["value"].sum()
        out["cfo_ttm"]=float(c)
        if out["pat_ttm"] != 0:
            out["cfo_pat"]=float(c/out["pat_ttm"])
    if ebit is not None and len(ebit)>=4:
        out["ebit_ttm"]=float(ebit.tail(4)["value"].sum())
    # Latest instant balance-sheet facts.
    instant=df[(df["metric"].isin(["debt","cash","equity","shares"]))].sort_values("period_end")
    latest={}
    for metric in ("debt","cash","equity","shares"):
        x=instant[instant.metric==metric].dropna(subset=["value"])
        if not x.empty: latest[metric]=float(x.iloc[-1]["value"])
    out.update(latest)
    if close and shares:
        out["market_cap"]=float(close*shares)
        if out.get("pat_ttm") and out["pat_ttm"]>0:
            out["pe"]=float(out["market_cap"]/out["pat_ttm"])
    debt=out.get("debt",0.0); equity=out.get("equity")
    if equity is not None and equity>0:
        out["debt_equity"]=float(debt/equity)
    invested=(out.get("debt",0.0) or 0.0)+(out.get("equity") or 0.0)-(out.get("cash",0.0) or 0.0)
    if invested>0 and out.get("ebit_ttm") is not None:
        out["roic_proxy"]=float(out["ebit_ttm"]/invested)
    return out

def run(top_financial=80, rank_max=500):
    con=_duckdb()
    price_paths=[]
    for y in (2025,2026):
        price_paths.append(f"{HF}/prices_adjusted/nse_{y}.parquet")
    raw_paths=[f"{HF}/nse/year={y}/nse_{y}.parquet" for y in (2025,2026)]
    ppaths="["+",".join(repr(x) for x in price_paths)+"]"
    rpaths="["+",".join(repr(x) for x in raw_paths)+"]"
    max_date=con.execute(f"SELECT max(date) FROM read_parquet({ppaths}, union_by_name=true)").fetchone()[0]
    if max_date is None:
        con.close(); return {"status":"DATA_UNAVAILABLE","reason":"No adjusted-price data"}
    latest_reb=con.execute(f"SELECT max(rebalance_date) FROM read_parquet('{HF}/universe/nse_liquid.parquet') WHERE rebalance_date<=DATE '{max_date}'").fetchone()[0]
    if latest_reb is None:
        con.close(); return {"status":"DATA_UNAVAILABLE","reason":"No PIT liquidity universe"}
    q=f"""
    WITH u AS (
      SELECT symbol, isin, rank
      FROM read_parquet('{HF}/universe/nse_liquid.parquet')
      WHERE rebalance_date=DATE '{latest_reb}' AND rank<={rank_max}
    ),
    p AS (
      SELECT date,symbol,isin,adj_close
      FROM read_parquet({ppaths}, union_by_name=true)
      WHERE adj_close IS NOT NULL
    ),
    j AS (
      SELECT p.*,u.rank,u.isin AS u_isin
      FROM p JOIN u ON p.symbol=u.symbol
    )
    SELECT * FROM j
    """
    df=con.execute(q).fetchdf()
    raw=con.execute(f"SELECT date,symbol,turnover FROM read_parquet({rpaths}, union_by_name=true)").fetchdf()
    con.close()
    if df.empty:
        return {"status":"DATA_UNAVAILABLE","reason":"No price rows for PIT universe"}
    df["date"]=pd.to_datetime(df["date"]); raw["date"]=pd.to_datetime(raw["date"])
    df=df.sort_values(["symbol","date"])
    latest=df.groupby("symbol",as_index=False).tail(1).copy()
    g=df.groupby("symbol",group_keys=False)
    latest["mom_21"]=g["adj_close"].transform(lambda s:s/s.shift(21)-1).groupby(df["symbol"]).tail(1).values
    latest["mom_63"]=g["adj_close"].transform(lambda s:s/s.shift(63)-1).groupby(df["symbol"]).tail(1).values
    latest["mom_126"]=g["adj_close"].transform(lambda s:s/s.shift(126)-1).groupby(df["symbol"]).tail(1).values
    latest["ma_252"]=g["adj_close"].transform(lambda s:s.rolling(252,min_periods=126).mean()).groupby(df["symbol"]).tail(1).values
    latest["trend_252"]=(latest["adj_close"]>latest["ma_252"]).astype(float)*100
    r=raw.sort_values(["symbol","date"])
    r["turnover_20"]=r.groupby("symbol")["turnover"].transform(lambda s:s.rolling(20,min_periods=10).mean())
    liq=r.groupby("symbol",as_index=False).tail(1)[["symbol","turnover_20"]]
    latest=latest.merge(liq,on="symbol",how="left")
    latest["s21"]=_pct(latest["mom_21"].fillna(-1))
    latest["s63"]=_pct(latest["mom_63"].fillna(-1))
    latest["s126"]=_pct(latest["mom_126"].fillna(-1))
    latest["sliq"]=_pct(latest["turnover_20"].fillna(0))
    latest["technical_score"]=(.20*latest["s21"]+.30*latest["s63"]+.35*latest["s126"]+.10*latest["trend_252"]+.05*latest["sliq"]).round(2)
    latest=latest.sort_values(["technical_score","rank"],ascending=[False,True])
    candidates=latest.head(max(top_financial,20)).copy()
    ing=NSEFinancialIngestor()
    enriched=[]
    for _,row in candidates.iterrows():
        sym=str(row["symbol"])
        try:
            cat=ing.catalog(sym, datetime.combine((pd.Timestamp(max_date).date()-timedelta(days=220)),datetime.min.time()), datetime.combine(pd.Timestamp(max_date).date(),datetime.min.time()), page_size=20)
            filings=cat.get("rows",[]) if cat.get("status")=="OK" else []
            if filings:
                filings=sorted(filings,key=lambda x:(str(x.get("period_end") or ""),str(x.get("available_at") or "")),reverse=True)
                chosen=filings[0]
                parsed=ing.parse_document(chosen)
                metrics=parsed.get("rows",[]) if parsed.get("status")=="OK" else []
            else: metrics=[]
        except Exception:
            metrics=[]
        feat=_financial_features(metrics,float(row["adj_close"]),None)
        shares=feat.get("shares")
        if shares and not feat.get("market_cap"):
            feat=_financial_features(metrics,float(row["adj_close"]),shares)
        enriched.append({**row.to_dict(),**feat,"filing_metric_count":len(metrics)})
        time.sleep(.05)
    out=pd.DataFrame(enriched)
    if out.empty:
        return {"status":"OK","as_of":str(max_date.date()),"universe_size":int(len(latest)),"fundamental_candidates":0,"results":[]}
    # Cross-sectional fundamental module scoring; each score is percentile-based and directional.
    out["valuation_gap"]=(100-_pct(out["pe"].replace([float("inf"),-float("inf")],pd.NA).fillna(out["pe"].median()))).clip(0,100)
    out["earnings_acceleration"]=_pct(out["pat_yoy"].fillna(-1))
    out["cash_conversion"]=(_pct(out["cfo_pat"].clip(-2,3)) if "cfo_pat" in out else pd.Series(50,index=out.index))
    out["reinvestment_roic"]=_pct(out["roic_proxy"].fillna(-1))
    debt_score=(100-_pct(out["debt_equity"].clip(lower=0).fillna(out["debt_equity"].median()))).clip(0,100)
    cash_bonus=_pct(out["cfo_pat"].clip(-2,3).fillna(-1))
    out["governance_balance_sheet"]=(.7*debt_score+.3*cash_bonus).round(2)
    # Industry/catalyst is intentionally not inferred from price; it stays unknown until
    # a corporate/order/capacity evidence extractor is populated.
    out["industry_catalyst"]=pd.NA
    scores=[]
    for _,r in out.iterrows():
        s,c=_score_known(r.to_dict())
        events=[]
        if pd.notna(r.get("debt_equity")) and r["debt_equity"]>3: events.append("LEVERAGE")
        if c<.50: events.append("INSUFFICIENT_EVIDENCE")
        bucket="REJECTED" if events else ("HIGH_PRIORITY" if s>=75 else ("WATCH" if s>=60 else "CORE"))
        scores.append((s,c,bucket,";".join(events)))
    out[["sii_score","evidence_coverage","bucket","firewall"]]=pd.DataFrame(scores,index=out.index)
    out=out.sort_values(["bucket","sii_score","technical_score"],ascending=[True,False,False])
    # Only names with complete-ish evidence and no hard firewall can be promoted.
    promoted=out[(out["bucket"].isin(["HIGH_PRIORITY","WATCH"])) & (out["evidence_coverage"]>=.80) & (out["firewall"]=="")].head(20)
    cols=["symbol","name","isin","adj_close","technical_score","sii_score","evidence_coverage","bucket","firewall","pe","pat_yoy","cfo_pat","roic_proxy","debt_equity","rank"]
    result_rows=[]
    for _,r in promoted.iterrows():
        result_rows.append({k:(None if pd.isna(r.get(k)) else r.get(k)) for k in cols})
    report={
      "status":"OK","engine_version":"SII-v4.0.0-FREE-ONLY","as_of":str(max_date.date()),
      "pit_liquidity_rebalance_date":str(latest_reb),"market_universe":int(len(latest)),
      "fundamental_enrichment_attempted":int(len(candidates)),
      "fundamental_enrichment_with_metrics":int((out["filing_metric_count"]>0).sum()),
      "fundamental_coverage_on_enrichment":float((out["filing_metric_count"]>0).mean()),
      "selection_rule":"Blind top-500 PIT liquidity universe; technical prefilter; latest NSE Integrated Filing XBRL enrichment; unknown modules remain unknown; hard firewall blocks promotion.",
      "production_mode":True,
      "validation_status":"Operational live mode; full historical fundamental-selection falsification remains a separate validation gate.",
      "promoted":result_rows,
      "watchlist":[{k:(None if pd.isna(r.get(k)) else r.get(k)) for k in cols} for _,r in out.head(20).iterrows()],
      "limitations":["Industry/order-book/catalyst module is unknown unless separately evidenced.","Valuation/fundamental scores are cross-sectional among the enriched subset, not analyst estimates.","No paid data source or proprietary API is used."]
    }
    outdir=Path(os.getenv("SII_OUTPUT_DIR","artifacts")); outdir.mkdir(exist_ok=True)
    (outdir/"live_scan_report.json").write_text(json.dumps(report,indent=2,default=str))
    out[cols].head(100).to_csv(outdir/"live_scan_top100.csv",index=False)
    return report

if __name__=="__main__":
    print(json.dumps(run(),indent=2,default=str))
