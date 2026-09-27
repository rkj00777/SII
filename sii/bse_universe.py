"""Current BSE equity universe from the public BSE security master."""
import json, os
from pathlib import Path
from .adapters import BSEAdapter

def run():
    r=BSEAdapter().security_master()
    if r.status!="OK":
        return {"status":r.status,"rows":0,"detail":r.detail}
    try:data=json.loads(r.content.decode("utf-8"))
    except Exception as e:return {"status":"PARSE_ERROR","rows":0,"detail":str(e)}
    rows=data if isinstance(data,list) else data.get("Table",data.get("data",[]))
    out=[]
    for x in rows:
        isin=str(x.get("ISIN_NUMBER") or x.get("ISIN") or "").strip()
        code=str(x.get("SCRIP_CD") or x.get("Scripcode") or "").strip()
        symbol=str(x.get("scrip_id") or x.get("Scrip_Name") or "").strip()
        name=str(x.get("Issuer_Name") or x.get("Scrip_Name") or "").strip()
        if len(isin)==12 and isin.startswith("IN") and code:
            out.append({"exchange":"BSE","bse_scrip_code":code,"symbol":symbol,"name":name,"isin":isin,
                        "group":x.get("GROUP"),"industry":x.get("INDUSTRY"),"status":x.get("Status"),
                        "source_type":"BSE_SECURITY_MASTER","source_url":"https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"})
    ded={x["isin"]:x for x in out}
    report={"status":"OK","as_of":__import__("datetime").datetime.utcnow().isoformat(),"rows":len(ded),
            "raw_rows":len(rows),"source":"BSE public security master","dedup_key":"ISIN",
            "notes":["Current BSE equity universe; suspended/delisted securities are not silently mixed into active universe.",
                     "BSE scrip code and ISIN are retained for filing joins."]}
    outdir=Path(os.getenv("SII_OUTPUT_DIR","artifacts"));outdir.mkdir(exist_ok=True)
    (outdir/"bse_universe_report.json").write_text(json.dumps(report,indent=2))
    (outdir/"bse_universe.json").write_text(json.dumps(list(ded.values()),indent=2,default=str))
    return report
if __name__=="__main__":print(json.dumps(run(),indent=2))
