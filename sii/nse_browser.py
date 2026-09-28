import asyncio
import json
import threading
from urllib.parse import urlencode

class NSEBrowserCatalog:
    """Synchronous facade over Playwright's async API.

    The caller may itself be running inside asyncio. Playwright therefore runs
    on a dedicated background event-loop thread so the Sync API is never
    invoked from an active asyncio loop.
    """

    def __init__(self):
        self._ready = threading.Event()
        self._closed = False
        self._thread = threading.Thread(target=self._thread_main, name="sii-nse-playwright", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=90):
            raise RuntimeError("Timed out starting NSE Playwright worker")
        if getattr(self, "_startup_error", None):
            raise RuntimeError(f"NSE Playwright startup failed: {self._startup_error}")

    def _thread_main(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            from playwright.async_api import async_playwright
            self._loop.run_until_complete(self._async_start(async_playwright))
            self._ready.set()
            self._loop.run_forever()
        except Exception as exc:
            self._startup_error = exc
            self._ready.set()

    async def _async_start(self, async_playwright):
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=True)
        self.page = await self.browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
            locale="en-IN",
        )
        await self.page.goto(
            "https://www.nseindia.com/companies-listing/corporate-integrated-filing",
            wait_until="domcontentloaded",
            timeout=60000,
        )
        await self.page.wait_for_timeout(3000)

    def _run(self, coro, timeout=120):
        if self._closed:
            raise RuntimeError("NSE browser is closed")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    async def _fetch_json(self, url):
        data = await self.page.evaluate(
            """async (url) => {
              const r = await fetch(url, {
                credentials: 'include',
                headers: {
                  'X-Requested-With': 'XMLHttpRequest',
                  'Accept': 'application/json, text/plain, */*'
                }
              });
              const text = await r.text();
              return {status: r.status, text};
            }""",
            url,
        )
        if data["status"] != 200:
            return {"status": "DATA_UNAVAILABLE", "detail": f"browser HTTP {data['status']}"}
        try:
            return {"status": "OK", "raw": json.loads(data["text"])}
        except Exception as exc:
            return {"status": "PARSE_ERROR", "detail": str(exc)}

    def fetch(self, symbol, start, end, page=1, size=20, issuer=None):
        params = {
            "type": "Integrated Filing- Financials",
            "page": page,
            "size": size,
            "index": "equities",
            "symbol": symbol,
            "period_ended": "all",
            "from_date": start.strftime("%d-%m-%Y"),
            "to_date": end.strftime("%d-%m-%Y"),
        }
        if issuer:
            params["issuer"] = issuer
        return self._run(self._fetch_json(
            "https://www.nseindia.com/api/integrated-filing-results?" + urlencode(params)
        ))

    def fetch_legacy(self, symbol, period="Quarterly", start=None, end=None, page=1, size=100):
        params = {"index": "equities", "period": period, "page": page, "size": size}
        if start:
            params["from_date"] = start.strftime("%d-%m-%Y")
        if end:
            params["to_date"] = end.strftime("%d-%m-%Y")
        if symbol:
            params["symbol"] = symbol
        return self._run(self._fetch_json(
            "https://www.nseindia.com/api/corporates-financial-results?" + urlencode(params)
        ))

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(timeout=30)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=30)

    async def _async_close(self):
        try:
            await self.browser.close()
        finally:
            await self._pw.stop()
