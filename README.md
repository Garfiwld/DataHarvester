# DataHarvester

DataHarvester is a Python worker that periodically pulls OHLCV (open/high/low/close/volume) market data from external sources, writes it into a SQL Server database, and keeps derived columns (close change, close change %) up to date.

## Overview

The pipeline works like this:

1. **Load active configs** — read all rows from `tblDataHarvester_Config` where `DHC_isActive = 1`. Each row describes one symbol/exchange/interval combination to track.
2. **Fetch data** — for each config, call the matching fetcher (TradingView or TradingEconomics) to pull new bars.
3. **Load data** — upsert the fetched bars into `tblDataHarvester` via a `MERGE` statement, so re-runs don't create duplicates.
4. **Update last success** — stamp `DHC_LastSuccess` so the next run knows to fetch only recent bars instead of a full history.
5. **Run the updater** — recompute `DH_CloseChange` and `DH_CloseChangePct` for any rows that need it.

All of this is orchestrated by a thread pool so multiple symbols are fetched concurrently.

## Project Structure

```
DataHarvester/
├── main.py                # Entry point — calls run_worker()
├── run.bat                # Windows launcher (cd + python main.py)
├── Database.txt           # SQL DDL for tables/view used by the project
├── .env                   # DB credentials and tunables (not committed)
└── app/
    ├── config.py           # Loads .env into typed settings (DB_CONFIG, MAX_WORKERS, etc.)
    ├── db.py               # pyodbc connection helper + context manager
    ├── worker.py           # Orchestrator: fetch → load → mark success → update
    ├── fetcher_tv.py       # Fetcher backed by tvDatafeed (TradingView)
    ├── fetcher_te.py       # Fetcher backed by Playwright scraping (TradingEconomics)
    ├── loader.py           # Upserts fetched rows into tblDataHarvester
    ├── updater.py          # Recalculates DH_CloseChange / DH_CloseChangePct
    └── logger.py           # Writes run logs to tblDataHarvester_Log + console
```

## Database Schema

Three tables and one view, defined in `Database.txt`:

- **`tblDataHarvester_Config`** — one row per symbol to track (symbol, exchange, interval, active flag, retry count, last success timestamp, data source).
- **`tblDataHarvester`** — the actual OHLCV bars, keyed uniquely by `(DH_DHC_RecordID, DH_TimeStamp)`.
- **`tblDataHarvester_Log`** — append-only log of each fetch attempt's status and message.
- **`viwDataHarvester`** — a reporting view that joins config + data, and converts prices to THB using a reference USD/THB row.

## Data Sources

| Source | Key | Mechanism |
|--------|-----|-----------|
| TradingView | `TV` (default) | `tvDatafeed` library, `tv.get_hist(...)` |
| TradingEconomics | `TE` | Headless-browser scraping via Playwright |

The source used per symbol is set in `DHC_Source` on the config table; `worker.py` dispatches to the right fetcher via the `FETCHERS` dict.

## Fetch Behavior

- **First run for a symbol** (`DHC_LastSuccess IS NULL`): fetches a large initial history (`FETCH_INITIAL`, default 2000 bars).
- **Subsequent runs**: fetches only the most recent bars (`FETCH_LIMIT`, default 10).
- Each fetch attempt retries up to `DHC_RetryMax` times with exponential backoff (`RETRY_BASE_DELAY ** attempt`).

## Configuration

Environment variables (loaded via `.env` and `python-dotenv`):

| Variable | Purpose | Default |
|----------|---------|---------|
| `DB_SERVER` | SQL Server host | — |
| `DB_NAME` | Database name | — |
| `DB_USER` | SQL Server username | — |
| `DB_PASSWORD` | SQL Server password | — |
| `MAX_WORKERS` | Thread pool size for concurrent fetching | `2` |
| `FETCH_INITIAL` | Bars to fetch on first run per symbol | `2000` |
| `FETCH_LIMIT` | Bars to fetch on subsequent runs | `10` |
| `RETRY_BASE_DELAY` | Base seconds for exponential backoff | `2.0` |

## Running

```bash
python main.py
```

On Windows, `run.bat` changes into the project directory and runs the same entry point:

```bat
cd /d C:\Work\DataHarvester
python main.py
```

## Requirements

- Python 3.x
- SQL Server with ODBC Driver 18
- Python packages: `pyodbc`, `python-dotenv`, `pandas`, `tvDatafeed`, `playwright` (plus a Playwright browser install for the TE fetcher)

## Logging

Every fetch attempt logs to both the console and `tblDataHarvester_Log` via `app/logger.py`, with one of three statuses: `SUCCESS`, `ERROR` (per retry attempt), or `FAILED` (after exhausting retries).
