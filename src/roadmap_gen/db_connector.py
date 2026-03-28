import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """
    Tạo và trả về connection đến PostgreSQL based on environment variables.
    """
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USERNAME", "postgres"),
        password=os.getenv("DB_PASSWORD", "")
    )
    return conn
