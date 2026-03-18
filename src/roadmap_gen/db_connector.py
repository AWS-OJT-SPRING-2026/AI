import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """
    Tạo và trả về connection đến PostgreSQL based on environment variables.
    """
    conn = psycopg2.connect(
        host="localhost",
        database=os.getenv("DATABASE_NAME"),
        user="postgres",
        password=os.getenv("POSTGRESQL_PASSWORD")
    )
    return conn
