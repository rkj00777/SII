import json
from datetime import datetime,timedelta
from .financial_ingest import NSEFinancialIngestor

for sym in ["TBZ","WELCORP","RAYMOND"]:
    ing=NSEFinancialIngestor()
    r=ing.catalog(sym,datetime(2026,6,1),datetime(2026,9,25),page_size=5)
    print("SYMBOL",sym,"STATUS",r.get("status"),"DETAIL",r.get("detail"))
    print("ROWS",len(r.get("rows",[])))
    if r.get("raw") is not None:
        raw=r["raw"]
        print("RAW_TYPE",type(raw).__name__)
        if isinstance(raw,dict):
            print("RAW_KEYS",list(raw.keys())[:50])
            for k,v in raw.items():
                if isinstance(v,list) and v:
                    print("LIST_KEY",k,"ITEM_KEYS",list(v[0].keys())[:50] if isinstance(v[0],dict) else type(v[0]).__name__)
                    print("FIRST_ITEM",json.dumps(v[0],default=str)[:5000])
                    break
