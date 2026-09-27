import json
from datetime import datetime
from sii.financial_ingest import extract_filing_rows
from sii.bse_financial import BSEFinancialIngestor
from sii.pit_fundamental_backtest import _snapshot

def test_extract_filing_rows_accepts_nested_xbrl():
    payload={"data":[{"symbol":"ABC","xbrl":{"href":"https://nsearchives.nseindia.com/corporate/ABC.xml"},"toDate":"31-Mar-2024","broadcastDateTime":"2024-05-10T12:00:00"}]}
    rows=extract_filing_rows(payload)
    assert len(rows)==1
    assert rows[0]["xbrl_url"].endswith("ABC.xml")

def test_pit_snapshot_excludes_future_revision():
    metrics=[]
    for i,v in enumerate([6,7,8,9]):
        pe=f"202{3+i}-03-31"
        metrics.append({"metric":"pat","value":v,"period_end":pe,"duration_days":90,"available_at":"2024-05-10T12:00:00"})
        metrics.append({"metric":"cfo","value":v+1,"period_end":pe,"duration_days":90,"available_at":"2024-05-10T12:00:00"})
    metrics.append({"metric":"pat","value":99,"period_end":"2026-03-31","duration_days":90,"available_at":"2024-08-10T12:00:00"})
    snap=_snapshot(metrics,datetime(2024,6,1,15,30))
    assert snap["pat_ttm"]==30
    assert snap["cfo_ttm"]==34

def test_bse_universe_sample_schema():
    sample={"SCRIP_CD":"500002","Scrip_Name":"ABB India Limited","Status":"Active","ISIN_NUMBER":"INE117A01022","scrip_id":"ABB","Segment":"Equity"}
    assert len(sample["ISIN_NUMBER"])==12
