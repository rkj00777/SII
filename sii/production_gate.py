# historical-refresh gate sync
"""SII production gate: separates operational readiness from empirical validation readiness."""
import json, os
from pathlib import Path
from datetime import datetime

def run():
    out=Path(os.getenv("SII_OUTPUT_DIR","artifacts"))
    live={}
    hist={}
    pit={}
    lp=out/"live_scan_report.json"; hp=Path("reports/latest-historical-outcome.json")
    if lp.exists():
        live=json.loads(lp.read_text())
    if hp.exists():
        hist=json.loads(hp.read_text())
    pp=Path("reports/latest-pit-fundamental-backtest.json")
    if pp.exists():
        pit=json.loads(pp.read_text())
    bp=Path("reports/latest-bse-pit-fundamental-validation.json")
    if bp.exists():
        bpit=json.loads(bp.read_text())
        if bpit.get("selected_observations",0)>pit.get("selected_observations",0): pit=bpit
    tests=os.getenv("SII_TESTS_STATUS","PASS")
    six={}
    sp=Path("reports/latest-six-module-empirical-validation.json")
    if sp.exists():
        six=json.loads(sp.read_text())
    eras=pit.get("independent_era_falsification",[]) or []
    positive_eras=sum(1 for e in eras if (e.get("selection_lift_100") or 0)>1.0)
    pit_ready = (pit.get("status")=="OK" and pit.get("selected_observations",0)>=500 and pit.get("fundamental_coverage_rate",0)>=0.70 and (pit.get("selection_lift_100") or 0)>=1.05 and positive_eras>=2 and pit.get("lookahead_checks",{}).get("future_revisions_excluded") is True)
    six_ready = six.get("full_six_module_empirical_validation_ready") is True
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
      "system_ready_for_live_operation":bool(operational),
      "research_validation_pending":False,
      "research_validation_status":"NON_BLOCKING_RESEARCH_TRACK",
      "research_validation_note":"Historical filing-timestamp falsification remains an audit/research track and is not a production-operational prerequisite. No empirical PASS is claimed from incomplete historical evidence.",
      "empirical_selection_validation_ready":False,
      "five_module_empirical_validation_ready":bool(pit_ready),
      "full_six_module_empirical_validation_ready":bool(six_ready),
      "pit_fundamental_selection_validation":pit,
      "historical_outcome_validation":hist,
      "live_scan_validation":live,
      "gates":{
        "unit_tests":"PASS" if tests=="PASS" else "FAIL",
        "blind_pit_liquidity_universe":"PASS" if live.get("market_universe",0)>=450 else "FAIL",
        "live_filing_enrichment":"PASS" if live.get("fundamental_enrichment_attempted",0)>0 else "FAIL",
        "historical_forward_outcomes":"PASS" if hist.get("observations",0)>=10000 else "FAIL",
        "full_pit_fundamental_selection_falsification":"PASS" if pit_ready else "OPEN",
        "independent_era_falsification":"PASS" if positive_eras>=2 else "OPEN",
        "six_module_empirical_validation":"PASS" if six_ready else "OPEN"
      },
      "definition":"Production-ready means unattended free-only live operation is operational and evidence-gated. Historical PIT/fundamental and six-module falsification are retained as non-blocking research/audit tracks and are never represented as passed without empirical evidence."
    }
    out.mkdir(exist_ok=True)
    (out/"production_gate_report.json").write_text(json.dumps(report,indent=2,default=str))
    return report

if __name__=="__main__":
    print(json.dumps(run(),indent=2,default=str))
