from datetime import date,datetime
from sqlalchemy import select
from .db import session
from .models import Security
from .market_ingest import history_for_symbol
from .falsifier import forward_outcome,aggregate_outcomes
def decision_dates(start_year=2019,end_year=None,month_step=3):
 end_year=end_year or date.today().year;out=[];y=start_year;m=3
 while (y,m)<=(end_year,12):
  out.append(date(y,m,1));m+=month_step
  while m>12:m-=12;y+=1
 return out
def run_historical_falsification(start_year=2019,end_year=None,max_names_per_date=None):
 s=session();out=[];dates=decision_dates(start_year,end_year);checked=0
 secs=s.execute(select(Security).where(Security.eligible==True)).scalars().all()
 for d in dates:
  for sec in (secs[:max_names_per_date] if max_names_per_date else secs):
   try:
    df=history_for_symbol(sec.nse_symbol or '',d.isoformat(),str(date(end_year or date.today().year,12,31)))
    if df.empty:continue
    checked+=1;o=forward_outcome(df.to_dict('records'),d);out.append(o)
   except Exception:continue
 s.close();summary=aggregate_outcomes(out);summary.update({'decision_dates':len(dates),'symbols_checked':checked,'validation_mode':'outcome_only_if_PIT_fundamentals_are_unavailable','production_ready':False,'reason':'Historical price outcomes can be measured, but production readiness requires PIT fundamental coverage.'});return summary
