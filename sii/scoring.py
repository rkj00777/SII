WEIGHTS={'A':{'valuation_gap':.35,'earnings_acceleration':.15,'cash_conversion':.20,'reinvestment_roic':.10,'governance_balance_sheet':.20,'industry_catalyst':0},'B':{'valuation_gap':.10,'earnings_acceleration':.30,'cash_conversion':.10,'reinvestment_roic':.20,'governance_balance_sheet':.10,'industry_catalyst':.20}}
MODULES=list(WEIGHTS['A'])
def clamp(x): return None if x is None else max(0,min(100,float(x)))
def evidence_multiplier(coverage):
 if coverage>=.90:return 1.0
 if coverage>=.80:return .90
 if coverage>=.65:return .75
 if coverage>=.50:return .60
 return .35
def weighted_score(track,modules,evidence):
 w=WEIGHTS[track]; vals=[(k,clamp(modules.get(k))) for k in w if modules.get(k) is not None]; base=sum(w[k]*v for k,v in vals)/sum(w[k] for k,v in vals) if vals else 0; em=evidence_multiplier(evidence); return round(base*em,4),em
