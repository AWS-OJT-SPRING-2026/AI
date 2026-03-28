import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def inspect_table(cur, table_name):
    print(f"\n--- Columns in {table_name} ---")
    cur.execute(f"SELECT table_schema, column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY table_schema, ordinal_position")
    for row in cur.fetchall():
        print(f"  {row[0]}.{row[1]} ({row[2]})")

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD")
    )
    cur = conn.cursor()
    
    with open("schema_info.txt", "w", encoding="utf-8") as f:
        # Also list tables
        f.write("--- Existing Tables ---\n")
        cur.execute("SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('information_schema', 'pg_catalog')")
        for row in cur.fetchall():
            f.write(f"  {row[0]}.{row[1]}\n")

        tables = [
            'subjects', 'lessons', 'chapters', 'submissions', 'submission_answers', 
            'books', 'users', 'students', 'questions', 'answers', 
            'roadmaps', 'roadmap_chapters', 'roadmap_lessons', 'question_bank',
            'classrooms', 'class_member'
        ]
        for table in tables:
            f.write(f"\n--- Columns in {table} ---\n")
            cur.execute(f"SELECT table_schema, column_name, data_type FROM information_schema.columns WHERE table_name = '{table}' ORDER BY table_schema, ordinal_position")
            for row in cur.fetchall():
                f.write(f"  {row[0]}.{row[1]} ({row[2]})\n")
    
    print("Schema info written to schema_info.txt")
        
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
