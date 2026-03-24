from src.quiz_gen.quiz_generator import get_db_connection
import json

def export_tables():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    tables = [r[0] for r in cur.fetchall()]
    
    table_details = {}
    for t in tables:
        cur.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{t}'")
        cols = [r[0] for r in cur.fetchall()]
        table_details[t] = cols
        
    with open('db_details.json', 'w') as f:
        json.dump(table_details, f, indent=2)
    
    cur.close()
    conn.close()

if __name__ == "__main__":
    export_tables()
