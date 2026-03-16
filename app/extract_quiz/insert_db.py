import json
import os
import sys
import psycopg2
from datetime import datetime
from app.models.schema_question_bank import QuestionBank
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
with open("./app/extract_quiz/output_questions.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Sinh embedding cho câu hỏi nếu JSON chưa có
for topic in data.get("topics", []):
    for question in topic.get("questions", []):
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

# Insert topics
for topic in qb.topics:
    cur.execute(
        """
        INSERT INTO topics (topic_name, bank_id)
        VALUES (%s,%s)
        RETURNING id
        """,
        (topic.topic_name, bank_id)
    )
    topic_id = cur.fetchone()[0]
    
    # Insert questions
    for question in topic.questions:
        cur.execute(
            """
            INSERT INTO questions (question_text, image_url, explanation, difficulty_level, embedding, topic_id)
            VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                question.question_text,
                question.image_url,
                question.explanation,
                question.difficulty_level,
                question.vector,
                topic_id
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
