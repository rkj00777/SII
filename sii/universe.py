import re
from datetime import datetime

def _pick(row, *keys):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return str(row[k]).strip()
    return ""

def normalize_nse(row, segment):
    isin=_pick(row,'ISIN','ISIN_CODE','ISIN NUMBER','ISIN_NUMBER','ISIN NO','ISIN_NO')
    symbol=_pick(row,'SYMBOL','Symbol')
    name=_pick(row,'NAME OF COMPANY','NAME_OF_COMPANY','NAME')
    series=_pick(row,'SERIES','Series')
    allowed={'EQ','BE'} if segment=='MAIN' else {'SM','ST','STP'}
    if not re.fullmatch(r'IN[A-Z0-9]{10}',isin):
        return None
    excluded=series not in allowed
    return {
        'isin':isin,'name':name,'nse_symbol':symbol,'series':series,
        'segment':segment,'eligible':not excluded,
        'exclusion_code':('X_SERIES' if excluded else None),
        'exclusion_reason':('Non-equity/ineligible series' if excluded else None),
        'listed_nse':True,'source_urls':[],'last_seen_at':datetime.utcnow()
    }

def merge_rows(rows):
    out={}
    for r in rows:
        if not r: continue
        old=out.get(r['isin'])
        if not old:
            out[r['isin']]=r
            continue
        old['eligible']=old['eligible'] or r['eligible']
        old['listed_nse']=old['listed_nse'] or r['listed_nse']
        old['source_urls']=list(set((old.get('source_urls') or [])+(r.get('source_urls') or [])))
        if not old.get('nse_symbol'): old['nse_symbol']=r.get('nse_symbol')
        if not old.get('name'): old['name']=r.get('name')
    return out
