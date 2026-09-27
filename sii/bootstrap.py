import json,os
from datetime import date,datetime
from pathlib import Path
from .pipeline import run_universe,gate_snapshot
from .free_market import nse_year,_duckdb
OUT=Path(os.getenv('SII_OUTPUT_DIR','artifacts'));OUT.mkdir(parents=True,exist_ok=True)
def run_bootstrap():
 started=datetime.utcnow();universe=run_universe()
 con=_duckdb();row=con.execute(f"SELECT count(*) FROM read_parquet('{nse_year(date.today().year)}')").fetchone()[0];con.close()
 gate=gate_snapshot()
 report={'job':'bootstrap','started_at':started.isoformat(),'finished_at':datetime.utcnow().isoformat(),'universe':universe,'tejhq_current_year_rows':int(row),'gate':gate,'status':'READY_FOR_HISTORICAL_OUTCOME_VALIDATION' if row>0 and universe.get('eligible',0)>0 else 'DATA_UNAVAILABLE'}
 (OUT/'bootstrap_report.json').write_text(json.dumps(report,indent=2,default=str));print(json.dumps(report,indent=2,default=str));return report
if __name__=='__main__':run_bootstrap()
