import re
from datetime import datetime

def normalize_nse(row,segment):
    isin=(row.get('ISIN') or row.get('ISIN_CODE') or '').strip(); symbol=(row.get('SYMBOL') or row.get('Symbol') or '').strip(); name=(row.get('NAME OF COMPANY') or row.get('NAME_OF_COMPANY') or row.get('NAME') or '').strip(); series=(row.get('SERIES') or '').strip()
    if not re.fullmatch(r'IN[A-Z0-9]{10}',isin): return None
    allowed={'EQ','BE'} if segment=='MAIN' else {'SM','ST'}
    excluded=not(series in allowed)
    return {'isin':isin,'name':name,'nse_symbol':symbol,'series':series,'segment':segment,'eligible':not excluded,'exclusion_code':('X_SERIES' if excluded else None),'exclusion_reason':('Non-equity/ineligible series' if excluded else None),'listed_nse':True,'source_urls':[],'last_seen_at':datetime.utcnow()}

def merge_rows(rows):
    out={}
    for r in rows:
        if not r:continue
        old=out.get(r['isin'])
        if not old:out[r['isin']]=r; continue
        old['eligible']=old['eligible'] or r['eligible']; old['listed_nse']=old['listed_nse'] or r['listed_nse']; old['source_urls']=list(set((old.get('source_urls') or [])+(r.get('source_urls') or [])))
    return out
