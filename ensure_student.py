import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host="localhost",
        database=os.getenv("DATABASE_NAME", "postgres"),
        user="postgres",
        password=os.getenv("POSTGRESQL_PASSWORD", "tuandang271")
    )
    cur = conn.cursor()
    # Check students table columns
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'students'")
    cols = [r[0] for r in cur.fetchall()]
    print(f"Columns: {cols}")
    
    # Try to insert a test student if not exists
    # Based on the error log, the table is "students" and the key is "studentid"
    # Let's see if 'name' or 'full_name' exists
    name_col = 'full_name' if 'full_name' in cols else 'name' if 'name' in cols else None
    
    if name_col:
        cur.execute(f"INSERT INTO students (studentid, {name_col}) VALUES (1, 'Test Student') ON CONFLICT DO NOTHING")
    else:
        cur.execute("INSERT INTO students (studentid) VALUES (1) ON CONFLICT DO NOTHING")
        
    conn.commit()
    print("Test student 1 ensured.")
    
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
