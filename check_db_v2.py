from src.quiz_gen.quiz_generator import get_db_connection
import traceback
import sys

def check_tables():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        print("--- Tables ---")
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            print(f"- {t}")
        
        needed_tables = ['questions', 'answers', 'question_content_blocks', 'content_blocks', 'lessons', 'subjects', 'question_bank']
        print("\n--- Needed Tables Check ---")
        for t in needed_tables:
            if t in tables:
                print(f"Table '{t}': EXISTS")
                cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}'")
                cols = [r[0] for r in cur.fetchall()]
                print(f"  Columns: {', '.join(cols)}")
            else:
                print(f"Table '{t}': MISSING")
                
        cur.close()
        conn.close()
    except Exception as e:
        print("Error checking tables:")
        traceback.print_exc()

if __name__ == "__main__":
    check_tables()
