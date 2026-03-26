import psycopg2
try:
    conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/edu_carre')
    cur = conn.cursor()
    cur.execute("SELECT studentid FROM students LIMIT 5")
    rows = cur.fetchall()
    print(f"Students: {rows}")
    cur.execute("SELECT studentid FROM submissions LIMIT 5")
    rows = cur.fetchall()
    print(f"Submissions students: {rows}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
