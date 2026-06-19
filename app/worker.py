import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.db import db_connection
from app.fetcher_tv import fetch_data as fetch_data_tv
from app.fetcher_te import fetch_data as fetch_data_te
from app.loader import batch_insert
from app.logger import log
from app.config import MAX_WORKERS, RETRY_BASE_DELAY
from app.updater import run_updater

_log = logging.getLogger("DataHarvester")

FETCHERS = {
    "TV": fetch_data_tv,
    "TE": fetch_data_te,
}
DEFAULT_SOURCE = "TV"


def get_configs():
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                DHC_RecordID,
                DHC_Symbol,
                DHC_Exchange,
                DHC_Interval,
                DHC_LastSuccess,
                DHC_RetryMax,
                DHC_Source
            FROM tblDataHarvester_Config
            WHERE DHC_isActive = 1
            """
        )
        return cursor.fetchall()


def update_last_success(dhc_id):
    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE tblDataHarvester_Config SET DHC_LastSuccess = GETDATE() WHERE DHC_RecordID = ?",
            dhc_id,
        )
        conn.commit()


def process_symbol(cfg):
    dhc_id, symbol, exchange, interval, last_success, retry_max, source = cfg

    fetch_data = FETCHERS.get(source or DEFAULT_SOURCE)
    if fetch_data is None:
        log(dhc_id, "FAILED", f"Unknown DHC_Source '{source}' — no fetcher registered")
        return

    for attempt in range(1, retry_max + 1):
        try:
            data = fetch_data(dhc_id, symbol, exchange, interval, last_success, retry_max)

            if not data:
                raise ValueError("fetch_data returned empty — no data to insert")

            inserted = batch_insert(dhc_id, data)
            update_last_success(dhc_id)
            log(dhc_id, "SUCCESS", f"Inserted {inserted} rows")
            return  # done

        except Exception as e:
            log(dhc_id, "ERROR", f"Attempt {attempt}/{retry_max}: {e}")
            if attempt < retry_max:
                time.sleep(RETRY_BASE_DELAY ** attempt)

    log(dhc_id, "FAILED", "Max retries reached")


def run_worker():
    configs = get_configs()
    _log.info(f"Starting worker with {len(configs)} active symbols, {MAX_WORKERS} threads")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_symbol, cfg): cfg for cfg in configs}

        for future in as_completed(futures):
            cfg = futures[future]
            symbol = cfg[1]
            try:
                future.result()
            except Exception as e:
                _log.error(f"Unhandled crash for {symbol}: {e}")

    _log.info("Worker finished — running updater")
    run_updater(configs)