import psycopg2
import os
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
    
    # Check current columns of roadmap_lessons
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'roadmap_lessons'")
    cols = [r[0] for r in cur.fetchall()]
    print(f"Current columns in roadmap_lessons: {cols}")
    
    if 'explain' in cols and 'explanation' not in cols:
        print("Renaming 'explain' to 'explanation'...")
        cur.execute("ALTER TABLE roadmap_lessons RENAME COLUMN explain TO explanation")
        conn.commit()
        print("Rename successful.")
    elif 'explanation' in cols:
        print("'explanation' column already exists.")
    else:
        print("Neither 'explain' nor 'explanation' found. Something is wrong.")
        
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
