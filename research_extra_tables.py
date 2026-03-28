import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def print_columns(cur, table):
    cur.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}'")
    cols = cur.fetchall()
    print(f"--- {table} ---")
    for c in cols:
        print(f"  {c[0]} ({c[1]})")

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    print_columns(cur, 'question_bank')
    print_columns(cur, 'subsections')
    print_columns(cur, 'sections')
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
