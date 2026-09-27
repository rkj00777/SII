# SII historical falsification v4\nimport json,os
from pathlib import Path
from .historical_outcomes import run
def run_historical_falsification(start_year=2019,end_year=2024):
 r=run(start_year,end_year,rank_max=500,horizon_days=756)
 out=Path(os.getenv('SII_OUTPUT_DIR','artifacts'));out.mkdir(exist_ok=True)
 (out/'historical_outcome_report.json').write_text(json.dumps(r,indent=2,default=str))
 return r
