from app.db import db_connection


def batch_insert(dhc_id, data):
    if not data:
        return 0

    payload = [(dhc_id, *row) for row in data]

    with db_connection() as conn:
        cursor = conn.cursor()
        cursor.fast_executemany = True
        cursor.executemany(
            """
            BEGIN TRY
                INSERT INTO tblDataHarvester (
                    DH_DHC_RecordID,
                    DH_TimeStamp,
                    DH_Open,
                    DH_High,
                    DH_Low,
                    DH_Close,
                    DH_Volume
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            END TRY
            BEGIN CATCH
            END CATCH
            """,
            payload,
        )
        conn.commit()

    return len(payload)