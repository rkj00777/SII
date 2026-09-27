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
        try:
            resp=self.page.goto(url,wait_until="domcontentloaded",timeout=60000)
            status=resp.status if resp else 0
            text=self.page.locator("body").inner_text(timeout=10000)
            if status!=200:return {"status":"DATA_UNAVAILABLE","detail":f"BSE browser HTTP {status}"}
            return {"status":"OK","raw":json.loads(text)}
        except Exception as e:
            return {"status":"DATA_UNAVAILABLE","detail":f"BSE browser navigation: {type(e).__name__}: {e}"}
    def security_master(self):
        url="https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?"+urlencode({"Group":"","Scripcode":"","industry":"","segment":"Equity","status":"Active"})
        return self.fetch_json(url)
    def announcements(self,scripcode,start=None,end=None,page=1):
        params={"pageno":page,"strCat":"Result","subcategory":"Financial+Results","strSearch":"P","strType":"C","strScrip":str(scripcode)}
        if start:params["strPrevDate"]=start.strftime("%Y%m%d")
        if end:params["strToDate"]=end.strftime("%Y%m%d")
        url="https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?"+urlencode(params)
        return self.fetch_json(url)
