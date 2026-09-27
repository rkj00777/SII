"""Free TejHQ parquet ingestion and PIT-safe outcome queries."""
from datetime import date
from .free_market import _duckdb,nse_year,bse_year
def latest_nse(as_of:str):
    con=_duckdb(); path=nse_year(int(as_of[:4])); q=f"SELECT symbol,series,isin,name,close,open,high,low,volume,turnover,date FROM read_parquet('{path}') WHERE date <= DATE '{as_of}' QUALIFY row_number() OVER(PARTITION BY coalesce(isin,symbol) ORDER BY date DESC)=1"; return con.execute(q).fetchdf()
def history_for_symbol(symbol,start,end,exchange='nse'):
    con=_duckdb(); paths=[nse_year(y) if exchange.lower()=='nse' else bse_year(y) for y in range(int(start[:4]),int(end[:4])+1)]; quoted=','.join(repr(p) for p in paths); q=f"SELECT * FROM read_parquet([{quoted}], union_by_name=true) WHERE symbol=? AND date BETWEEN DATE ? AND DATE ? ORDER BY date"; return con.execute(q,[symbol,start,end]).fetchdf()
def all_prices(start_year=2010,end_year=None,exchange='nse'):
    end_year=end_year or date.today().year; con=_duckdb(); paths=[nse_year(y) if exchange.lower()=='nse' else bse_year(y) for y in range(start_year,end_year+1)]; quoted=','.join(repr(p) for p in paths); return con.execute(f"SELECT * FROM read_parquet([{quoted}], union_by_name=true)").fetchdf()
def outcome_for_symbol(symbol,start,horizon_days=756):
    end=str(date.fromisoformat(start).replace(year=date.fromisoformat(start).year+4)); df=history_for_symbol(symbol,start,end)
    if df.empty:return None
    from .falsifier import forward_outcome
    return forward_outcome(df.to_dict('records'),date.fromisoformat(start),horizon_days=horizon_days)
