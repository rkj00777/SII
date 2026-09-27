from datetime import datetime
from sqlalchemy import select
from .db import session
from .models import Security
from .pipeline import score_candidate
def run_blind_scan(as_of=None,limit=None):
 s=session();secs=s.execute(select(Security).where(Security.eligible==True)).scalars().all();s.close()
 if limit:secs=secs[:limit]
 results=[]
 for sec in secs:
  modules={'valuation_gap':None,'earnings_acceleration':None,'cash_conversion':None,'reinvestment_roic':None,'governance_balance_sheet':None,'industry_catalyst':None}
  for track in ('A','B'):results.append((sec.isin,track,score_candidate(sec.isin,modules,0,track=track,as_of=as_of or datetime.utcnow())))
 return results
