import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USERNAME", "postgres"),
        password=os.getenv("DB_PASSWORD", "")
    )
    cur = conn.cursor()
    cur.execute("SELECT studentid FROM students LIMIT 5")
    rows = cur.fetchall()
    print(f"Students: {rows}")
    cur.execute("SELECT studentid FROM submissions LIMIT 5")
    rows = cur.fetchall()
    print(f"Submissions students: {rows}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
