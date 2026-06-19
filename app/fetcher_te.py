import re
import time
import logging
from datetime import datetime
from app.config import FETCH_LIMIT, RETRY_BASE_DELAY

from playwright.sync_api import sync_playwright

_log = logging.getLogger("DataHarvester")

INTERVAL_SELECTOR = {
    "Day": "1d",
    "Week": "1w",
}
DEFAULT_INTERVAL_ATTR = "1w"

#   exchange = "https://tradingeconomics.com/"
#   symbol   = "commodity/crude-oil"
def _build_url(symbol, exchange):
    return "https://tradingeconomics.com/" + symbol


def _clean_float(text):
    if text is None:
        return None
    cleaned = re.sub(r"[+%(),\s]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(text):
    return datetime.strptime(text.strip(), "%b %d %Y")


def fetch_data(dhc_id, symbol, exchange, interval, last_success, retry_max):
    
    url = _build_url(symbol, exchange)
    interval_attr = INTERVAL_SELECTOR.get(interval, DEFAULT_INTERVAL_ATTR)

    for attempt in range(1, retry_max + 1):
        _log.info(f"[{dhc_id}] Fetching {url} ({interval_attr}) (attempt {attempt}/{retry_max})")
        try:
            records = _scrape_once(dhc_id, url, interval_attr, last_success)
        except Exception as e:
            _log.warning(f"[{dhc_id}] TE scrape error on attempt {attempt}: {e}")
            records = []

        if records:
            _log.info(f"[{dhc_id}] Fetched {len(records)} bars for {symbol}")
            return records

        wait = RETRY_BASE_DELAY ** attempt
        _log.warning(f"[{dhc_id}] Empty result, retrying in {wait:.1f}s...")
        time.sleep(wait)

    _log.error(f"[{dhc_id}] All {retry_max} attempts failed for {symbol}")
    return []


def _scrape_once(dhc_id, url, interval_attr, last_success):
    records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
          headless=False, 
          slow_mo=20,
          args=["--window-size=1,1", "--window-position=-1000,-1000"]
        )
        try:
            page = browser.new_page(viewport={"width": 1000, "height": 500})
            page.goto(url)

            page.wait_for_selector("#fullscreenBtn")
            page.locator("#fullscreenBtn").click()

            page.wait_for_selector("#iChart-bodyLabels-cntx", timeout=30000)

            page.evaluate(
                """
                (intervalAttr) => {
                    document.querySelector("a[data-type='ohlc']").click()
                    const el = document.querySelector(`a[data-interval='${intervalAttr}']`);
                    if (el) el.click();
                }
                """,
                interval_attr,
            )
            
            page.wait_for_selector("g.highcharts-series-0 > path")
            paths = page.locator("g.highcharts-series-0 > path")
            total = paths.count()

            page.evaluate("""
            () => {
                const cntx = document.querySelector('#iChart-bodyLabels-cntx');
                const chart = document.querySelector('.iChart-chart');
                document.head.innerHTML = '';
                document.body.innerHTML = '';
                document.body.appendChild(cntx);
                document.body.appendChild(chart);
            }
            """)

            if last_success is None:
                start = 0
            else:
                start = max(0, total - FETCH_LIMIT)

            for i in range(start, total):
                path = paths.nth(i)
                box = path.bounding_box()
                if not box:
                    continue

                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                page.mouse.move(x, y)

                try:
                    raw_date = page.locator(".yLabelDrag").inner_text().strip()
                    dt = _parse_date(raw_date)

                    o = _clean_float(page.locator(".openLabel").inner_text())
                    h = _clean_float(page.locator(".highLabel").inner_text())
                    l = _clean_float(page.locator(".lowLabel").inner_text())
                    c = _clean_float(page.locator(".closeLabel").inner_text())

                    if None in (o, h, l, c):
                        _log.warning(f"[{dhc_id}] Skipping unparseable row at index {i}: "
                                     f"o={o} h={h} l={l} c={c} raw_date={raw_date!r}")
                        continue

                except Exception as e:
                    _log.warning(f"[{dhc_id}] Skipping point {i}: {e}")
                    continue
                
                # chg, chg_pct = None, None
                # try:
                #     chg = _clean_float(page.locator(".nChange").inner_text(timeout=0))
                #     chg_pct = _clean_float(page.locator(".percChange").inner_text(timeout=0))
                # except Exception:
                #     pass  # fall through to the calculated fallback below
                
                # if (chg is None or chg_pct is None) and records:
                #     prev_close = records[-1][4]  # close is index 4 in our tuple
                #     if prev_close:
                #         if chg is None:
                #             chg = round(c - prev_close, 6)
                #         if chg_pct is None:
                #             chg_pct = round((c - prev_close) / prev_close * 100, 6)

                records.append((dt, o, h, l, c, None))
        finally:
            browser.close()

    return records