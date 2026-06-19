from app.db import db_connection


def batch_insert(dhc_id, data):
    """
    Upserts rows into tblDataHarvester keyed on (DH_DHC_RecordID, DH_TimeStamp),
    which matches the table's uq_dhcid_time unique constraint.

    Accepts two row shapes from fetchers:
      - 6-tuple (TV): (datetime, open, high, low, close, volume)
            -> DH_CloseChange / DH_CloseChangePct left untouched here;
               app/updater.py computes them afterward for these rows.
      - 8-tuple (TE): (datetime, open, high, low, close, volume, close_change, close_change_pct)
            -> close_change/pct come straight from the source and are written
               directly. Whether app/updater.py later overwrites these for a
               given config depends on DHC_LastSuccess (see app/updater.py).

    Both fetchers re-pull a trailing window of recent bars on every run, so
    existing rows in that window need to be refreshed (e.g. an "official"
    close replacing an intraday/partial one) rather than silently skipped by
    a plain INSERT hitting the unique constraint -- hence MERGE.

    Returns the number of rows attempted (not a distinct inserted/updated
    count -- SQL Server's MERGE doesn't cheaply expose that split via pyodbc).
    """
    if not data:
        return 0

    payload = []
    for row in data:
        if len(row) == 8:
            dt, o, h, l, c, v, chg, chg_pct = row
        elif len(row) == 6:
            dt, o, h, l, c, v = row
            chg, chg_pct = None, None
        else:
            raise ValueError(f"Unexpected row shape from fetcher: {row!r}")
        payload.append((dhc_id, dt, o, h, l, c, v, chg, chg_pct))

    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.fast_executemany = True
        cursor.executemany(
            """
            MERGE INTO tblDataHarvester AS target
            USING (VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)) AS src (
                DH_DHC_RecordID, DH_TimeStamp, DH_Open, DH_High, DH_Low, DH_Close,
                DH_Volume, DH_CloseChange, DH_CloseChangePct
            )
            ON target.DH_DHC_RecordID = src.DH_DHC_RecordID
               AND target.DH_TimeStamp = src.DH_TimeStamp
            WHEN MATCHED THEN
                UPDATE SET
                    DH_Open            = src.DH_Open,
                    DH_High            = src.DH_High,
                    DH_Low             = src.DH_Low,
                    DH_Close           = src.DH_Close,
                    DH_Volume          = src.DH_Volume,
                    DH_CloseChange     = COALESCE(src.DH_CloseChange, target.DH_CloseChange),
                    DH_CloseChangePct  = COALESCE(src.DH_CloseChangePct, target.DH_CloseChangePct)
            WHEN NOT MATCHED THEN
                INSERT (
                    DH_DHC_RecordID, DH_TimeStamp, DH_Open, DH_High, DH_Low, DH_Close,
                    DH_Volume, DH_CloseChange, DH_CloseChangePct
                )
                VALUES (
                    src.DH_DHC_RecordID, src.DH_TimeStamp, src.DH_Open, src.DH_High, src.DH_Low, src.DH_Close,
                    src.DH_Volume, src.DH_CloseChange, src.DH_CloseChangePct
                );
            """,
            payload,
        )
        conn.commit()

    return len(payload)