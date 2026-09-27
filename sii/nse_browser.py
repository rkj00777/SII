import json
from urllib.parse import urlencode

class NSEBrowserCatalog:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw=sync_playwright().start()
        self.browser=self._pw.chromium.launch(headless=True)
        self.page=self.browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36", locale="en-IN")
        self.page.goto("https://www.nseindia.com/companies-listing/corporate-integrated-filing", wait_until="domcontentloaded", timeout=60000)
        self.page.wait_for_timeout(3000)

    def fetch(self,symbol,start,end,page=1,size=20,issuer=None):
        params={"type":"Integrated Filing- Financials","page":page,"size":size,"index":"equities","symbol":symbol,"period_ended":"all","from_date":start.strftime("%d-%m-%Y"),"to_date":end.strftime("%d-%m-%Y")}
        if issuer: params["issuer"]=issuer
        url="https://www.nseindia.com/api/integrated-filing-results?"+urlencode(params)
        data=self.page.evaluate("""async (url) => {
          const r=await fetch(url,{credentials:'include',headers:{'X-Requested-With':'XMLHttpRequest','Accept':'application/json, text/plain, */*'}});
          const text=await r.text();
          return {status:r.status,text};
        }""",url)
        if data["status"]!=200: return {"status":"DATA_UNAVAILABLE","detail":f"browser HTTP {data['status']}"}
        try: return {"status":"OK","raw":json.loads(data["text"])}
        except Exception as e: return {"status":"PARSE_ERROR","detail":str(e)}

    def fetch_legacy(self,symbol,period="Quarterly"):
        params={"index":"equities","period":period}
        if symbol: params["symbol"]=symbol
        url="https://www.nseindia.com/api/corporates-financial-results?"+urlencode(params)
        data=self.page.evaluate("""async (url) => {
          const r=await fetch(url,{credentials:'include',headers:{'X-Requested-With':'XMLHttpRequest','Accept':'application/json, text/plain, */*'}});
          const text=await r.text(); return {status:r.status,text};
        }""",url)
        if data["status"]!=200: return {"status":"DATA_UNAVAILABLE","detail":f"legacy browser HTTP {data['status']}"}
        try:return {"status":"OK","raw":json.loads(data["text"])}
        except Exception as e:return {"status":"PARSE_ERROR","detail":str(e)}

    def close(self):
        try:self.browser.close()
        finally:self._pw.stop()
