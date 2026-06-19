from app.db import db_connection

def batch_insert(dhc_id, data):
    if not data:
        return 0

    payload = []
    for row in data:
        if len(row) == 6:
            dt, o, h, l, c, v = row
            chg, chg_pct = None, None
        elif len(row) == 8:
            dt, o, h, l, c, v, chg, chg_pct = row
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
                    DH_Volume          = src.DH_Volume
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