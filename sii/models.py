from datetime import datetime
from sqlalchemy import String,Integer,Float,Boolean,DateTime,Text,JSON,ForeignKey
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
class Security(Base):
 __tablename__='securities'
 isin:Mapped[str]=mapped_column(String(20),primary_key=True); name:Mapped[str]=mapped_column(String(300),default=''); nse_symbol:Mapped[str|None]=mapped_column(String(80)); bse_code:Mapped[str|None]=mapped_column(String(30)); series:Mapped[str|None]=mapped_column(String(20)); segment:Mapped[str]=mapped_column(String(20),default='MAIN'); eligible:Mapped[bool]=mapped_column(Boolean,default=False); exclusion_code:Mapped[str|None]=mapped_column(String(80)); exclusion_reason:Mapped[str|None]=mapped_column(Text); listed_nse:Mapped[bool]=mapped_column(Boolean,default=False); listed_bse:Mapped[bool]=mapped_column(Boolean,default=False); source_urls:Mapped[list]=mapped_column(JSON,default=list); first_seen_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); last_seen_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class IngestionRun(Base):
 __tablename__='ingestion_runs'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); job_type:Mapped[str]=mapped_column(String(60)); status:Mapped[str]=mapped_column(String(30),default='running'); started_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); finished_at:Mapped[datetime|None]=mapped_column(DateTime); stats:Mapped[dict]=mapped_column(JSON,default=dict); run_hash:Mapped[str|None]=mapped_column(String(128)); critical_errors:Mapped[int]=mapped_column(Integer,default=0); error_count:Mapped[int]=mapped_column(Integer,default=0)
class MarketPrice(Base):
 __tablename__='market_prices'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); isin:Mapped[str|None]=mapped_column(String(20),index=True); symbol:Mapped[str]=mapped_column(String(80),index=True); exchange:Mapped[str]=mapped_column(String(10)); trade_date:Mapped[datetime]=mapped_column(DateTime,index=True); open:Mapped[float|None]=mapped_column(Float); high:Mapped[float|None]=mapped_column(Float); low:Mapped[float|None]=mapped_column(Float); close:Mapped[float|None]=mapped_column(Float); volume:Mapped[float|None]=mapped_column(Float); turnover:Mapped[float|None]=mapped_column(Float); available_at:Mapped[datetime]=mapped_column(DateTime); source_url:Mapped[str]=mapped_column(Text)
class FinancialMetric(Base):
 __tablename__='financial_metrics'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); isin:Mapped[str]=mapped_column(String(20),index=True); period_end:Mapped[datetime]=mapped_column(DateTime); available_at:Mapped[datetime]=mapped_column(DateTime,index=True); metric:Mapped[str]=mapped_column(String(100)); value:Mapped[float|None]=mapped_column(Float); unit:Mapped[str|None]=mapped_column(String(30)); basis:Mapped[str|None]=mapped_column(String(30)); source_url:Mapped[str]=mapped_column(Text); source_type:Mapped[str]=mapped_column(String(40))
class CandidateState(Base):
 __tablename__='candidate_states'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); isin:Mapped[str]=mapped_column(String(20),index=True); track:Mapped[str]=mapped_column(String(1)); bucket:Mapped[str]=mapped_column(String(30)); thesis_state:Mapped[str]=mapped_column(String(30)); entry_state:Mapped[str]=mapped_column(String(40)); rejection_code:Mapped[str|None]=mapped_column(String(80)); score:Mapped[float]=mapped_column(Float); evidence_coverage:Mapped[float]=mapped_column(Float); as_of:Mapped[datetime]=mapped_column(DateTime)
class FirewallEvent(Base):
 __tablename__='firewall_events'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); isin:Mapped[str]=mapped_column(String(20),index=True); rule_id:Mapped[str]=mapped_column(String(80)); severity:Mapped[str]=mapped_column(String(20)); triggered:Mapped[bool]=mapped_column(Boolean); detail:Mapped[str|None]=mapped_column(Text); as_of:Mapped[datetime]=mapped_column(DateTime)
class ModelDrift(Base):
 __tablename__='model_drift'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); run_id:Mapped[int]; metric:Mapped[str]=mapped_column(String(80)); value:Mapped[float]; threshold:Mapped[float]; status:Mapped[str]=mapped_column(String(20)); detail:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class CoverageAudit(Base):
 __tablename__='coverage_audits'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); run_id:Mapped[int]; universe_coverage:Mapped[float]=mapped_column(Float); market_coverage:Mapped[float]=mapped_column(Float); fundamental_coverage:Mapped[float]=mapped_column(Float); evidence_coverage:Mapped[float]=mapped_column(Float); pit_coverage:Mapped[float]=mapped_column(Float); critical_errors:Mapped[int]=mapped_column(Integer); run_hash:Mapped[str|None]=mapped_column(String(128)); gate_passed:Mapped[bool]=mapped_column(Boolean); detail:Mapped[dict]=mapped_column(JSON,default=dict); created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
class SourceAudit(Base):
 __tablename__='source_audits'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); run_id:Mapped[int|None]=mapped_column(ForeignKey('ingestion_runs.id')); source:Mapped[str]=mapped_column(String(80)); url:Mapped[str]=mapped_column(Text); status:Mapped[str]=mapped_column(String(30)); http_status:Mapped[int|None]=mapped_column(Integer); retrieved_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow); content_hash:Mapped[str|None]=mapped_column(String(128)); detail:Mapped[str|None]=mapped_column(Text)
class EvidenceSource(Base):
 __tablename__='evidence_sources'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); isin:Mapped[str]=mapped_column(String(20),index=True); evidence_type:Mapped[str]=mapped_column(String(80)); title:Mapped[str|None]=mapped_column(Text); published_at:Mapped[datetime|None]=mapped_column(DateTime); available_at:Mapped[datetime]=mapped_column(DateTime); source_url:Mapped[str]=mapped_column(Text); tier:Mapped[str]=mapped_column(String(20)); content_hash:Mapped[str|None]=mapped_column(String(128)); extracted:Mapped[dict]=mapped_column(JSON,default=dict)
class ModuleScore(Base):
 __tablename__='module_scores'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); isin:Mapped[str]=mapped_column(String(20),index=True); track:Mapped[str]=mapped_column(String(1)); total_score:Mapped[float]=mapped_column(Float,default=0); evidence_multiplier:Mapped[float]=mapped_column(Float,default=0); as_of:Mapped[datetime]=mapped_column(DateTime)
class HistoricalArchetype(Base):
 __tablename__='historical_reference_cases'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); name:Mapped[str]=mapped_column(String(120)); tags:Mapped[list]=mapped_column(JSON,default=list); description:Mapped[str]=mapped_column(Text); qualitative_only:Mapped[bool]=mapped_column(Boolean,default=True)
class ThesisChange(Base):
 __tablename__='thesis_changes'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); isin:Mapped[str]=mapped_column(String(20),index=True); previous_state:Mapped[str|None]=mapped_column(String(30)); new_state:Mapped[str]=mapped_column(String(30)); reason:Mapped[str]=mapped_column(Text); as_of:Mapped[datetime]=mapped_column(DateTime)
class RunError(Base):
 __tablename__='run_errors'
 id:Mapped[int]=mapped_column(Integer,primary_key=True); run_id:Mapped[int]; source:Mapped[str]; severity:Mapped[str]; message:Mapped[str]; created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
