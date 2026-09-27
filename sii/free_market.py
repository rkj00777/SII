"""Free TejHQ/Hugging Face market-data bridge."""
from dataclasses import dataclass
from datetime import date
HF='https://huggingface.co/datasets/tejhq/indian-markets/resolve/main'
@dataclass
class RemoteQuery:
    sql:str
    rows:list
def _duckdb():
    import duckdb
    con=duckdb.connect(); con.execute("INSTALL httpfs; LOAD httpfs;"); return con
def nse_year(year:int): return f"{HF}/nse/year={year}/nse_{year}.parquet"
def bse_year(year:int): return f"{HF}/bse/year={year}/bse_{year}.parquet"
def actions_year(exchange:str,year:int): return f"{HF}/actions/{exchange.lower()}_{year}.parquet"
def scan_nse(start_year=2010,end_year=None):
    end_year=end_year or date.today().year; con=_duckdb(); paths=','.join("'"+nse_year(y)+"'" for y in range(start_year,end_year+1)); return con.execute(f"SELECT * FROM read_parquet([{paths}], union_by_name=true)").fetchall()
def nse_cross_section(as_of:str):
    con=_duckdb(); path=nse_year(int(as_of[:4])); q=f"SELECT symbol,series,isin,name,close,volume,turnover,date FROM read_parquet('{path}') WHERE date <= DATE '{as_of}' QUALIFY row_number() OVER(PARTITION BY coalesce(isin,symbol) ORDER BY date DESC)=1"; return con.execute(q).fetchall()
def nse_liquidity(as_of:str):
    con=_duckdb(); u=f"{HF}/universe/nse_liquid.parquet"; return con.execute(f"SELECT * FROM read_parquet('{u}') WHERE rebalance_date <= DATE '{as_of}' AND valid_to >= DATE '{as_of}' ORDER BY rank").fetchall()
