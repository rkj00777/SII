from datetime import datetime,timedelta
from types import SimpleNamespace
from sii.pit import pit_rows,assert_no_lookahead
from sii.scoring import weighted_score
from sii.firewall import firewall,firewall_state
from sii.falsifier import forward_outcome
def test_pit_blocks_future():
 now=datetime(2026,1,1);rows=[SimpleNamespace(available_at=now-timedelta(days=1)),SimpleNamespace(available_at=now+timedelta(days=1))]
 assert len(pit_rows(rows,now))==1
 try:assert_no_lookahead(rows,now);assert False
 except AssertionError:pass
def test_score_deterministic():
 m={'valuation_gap':80,'earnings_acceleration':70,'cash_conversion':60,'reinvestment_roic':75,'governance_balance_sheet':90,'industry_catalyst':50};assert weighted_score('B',m,.9)==weighted_score('B',m,.9)
def test_low_evidence_discount():
 m={k:100 for k in ['valuation_gap','earnings_acceleration','cash_conversion','reinvestment_roic','governance_balance_sheet','industry_catalyst']};assert weighted_score('B',m,.4)[0]<100
def test_firewall():
 ev=firewall({'median_turnover_lacs':5,'debt_to_equity':4,'evidence_coverage':.2});ids={x[0] for x in ev};assert 'LIQUIDITY_HARD' in ids and 'LEVERAGE' in ids and 'INSUFFICIENT_EVIDENCE' in ids;assert firewall_state(ev).startswith('REJECTED')
def test_falsifier():
 rows=[{'date':datetime(2020,1,1).date(),'symbol':'X','adj_close':100},{'date':datetime(2020,1,2).date(),'symbol':'X','adj_close':205}];o=forward_outcome(rows,datetime(2020,1,1).date());assert o.hit_100 and o.days_to_100==1
def test_free_only_policy_blocks_paid_sources():
 from sii.free_sources import assert_free_only
 import pytest
 assert_free_only('NSE');assert_free_only('TEJHQ')
 with pytest.raises(RuntimeError):assert_free_only('TrueData')
