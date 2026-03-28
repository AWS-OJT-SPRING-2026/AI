import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    
    print("Adding classid column to books...")
    cur.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS classid INTEGER")
    
    print("Adding classid column to question_bank...")
    cur.execute("ALTER TABLE question_bank ADD COLUMN IF NOT EXISTS classid INTEGER")
    
    conn.commit()
    print("Success: Updated RDS schema.")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
