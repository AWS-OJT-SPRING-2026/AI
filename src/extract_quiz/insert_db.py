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

# Insert question_bank (kèm subject_id)
cur.execute(
    "INSERT INTO question_bank (bank_name, subject_id) VALUES (%s, %s) RETURNING id",
    (qb.bank_name, subject_id)
)

bank_id = cur.fetchone()[0]

# Insert questions
for question in qb.questions:
    
    # Normalize difficulty level: "dễ" -> "1", "trung bình" -> "2", "khó" -> "3"
    diff = str(question.difficulty_level).lower().strip()
    if "dễ" in diff or diff == "1":
        normalized_diff = "1"
    elif "khó" in diff or diff == "3":
        normalized_diff = "3"
    else:
        normalized_diff = "2" # default to medium
        
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
            normalized_diff,
            question.vector,
            bank_id
        )
    )
    question_id = cur.fetchone()[0]
    
    # Insert keywords link if present
    if hasattr(question, "keywords") and question.keywords:
        for kw in question.keywords:
            kw_clean = kw.strip()
            if not kw_clean:
                continue
            
            # Check if keyword exists
            cur.execute("SELECT id FROM keywords WHERE keyword = %s", (kw_clean,))
            kw_row = cur.fetchone()
            if kw_row:
                keyword_id = kw_row[0]
            else:
                cur.execute("INSERT INTO keywords (keyword) VALUES (%s) RETURNING id", (kw_clean,))
                keyword_id = cur.fetchone()[0]
            
            # Link to question (lesson_id is NULL here since it's from a generic quiz bank)
            cur.execute(
                "INSERT INTO questions_link (question_id, keyword_id) VALUES (%s, %s)",
                (question_id, keyword_id)
            )
    
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
