import logging
from app.db import db_connection

# Console logger for debugging
_console = logging.getLogger("DataHarvester")
if not _console.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    _console.addHandler(_handler)
    _console.setLevel(logging.INFO)


def log(dhc_id, status, message):
    """Write log to DB and also print to console."""
    _console.info(f"[{dhc_id}] {status}: {message}")
    try:
        with db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tblDataHarvester_Log (
                    DHL_DHC_RecordID,
                    DHL_Status,
                    DHL_Message
                )
                VALUES (?, ?, ?)
                """,
                str(dhc_id), status, message[:2000],  # guard against oversized messages
            )
            conn.commit()
    except Exception as e:
        # Don't let logging errors crash the main process
        _console.error(f"Failed to write log to DB: {e}")
