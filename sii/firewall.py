def firewall(m):
 out=[]
 if m.get('median_turnover_lacs') is not None and m['median_turnover_lacs']<10:out.append(('LIQUIDITY_HARD','HARD','Low liquidity'))
 if m.get('debt_to_equity') is not None and m['debt_to_equity']>3:out.append(('LEVERAGE','HARD','High leverage'))
 if m.get('evidence_coverage',1)<.5:out.append(('INSUFFICIENT_EVIDENCE','HARD','Insufficient evidence'))
 if m.get('promoter_pledge',0)>0.25:out.append(('PLEDGE','HARD','High promoter pledge'))
 return out
def firewall_state(events): return 'REJECTED' if any(e[1]=='HARD' for e in events) else 'CLEAR'
