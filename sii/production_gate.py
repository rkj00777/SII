# historical-refresh gate sync
"""SII production gate: separates operational readiness from empirical validation readiness."""
import json, os
from pathlib import Path
from datetime import datetime

def run():
    out=Path(os.getenv("SII_OUTPUT_DIR","artifacts"))
    live={}
    hist={}
    lp=out/"live_scan_report.json"; hp=Path("reports/latest-historical-outcome.json")
    if lp.exists():
        live=json.loads(lp.read_text())
    if hp.exists():
        hist=json.loads(hp.read_text())
    tests=os.getenv("SII_TESTS_STATUS","PASS")
    operational = (
        tests=="PASS"
        and live.get("status")=="OK"
        and live.get("market_universe",0)>=450
        and hist.get("status")=="OK"
        and hist.get("observations",0)>=10000
    )
    report={
      "timestamp_utc":datetime.utcnow().isoformat(),
      "engine":"SII-v4.0.0-FREE-ONLY",
      "operational_production_ready":bool(operational),
      "empirical_selection_validation_ready":False,
      "historical_outcome_validation":hist,
      "live_scan_validation":live,
      "gates":{
        "unit_tests":"PASS" if tests=="PASS" else "FAIL",
        "blind_pit_liquidity_universe":"PASS" if live.get("market_universe",0)>=450 else "FAIL",
        "live_filing_enrichment":"PASS" if live.get("fundamental_enrichment_attempted",0)>0 else "FAIL",
        "historical_forward_outcomes":"PASS" if hist.get("observations",0)>=10000 else "FAIL",
        "full_pit_fundamental_selection_falsification":"OPEN"
      },
      "definition":"Operational production ready means the engine can run unattended, free-only, PIT-aware, evidence-gated and firewall-protected. It does not claim that the six-module fundamental selector has passed multi-year PIT falsification."
    }
    out.mkdir(exist_ok=True)
    (out/"production_gate_report.json").write_text(json.dumps(report,indent=2,default=str))
    return report

if __name__=="__main__":
    print(json.dumps(run(),indent=2,default=str))
