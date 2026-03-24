from src.quiz_gen.quiz_generator import get_db_connection
import traceback

def check_data():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        print("Checking submission data...")
        
        cur.execute("SELECT * FROM submissions LIMIT 5")
        subs = cur.fetchall()
        print("Submissions:", subs)
        
        cur.execute("SELECT * FROM submission_answers LIMIT 5")
        ans = cur.fetchall()
        print("Answers:", ans)
        
        cur.close()
        conn.close()
    except Exception as e:
        traceback.print_exc()

if __name__ == "__main__":
    check_data()
