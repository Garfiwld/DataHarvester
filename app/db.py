import pyodbc
from contextlib import contextmanager
from app.config import DB_CONFIG


def _build_conn_str():
    return (
        f"DRIVER={DB_CONFIG['driver']};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['username']};"
        f"PWD={DB_CONFIG['password']};"
        f"Encrypt=yes;TrustServerCertificate=yes;"
    )


def get_connection():
    return pyodbc.connect(_build_conn_str())


@contextmanager
def db_connection():
    """Context manager — auto-closes connection and cursor."""
    conn = get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
