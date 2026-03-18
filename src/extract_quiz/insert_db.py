import json
import os
import sys
import psycopg2
from datetime import datetime
from src.models.schema_question_bank import QuestionBank
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Connect database
conn = psycopg2.connect(
    host="localhost",
    database=os.getenv("DATABASE_NAME"),
    user="postgres",
    password=os.getenv("POSTGRESQL_PASSWORD")
)

cur = conn.cursor()

# Lấy User ID từ người dùng
userid_input = input("Nhập User ID của Giáo viên (userid): ").strip()
if not userid_input.isdigit():
    print("[LỖI] User ID không hợp lệ.")
    sys.exit(1)
userid = int(userid_input)

# Lấy tên môn học từ người dùng
subject_name = input("Nhập tên môn học (subject_name): ").strip()
if not subject_name:
    print("[LỖI] Tên môn học không được để trống.")
    sys.exit(1)

# Kiểm tra subject đã tồn tại chưa, nếu chưa thì tạo mới
cur.execute(
    "SELECT subject_id FROM subjects WHERE subject_name = %s",
    (subject_name,)
)
row = cur.fetchone()
if row:
    subject_id = row[0]
    print(f"Đã tìm thấy môn học '{subject_name}' với subject_id = {subject_id}")
else:
    now = datetime.now()
    cur.execute(
        """
        INSERT INTO subjects (subject_name, created_at, updated_at)
        VALUES (%s, %s, %s)
        RETURNING subject_id
        """,
        (subject_name, now, now)
    )
    subject_id = cur.fetchone()[0]
    print(f"Đã tạo môn học mới '{subject_name}' với subject_id = {subject_id}")

# Kiểm tra giáo viên có tồn tại, nếu không có thì cảnh báo và tùy chọn tạo (ở đây tạo tạm)
cur.execute("SELECT userid FROM users WHERE userid = %s", (userid,))
if not cur.fetchone():
    print(f"[CẢNH BÁO] User ID {userid} chưa có trong bảng users. Đang thêm...")
    cur.execute("INSERT INTO users (userid, roleid) VALUES (%s, 2)", (userid,))

cur.execute("SELECT teacherid FROM teachers WHERE userid = %s", (userid,))
if not cur.fetchone():
    cur.execute("INSERT INTO teachers (teacherid, userid) VALUES (%s, %s)", (userid, userid))


# Load JSON
with open("./src/extract_quiz/output_questions.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Sinh embedding cho câu hỏi nếu JSON chưa có
for question in data.get("questions", []):
    if "vector" not in question:
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=question["question_text"]
        )
        question["vector"] = response.data[0].embedding

# Validate bằng Pydantic
qb = QuestionBank.model_validate(data)

# Tìm question_bank của giáo viên cho môn học này
cur.execute(
    "SELECT id FROM question_bank WHERE userid = %s AND subject_id = %s",
    (userid, subject_id)
)
qb_row = cur.fetchone()
if qb_row:
    bank_id = qb_row[0]
    print(f"Đã sử dụng ngân hàng câu hỏi có sẵn (bank_id={bank_id}) cho User {userid} - Môn {subject_name}")
else:
    try:
        cur.execute(
            "INSERT INTO question_bank (bank_name, userid, subject_id) VALUES (%s, %s, %s) RETURNING id",
            (qb.bank_name if qb.bank_name else f"Question Bank {subject_name}", userid, subject_id)
        )
        bank_id = cur.fetchone()[0]
        print(f"Đã tạo ngân hàng câu hỏi mới (bank_id={bank_id}) cho môn {subject_name}")
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Lỗi tạo question bank: {e}")
    
# Insert questions
for question in qb.questions:
    cur.execute(
        """
        INSERT INTO questions (question_text, image_url, explanation, difficulty_level, embedding, bank_id)
        VALUES (%s,%s,%s,%s,%s,%s)
        RETURNING id
        """,
        (
            question.question_text,
            question.image_url,
            question.explanation,
            question.difficulty_level,
            question.vector,
            bank_id
        )
    )
    question_id = cur.fetchone()[0]
    
    # Insert answers
    for answer in question.answers:
        cur.execute(
            """
            INSERT INTO answers (content, label, is_correct, question_id)
            VALUES (%s,%s,%s,%s)
            RETURNING id
            """,
            (
                answer.content,
                answer.label,
                answer.is_correct,
                question_id
            )
        )

conn.commit()

cur.close()
conn.close()

print("Insert and embed quiz data completed successfully")
