import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Local development fallback settings
LOCAL_DB_HOST = "localhost"
LOCAL_DB_PORT = "5432"
LOCAL_DB_NAME = "hostel_leave_db"
LOCAL_DB_USER = "postgres"
LOCAL_DB_PASSWORD = "K@a20112007"

def get_db_connection():
    """
    Establishes and returns a connection to the PostgreSQL database.
    Prioritizes DATABASE_URL (for Render / Neon Cloud) and falls back
    to local credentials for offline development.
    """
    database_url = os.environ.get("DATABASE_URL")
    
    if database_url:
        # Running on Render / Cloud (Connecting to Neon PostgreSQL)
        return psycopg2.connect(
            database_url,
            cursor_factory=RealDictCursor,
            connect_timeout=10,
            sslmode="require"
        )
    else:
        # Running locally on your PC
        return psycopg2.connect(
            host=LOCAL_DB_HOST,
            port=LOCAL_DB_PORT,
            database=LOCAL_DB_NAME,
            user=LOCAL_DB_USER,
            password=LOCAL_DB_PASSWORD,
            cursor_factory=RealDictCursor,
            connect_timeout=5,
            client_encoding="UTF8"
        )