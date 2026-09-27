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
    metrics=[
      {"metric":"pat","value":10,"period_end":"2024-03-31","duration_days":90,"available_at":"2024-05-10T12:00:00"},
      {"metric":"pat","value":20,"period_end":"2024-03-31","duration_days":90,"available_at":"2024-08-10T12:00:00"},
      {"metric":"cfo","value":12,"period_end":"2024-03-31","duration_days":90,"available_at":"2024-05-10T12:00:00"},
      {"metric":"cfo","value":24,"period_end":"2024-03-31","duration_days":90,"available_at":"2024-08-10T12:00:00"},
    ]
    snap=_snapshot(metrics,datetime(2024,6,1,15,30))
    assert snap["pat"].tail(1).iloc[0].value==10
    assert snap["cfo"].tail(1).iloc[0].value==12

def test_bse_universe_sample_schema():
    sample={"SCRIP_CD":"500002","Scrip_Name":"ABB India Limited","Status":"Active","ISIN_NUMBER":"INE117A01022","scrip_id":"ABB","Segment":"Equity"}
    assert len(sample["ISIN_NUMBER"])==12
