"""Fetch real data from TradingEconomics via app.fetcher_te and dump it to CSV.

Runs the actual Playwright scraper against the real tradingeconomics.com
(a browser window will open) but never touches the database — app.db and
app.loader are not imported at all. Results are written to a CSV file
instead of being inserted into tblDataHarvester.

Usage:
    python test_fetch_te_to_csv.py commodity/crude-oil
    python test_fetch_te_to_csv.py commodity/crude-oil --interval Week --out crude_oil.csv
"""
import argparse
import csv

from app.fetcher_te import fetch_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "symbol", nargs="?", default="commodity/crude-oil",
        help="TE symbol path, e.g. 'commodity/crude-oil' (default: %(default)s)",
    )
    parser.add_argument("--interval", default="Day", choices=["Day", "Week"])
    parser.add_argument("--retry-max", type=int, default=3)
    parser.add_argument("--out", default=None, help="CSV output path (default: <symbol>.csv)")
    args = parser.parse_args()

    out_path = args.out or (args.symbol.replace("/", "_") + ".csv")

    records = fetch_data(
        dhc_id="manual-test",
        symbol=args.symbol,
        exchange="",
        interval=args.interval,
        last_success=None,
        retry_max=args.retry_max,
    )

    if not records:
        print("No records fetched.")
        return

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["DateTime", "Open", "High", "Low", "Close", "Volume"])
        for dt, o, h, l, c, v in records:
            writer.writerow([dt.isoformat(), o, h, l, c, v])

    print(f"Wrote {len(records)} rows to {out_path}")


if __name__ == "__main__":
    main()
