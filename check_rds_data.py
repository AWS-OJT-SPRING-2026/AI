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
    
    print("\n--- Checking Books ---")
    cur.execute("SELECT id, book_name, subject_id FROM books")
    for row in cur.fetchall():
        print(f"  {row}")

    print("\n--- Checking Chapters ---")
    cur.execute("SELECT id, title, book_id FROM chapters")
    for row in cur.fetchall():
        print(f"  {row}")

    print("\n--- Checking Lessons ---")
    cur.execute("SELECT id, title, chapter_id FROM lessons")
    # Only print first 5 if too many
    rows = cur.fetchall()
    for row in rows[:5]:
        print(f"  {row}")
    if len(rows) > 5:
        print(f"  ... and {len(rows)-5} more")

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
