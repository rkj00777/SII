import json
from urllib.parse import urlencode

class BSEBrowser:
    def __init__(self):
        from playwright.sync_api import sync_playwright
        self._pw=sync_playwright().start()
        self.browser=self._pw.chromium.launch(headless=True)
        self.page=self.browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",locale="en-IN")
        self.page.goto("https://www.bseindia.com/",wait_until="domcontentloaded",timeout=60000)
        self.page.wait_for_timeout(2000)
    def fetch_json(self,url):
        data=self.page.evaluate("""async (url)=>{
          const r=await fetch(url,{credentials:'include',headers:{'Accept':'application/json, text/plain, */*','X-Requested-With':'XMLHttpRequest'}});
          const text=await r.text(); return {status:r.status,text};
        }""",url)
        if data["status"]!=200:return {"status":"DATA_UNAVAILABLE","detail":f"BSE browser HTTP {data['status']}"}
        try:return {"status":"OK","raw":json.loads(data["text"])}
        except Exception as e:return {"status":"PARSE_ERROR","detail":str(e)}
    def security_master(self):
        url="https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?"+urlencode({"Group":"","Scripcode":"","industry":"","segment":"Equity","status":"Active"})
        return self.fetch_json(url)
    def announcements(self,scripcode,start=None,end=None,page=1):
        params={"pageno":page,"strCat":"Result","subcategory":"Financial+Results","strSearch":"P","strType":"C","strScrip":str(scripcode)}
        if start:params["strPrevDate"]=start.strftime("%Y%m%d")
        if end:params["strToDate"]=end.strftime("%Y%m%d")
        url="https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?"+urlencode(params)
        return self.fetch_json(url)
