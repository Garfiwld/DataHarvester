import re
import time
import logging
from datetime import datetime

from playwright.sync_api import sync_playwright

_log = logging.getLogger("DataHarvester")

# TE chart "recent window" lookback for non-initial refreshes.
RECENT_POINTS = 10

INTERVAL_SELECTOR = {
    "Day": "1d",
    "Week": "1w",
}
DEFAULT_INTERVAL_ATTR = "1d"


# Build full TE URL from config: DHC_Exchange is the domain prefix,
# DHC_Symbol is the path slug, e.g.
#   exchange = "https://tradingeconomics.com/"
#   symbol   = "commodity/crude-oil"
def _build_url(symbol, exchange):
    return "https://tradingeconomics.com/" + symbol


def _clean_float(text):
    """Strip +, %, (), spaces, commas before float conversion."""
    if text is None:
        return None
    cleaned = re.sub(r"[+%(),\s]", "", text)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(text):
    """
    TE renders .yLabelDrag as e.g. 'Jun 12 2026' for daily/weekly charts.
    Raise if the format ever changes so we notice instead of silently
    inserting wrong timestamps.
    """
    return datetime.strptime(text.strip(), "%b %d %Y")


def fetch_data(dhc_id, symbol, exchange, interval, last_success, retry_max):
    """
    Returns a list of 8-tuples:
        (datetime, open, high, low, close, volume, close_change, close_change_pct)

    TE has no volume data on these commodity charts -> volume = None.
    close_change / close_change_pct come straight from TE's own tooltip
    (nChange / percChange) rather than being derived locally.

    NOTE: this is a different shape than fetcher_tv.fetch_data's 6-tuples
    (no change/pct columns there, since TV doesn't expose them and
    app/updater.py computes those for TV rows after the fact). app/loader.py
    handles both shapes.
    """
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

        wait = 2.0 ** attempt
        _log.warning(f"[{dhc_id}] Empty result, retrying in {wait:.1f}s...")
        time.sleep(wait)

    _log.error(f"[{dhc_id}] All {retry_max} attempts failed for {symbol}")
    return []


def _scrape_once(dhc_id, url, interval_attr, last_success):
    records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=20)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 500})
            page.goto(url)
            page.wait_for_timeout(3000)

            # Select interval (Day/Week) BEFORE switching to OHLC view.
            page.evaluate(
                """
                (intervalAttr) => {
                    const el = document.querySelector(`a[data-interval='${intervalAttr}']`);
                    if (el) el.click();
                }
                """,
                interval_attr,
            )
            page.wait_for_timeout(3000)

            page.evaluate("""
                () => {
                    document.querySelector("a[data-type='ohlc']").click()
                    document.querySelector("#fullscreenBtn").click();
                }
            """)

            page.wait_for_timeout(3000)

            page.evaluate("""
            () => {
                const chart = document.querySelector('.iChart-chart');
                const cntx = document.querySelector('#iChart-bodyLabels-cntx');
                document.head.innerHTML = '';
                document.body.innerHTML = '';
                document.body.appendChild(chart);
                document.body.appendChild(cntx);
            }
            """)

            page.wait_for_timeout(1000)

            paths = page.locator("g.highcharts-series-0 > path")
            total = paths.count()

            if last_success is None:
                # Initial fetch: take everything except the first point,
                # which is often a partial/cut-off candle at the chart edge.
                start = 1
            else:
                start = max(0, total - RECENT_POINTS)

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
                    chg = _clean_float(page.locator(".nChange").inner_text())
                    chg_pct = _clean_float(page.locator(".percChange").inner_text())

                    if None in (o, h, l, c):
                        _log.warning(f"[{dhc_id}] Skipping unparseable row at index {i}: "
                                     f"o={o} h={h} l={l} c={c} raw_date={raw_date!r}")
                        continue

                    # chg / chg_pct may legitimately be None if TE doesn't render
                    # them for the very first visible point on the chart.
                    records.append((dt, o, h, l, c, None, chg, chg_pct))

                except Exception as e:
                    _log.warning(f"[{dhc_id}] Skipping point {i}: {e}")
                    continue
        finally:
            browser.close()

    return records