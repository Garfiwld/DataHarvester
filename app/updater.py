"""
app/updater.py
UPDATE DH_CloseChange และ DH_CloseChangePct
- last_success IS NULL  → UPDATE ทั้งหมดของ symbol นั้น (initial fetch 1,000 แถว)
- last_success IS NOT NULL → UPDATE เฉพาะ 10 แถวล่าสุด
"""

import pandas as pd
from app.db import db_connection


def run_updater(configs):
    # แยก symbol ที่เป็น initial (last_success IS NULL) กับปกติ
    initial_ids = [cfg[0] for cfg in configs if not cfg[4]]
    normal_ids  = [cfg[0] for cfg in configs if cfg[4]]

    rows = []

    with db_connection() as conn:

        # --- Initial: ดึงทั้งหมด + 1 แถวก่อนหน้าเพื่อคำนวณแถวแรก ---
        if initial_ids:
            placeholders = ",".join("?" * len(initial_ids))
            df_init = pd.read_sql(
                f"""
                SELECT DH_RecordID, DH_DHC_RecordID, DH_TimeStamp, DH_Close
                FROM (
                    SELECT *,
                        ROW_NUMBER() OVER (
                            PARTITION BY DH_DHC_RecordID
                            ORDER BY DH_TimeStamp ASC
                        ) AS rn
                    FROM tblDataHarvester
                    WHERE DH_DHC_RecordID IN ({placeholders})
                ) x
                ORDER BY DH_DHC_RecordID, DH_TimeStamp
                """,
                conn,
                params=initial_ids,
            )
            rows.append(("all", df_init))

        # --- Normal: ดึง 11 แถวล่าสุด (10 + 1 เพื่อ shift) ---
        if normal_ids:
            placeholders = ",".join("?" * len(normal_ids))
            df_normal = pd.read_sql(
                f"""
                SELECT DH_RecordID, DH_DHC_RecordID, DH_TimeStamp, DH_Close
                FROM (
                    SELECT *,
                        ROW_NUMBER() OVER (
                            PARTITION BY DH_DHC_RecordID
                            ORDER BY DH_TimeStamp DESC
                        ) AS rn
                    FROM tblDataHarvester
                    WHERE DH_DHC_RecordID IN ({placeholders})
                ) x
                WHERE rn <= 11
                ORDER BY DH_DHC_RecordID, DH_TimeStamp
                """,
                conn,
                params=normal_ids,
            )
            rows.append(("normal", df_normal))

        # --- คำนวณและ UPDATE ---
        payload = []
        for mode, df in rows:
            if df.empty:
                continue

            df["prev_close"]        = df.groupby("DH_DHC_RecordID")["DH_Close"].shift(1)
            df["DH_CloseChange"]    = (df["DH_Close"] - df["prev_close"]).round(6)
            df["DH_CloseChangePct"] = ((df["DH_Close"] - df["prev_close"]) / df["prev_close"] * 100).round(6)
            df = df.dropna(subset=["DH_CloseChange", "DH_CloseChangePct"])

            if mode == "normal":
                df = df.groupby("DH_DHC_RecordID").tail(10)

            payload += [
                (row["DH_CloseChange"], row["DH_CloseChangePct"], row["DH_RecordID"])
                for _, row in df.iterrows()
            ]

        if not payload:
            return

        cursor = conn.cursor()
        cursor.fast_executemany = True
        cursor.executemany(
            """
            UPDATE tblDataHarvester
            SET DH_CloseChange    = ?,
                DH_CloseChangePct = ?
            WHERE DH_RecordID = ?
            """,
            payload,
        )
        conn.commit()
        print(f"อัปเดต {len(payload)} แถว เสร็จสิ้น")