import json
import os
import psycopg2
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

# Insert question_bank
cur.execute(
    "INSERT INTO question_bank (bank_name) VALUES (%s) RETURNING id",
    (qb.bank_name,)
)

bank_id = cur.fetchone()[0]

# Insert topics
for topic in qb.topics:
    cur.execute(
        """
        INSERT INTO topic (topic_name, bank_id)
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
            INSERT INTO question (question_text, image_url, explanation, difficulty_level, embedding, topic_id)
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
                INSERT INTO answer (content, label, is_correct, question_id)
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
