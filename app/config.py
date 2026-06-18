import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "driver": "{ODBC Driver 18 for SQL Server}",
    "server": os.getenv("DB_SERVER"),
    "database": os.getenv("DB_NAME"),
    "username": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
}

MAX_WORKERS = int(os.getenv("MAX_WORKERS", 2))
FETCH_INITIAL = int(os.getenv("FETCH_INITIAL", 2000))
FETCH_LIMIT = int(os.getenv("FETCH_LIMIT", 10))
RETRY_BASE_DELAY = float(os.getenv("RETRY_BASE_DELAY", 2.0))
