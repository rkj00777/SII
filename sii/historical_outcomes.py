"""Outcome-only historical falsification over the free TejHQ PIT liquidity universe.
This is deliberately separate from fundamental scoring: it measures whether the data
layer can reproduce +100/+200/+300 outcomes without survivorship leakage.
"""
from datetime import date
from .free_market import _duckdb
from .falsifier import Outcome

HF='https://huggingface.co/datasets/tejhq/indian-markets/resolve/main'
def _p(ex,kind,y):
    if kind=='raw': return f"{HF}/{ex}/year={y}/{ex}_{y}.parquet"
    return f"{HF}/prices_adjusted/{ex}_{y}.parquet"

def run(start_year=2019,end_year=2024,rank_max=500,horizon_days=756):
    con=_duckdb()
    years=list(range(start_year,end_year+1))
    price_years=list(range(start_year,end_year+min(6,2026-start_year)+1))
    up=f"{HF}/universe/nse_liquid.parquet"
    prices="["+",".join(repr(_p('nse','adj',y)) for y in price_years)+"]"
    q=f"""
    WITH u AS (
      SELECT rebalance_date, symbol, isin, rank
      FROM read_parquet('{up}')
      WHERE rank <= {rank_max}
        AND rebalance_date BETWEEN DATE '{start_year}-01-01' AND DATE '{end_year}-12-31'
    ),
    p AS (
      SELECT date, symbol, isin, adj_close
      FROM read_parquet({prices}, union_by_name=true)
      WHERE adj_close IS NOT NULL
    ),
    b AS (
      SELECT u.rebalance_date,u.symbol,u.isin,u.rank,
             arg_min(p.adj_close,p.date) AS entry_price,
             min(p.date) AS entry_date
      FROM u JOIN p ON p.symbol=u.symbol AND p.date>=u.rebalance_date
      GROUP BY ALL
    ),
    o AS (
      SELECT b.*, max(CASE WHEN p.date<=b.entry_date + INTERVAL '{horizon_days} days' THEN p.adj_close/b.entry_price-1 END) AS max_return
      FROM b JOIN p ON p.symbol=b.symbol AND p.date>=b.entry_date
      GROUP BY ALL
    )
    SELECT * FROM o
    """
    df=con.execute(q).fetchdf(); con.close()
    if df.empty:
        return {'status':'DATA_UNAVAILABLE','observations':0,'reason':'No TejHQ adjusted-price/universe rows returned'}
    import numpy as np
    ret=df['max_return'].astype(float)
    summary={
      'status':'OK','observations':int(len(df)),'decision_months':int(df['rebalance_date'].nunique()),
      'universe_rank_max':rank_max,'horizon_days':horizon_days,
      'hit_100':int((ret>=1).sum()),'hit_200':int((ret>=2).sum()),'hit_300':int((ret>=3).sum()),
      'hit_100_rate':float((ret>=1).mean()),'hit_200_rate':float((ret>=2).mean()),'hit_300_rate':float((ret>=3).mean()),
      'median_max_return':float(ret.median()),'p90_max_return':float(ret.quantile(.9)),
      'production_ready':False,
      'validation_type':'outcome_only',
      'limitation':'This validates forward price outcomes only. It does not validate SII fundamental/PIT selection because the public TejHQ dataset does not contain fundamentals.'
    }
    return summary
