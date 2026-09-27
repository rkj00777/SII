from datetime import datetime
from sqlalchemy import select,func
from .db import Base,engine,session
from .models import *
from .adapters import NSEAdapter,BSEAdapter,stable_hash
from .universe import normalize_nse,merge_rows
from .scoring import weighted_score
from .firewall import firewall,firewall_state
from .drift import drift_metrics
from .config import CONFIG
Base.metadata.create_all(engine)
def _run(job):
 s=session(); r=IngestionRun(job_type=job,status='running'); s.add(r); s.commit(); return s,r
def run_universe():
 s,run=_run('universe'); stats={'nse_main':0,'nse_sme':0,'bse_status':'NOT_RUN','eligible':0,'excluded':0,'source_status':{}}
 try:
  merged={}
  for segment,result in NSEAdapter().security_master():
   if not isinstance(result,list):stats['source_status'][segment]=result.status;continue
   stats['source_status'][segment]='OK';stats['nse_main' if segment=='MAIN' else 'nse_sme']=len(result)
   merged.update(merge_rows([normalize_nse(x,segment) for x in result]))
  for x in merged.values():
   old=s.get(Security,x['isin'])
   if old:
    for k,v in x.items():setattr(old,k,v)
    old.last_seen_at=datetime.utcnow()
   else:s.add(Security(**x))
  stats['eligible']=sum(x['eligible'] for x in merged.values());stats['excluded']=len(merged)-stats['eligible']
  bse=BSEAdapter().security_master();stats['bse_status']=bse.status
  run.status='ok' if stats['eligible']>0 else 'partial';run.stats=stats;run.run_hash=stable_hash(stats);run.finished_at=datetime.utcnow();s.commit();return stats
 except Exception as e:
  run.status='failed';run.critical_errors=1;run.error_count=1;run.finished_at=datetime.utcnow();s.commit();raise
 finally:s.close()
def coverage_snapshot(s):
 total=s.scalar(select(func.count()).select_from(Security).where(Security.eligible==True)) or 0
 prices=s.scalar(select(func.count()).select_from(MarketPrice)) or 0
 financials=s.scalar(select(func.count()).select_from(FinancialMetric)) or 0
 market_symbols=s.scalar(select(func.count(func.distinct(MarketPrice.isin)))) or 0
 fund_symbols=s.scalar(select(func.count(func.distinct(FinancialMetric.isin)))) or 0
 return {'eligible_universe':total,'market_rows':prices,'financial_rows':financials,'universe_coverage':1.0 if total else 0,'market_coverage':market_symbols/total if total else 0,'fundamental_coverage':fund_symbols/total if total else 0,'evidence_coverage':0,'pit_coverage':(1.0 if financials else 0)}
def gate_snapshot():
 s=session();c=coverage_snapshot(s);critical=s.scalar(select(func.coalesce(func.sum(IngestionRun.critical_errors),0))) or 0
 passed=c['universe_coverage']>=CONFIG.universe_gate and c['market_coverage']>=CONFIG.market_gate and c['fundamental_coverage']>=CONFIG.fundamental_gate and c['evidence_coverage']>=CONFIG.evidence_gate and c['pit_coverage']>=CONFIG.pit_gate and critical==0
 c.update({'critical_errors':critical,'gate_passed':passed,'reason':'PASS' if passed else 'Coverage/PIT gate not met'});s.close();return c
def score_candidate(isin,modules,evidence,track='B',as_of=None,metric_context=None):
 score,mult=weighted_score(track,modules,evidence); reasons=[k for k,v in modules.items() if v is not None];events=firewall({**(metric_context or {}),'evidence_coverage':evidence});bucket='REJECTED' if firewall_state(events)=='REJECTED' else ('HIGH_PRIORITY' if score>=75 else ('WATCH' if score>=60 else 'CORE'))
 s=session();s.add(ModuleScore(isin=isin,track=track,total_score=score,evidence_multiplier=mult,as_of=as_of or datetime.utcnow()))
 s.add(CandidateState(isin=isin,track=track,bucket=bucket,thesis_state='INTACT' if bucket!='REJECTED' else 'REJECTED',entry_state='NOT_READY',rejection_code=events[0][0] if events else None,score=score,evidence_coverage=evidence,as_of=as_of or datetime.utcnow()))
 for rule,severity,detail in events:s.add(FirewallEvent(isin=isin,rule_id=rule,severity=severity,triggered=True,detail=detail,as_of=as_of or datetime.utcnow()))
 s.commit();s.close();return {'score':score,'bucket':bucket,'firewall':events,'reasons':reasons}
def run_drift(run_id): return {}
