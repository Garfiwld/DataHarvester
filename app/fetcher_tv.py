import time
import logging
from tvDatafeed import TvDatafeed, Interval
from app.config import FETCH_INITIAL, FETCH_LIMIT, RETRY_BASE_DELAY

_log = logging.getLogger("DataHarvester")

tv = TvDatafeed()

INTERVAL_MAP = {
    "1":Interval.in_1_minute,
    "3":Interval.in_3_minute,
    "5":Interval.in_5_minute,
    "15":Interval.in_15_minute,
    "30":Interval.in_30_minute,
    "45":Interval.in_45_minute,
    "1H":Interval.in_1_hour,
    "2H":Interval.in_2_hour,
    "3H":Interval.in_3_hour,
    "4H":Interval.in_4_hour,
    "Day":Interval.in_daily,
    "Week":Interval.in_weekly,
    "Month":Interval.in_monthly
}


def fetch_data(dhc_id, symbol, exchange, interval, last_success, retry_max, limit=FETCH_LIMIT):
    tv_interval = INTERVAL_MAP.get(interval, Interval.in_daily)
    n_bars = FETCH_INITIAL if not last_success else limit

    for attempt in range(1, retry_max + 1):
        _log.info(f"[{dhc_id}] Fetching {symbol}/{exchange} {interval} (attempt {attempt}/{retry_max})")
        try:
            df = tv.get_hist(
                symbol=symbol,
                exchange=exchange,
                interval=tv_interval,
                n_bars=n_bars,
            )
        except Exception as e:
            _log.warning(f"[{dhc_id}] tvDatafeed error on attempt {attempt}: {e}")
            df = None

        if df is not None and not df.empty:
            df = df.reset_index()
            # Use vectorized conversion instead of iterrows (much faster)
            records = list(
                zip(
                    df["datetime"],
                    df["open"].astype(float),
                    df["high"].astype(float),
                    df["low"].astype(float),
                    df["close"].astype(float),
                    df["volume"].astype(float),
                )
            )
            _log.info(f"[{dhc_id}] Fetched {len(records)} bars for {symbol}")
            return records

        wait = RETRY_BASE_DELAY ** attempt
        _log.warning(f"[{dhc_id}] Empty result, retrying in {wait:.1f}s...")
        time.sleep(wait)

    _log.error(f"[{dhc_id}] All {retry_max} attempts failed for {symbol}")
    return []