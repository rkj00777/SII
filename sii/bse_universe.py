"""Current BSE equity universe from the public BSE security master."""
import json, os
from pathlib import Path
from .adapters import BSEAdapter

def run():
    r=BSEAdapter().security_master()
    data=None
    if r.status=="OK":
        try:data=json.loads(r.content.decode("utf-8"))
        except Exception:data=None
    if data is None:
        try:
            from .bse_browser import BSEBrowser
            br=BSEBrowser().security_master()
            if br.get("status")!="OK": return {"status":br.get("status","DATA_UNAVAILABLE"),"rows":0,"detail":br.get("detail")}
            data=br.get("raw")
        except Exception as e:
            return {"status":"DATA_UNAVAILABLE","rows":0,"detail":f"BSE browser fallback: {type(e).__name__}: {e}"}
    source="BSE official security master"
    if data is None:
        try:
            import duckdb
            y=__import__('datetime').date.today().year
            con=duckdb.connect()
            path=f"https://huggingface.co/datasets/tejhq/indian-markets/resolve/main/bse/year={y}/bse_{y}.parquet?download=true"
            data_rows=con.execute(f"SELECT * FROM read_parquet('{path}') WHERE date=(SELECT max(date) FROM read_parquet('{path}')) AND series IN ('A','B','T')").fetchdf().to_dict('records')
            data={'Table':data_rows}; source='TejHQ BSE market-data fallback'
        except Exception as e:
            return {"status":"DATA_UNAVAILABLE","rows":0,"detail":f"BSE official+browser+TejHQ fallback failed: {type(e).__name__}: {e}"}
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
            "raw_rows":len(rows),"source":source,"dedup_key":"ISIN",
            "notes":["Current BSE equity universe; suspended/delisted securities are not silently mixed into active universe.",
                     "BSE scrip code and ISIN are retained for filing joins."]}
    outdir=Path(os.getenv("SII_OUTPUT_DIR","artifacts"));outdir.mkdir(exist_ok=True)
    (outdir/"bse_universe_report.json").write_text(json.dumps(report,indent=2))
    (outdir/"bse_universe.json").write_text(json.dumps(list(ded.values()),indent=2,default=str))
    return report
if __name__=="__main__":print(json.dumps(run(),indent=2))
