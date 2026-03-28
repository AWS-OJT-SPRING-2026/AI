import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME"),
    user=os.getenv("DB_USERNAME"),
    password=os.getenv("DB_PASSWORD")
)
cur = conn.cursor()
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'question_bank'")
print("Columns in question_bank:", [r[0] for r in cur.fetchall()])
cur.execute("SELECT * FROM question_bank LIMIT 1")
print("First row in question_bank:", cur.fetchone())
cur.close()
conn.close()
