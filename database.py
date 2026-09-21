import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration
DB_HOST = "localhost"
DB_PORT = "5432"
DB_NAME = "hostel_leave_db"
DB_USER = "postgres"
DB_PASSWORD = "K@a20112007"

def get_db_connection():
    """Establishes and returns a connection to hostel_leave_db with timeout protection."""
    connection = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        cursor_factory=RealDictCursor,
        connect_timeout=5,
        client_encoding="UTF8"
    )
    return connection