"""Free-only SII source registry."""
FREE_SOURCES = {
    "NSE":{"tier":"PRIMARY_OFFICIAL","base":"https://www.nseindia.com","universe":"/static/market-data/securities-available-for-trading","filings":"/companies-listing/corporate-filings-actions","financial_results":"/companies-listing/corporate-filings-financial-results","integrated_filings":"/companies-listing/corporate-integrated-filing"},
    "BSE":{"tier":"PRIMARY_OFFICIAL","base":"https://www.bseindia.com","role":"security_master_bhavcopy_filings"},
    "TEJHQ":{"tier":"FREE_PUBLIC_MIRROR","dataset":"https://huggingface.co/datasets/tejhq/indian-markets","api":"https://api.tejhq.dev","coverage":"NSE 2010+, BSE 2024-07+"},
    "HUGGINGFACE":{"tier":"FREE_PUBLIC_DISTRIBUTION","base":"https://huggingface.co"},
}
PAID_PROVIDERS={"QntAify","Altys","TrueData","Fincrux","Bloomberg","Refinitiv","LSEG","Capital IQ","FactSet","paid_Screener","paid_Tijori","paid_Trendlyne"}
def assert_free_only(provider:str)->None:
    if provider in PAID_PROVIDERS: raise RuntimeError(f"Paid provider blocked by SII free-only policy: {provider}")
