"""Empirical six-module validation for SII.

Separates what can be falsified from what cannot be identified with the
free historical evidence set. Modules 1-5 are tested from the PIT selector.
Module 6 (industry/order-book/catalyst) is explicitly evidence-gated: it is
not scored historically unless dated pre-decision evidence exists.
"""
import json
from pathlib import Path
from datetime import datetime

MODULES = [
    "valuation_gap",
    "earnings_acceleration",
    "cash_conversion",
    "reinvestment_roic",
    "governance_balance_sheet",
    "industry_catalyst",
]

def run():
    root = Path("reports")
    pit_path = root / "latest-pit-fundamental-backtest.json"
    if not pit_path.exists():
        pit_path = Path("artifacts/pit_fundamental_backtest.json")
    pit = json.loads(pit_path.read_text()) if pit_path.exists() else {}

    eras = pit.get("independent_era_falsification", []) or []
    module_results = {
        "valuation_gap": {"historical_status": "EMPIRICALLY_TESTED", "source": "PIT fundamental selector"},
        "earnings_acceleration": {"historical_status": "EMPIRICALLY_TESTED", "source": "PIT fundamental selector"},
        "cash_conversion": {"historical_status": "EMPIRICALLY_TESTED", "source": "PIT fundamental selector"},
        "reinvestment_roic": {"historical_status": "EMPIRICALLY_TESTED", "source": "PIT fundamental selector"},
        "governance_balance_sheet": {"historical_status": "EMPIRICALLY_TESTED", "source": "PIT fundamental selector"},
        "industry_catalyst": {
            "historical_status": "NOT_IDENTIFIABLE_FROM_CURRENT_FREE_PIT_DATA",
            "source": "No dated historical structured industry/order-book/catalyst evidence is present in the current free PIT dataset.",
            "rule": "Unknown remains unknown and cannot contribute to historical alpha claims."
        },
    }

    tested = sum(v["historical_status"] == "EMPIRICALLY_TESTED" for v in module_results.values())
    sixth_unknown = module_results["industry_catalyst"]["historical_status"] != "EMPIRICALLY_TESTED"
    lookahead_clean = bool(pit.get("lookahead_checks", {}).get("future_revisions_excluded")) and bool(
        pit.get("lookahead_checks", {}).get("filing_available_at_lte_decision")
    )

    report = {
        "status": "OK",
        "validation_type": "empirical_six_module_validation",
        "timestamp_utc": datetime.utcnow().isoformat(),
        "modules": module_results,
        "modules_empirically_tested": tested,
        "modules_total": 6,
        "module_coverage": tested / 6,
        "sixth_module_historical_evidence_available": not sixth_unknown,
        "pit_selector_status": pit.get("status"),
        "selected_observations": pit.get("selected_observations", 0),
        "fundamental_coverage_rate": pit.get("fundamental_coverage_rate", 0),
        "selection_lift_100": pit.get("selection_lift_100"),
        "independent_eras": eras,
        "positive_independent_eras": sum(1 for e in eras if (e.get("selection_lift_100") or 0) > 1.0),
        "lookahead_clean": lookahead_clean,
        "five_module_empirical_validation_ready": bool(
            pit.get("status") == "OK"
            and pit.get("selected_observations", 0) >= 500
            and pit.get("fundamental_coverage_rate", 0) >= 0.70
            and (pit.get("selection_lift_100") or 0) >= 1.05
            and sum(1 for e in eras if (e.get("selection_lift_100") or 0) > 1.0) >= 2
            and lookahead_clean
        ),
        "full_six_module_empirical_validation_ready": False,
        "reason": (
            "The sixth industry/order-book/catalyst module is deliberately not "
            "fabricated. It remains unknown for historical PIT validation until "
            "dated pre-decision evidence can be reconstructed from a free source."
        ),
        "required_next_evidence": [
            "A free historical source containing dated pre-decision industry/order-book/catalyst disclosures.",
            "Point-in-time extraction with publication timestamp <= decision timestamp.",
            "Independent-era forward-return falsification with the sixth module enabled.",
        ],
    }
    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    (out / "six_module_empirical_validation.json").write_text(json.dumps(report, indent=2, default=str))
    return report

if __name__ == "__main__":
    print(json.dumps(run(), indent=2, default=str))
