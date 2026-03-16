import json
import os
import sys
import psycopg2
from datetime import datetime
from app.models.schema import Book
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
with open("./app/extract_doc/output_doc.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Validate bằng Pydantic
book = Book.model_validate(data)

# Insert book (kèm subject_id)
cur.execute(
    "INSERT INTO books (book_name, subject_id) VALUES (%s, %s) RETURNING id",
    (book.book_name, subject_id)
)

book_id = cur.fetchone()[0]

# Insert chapters
for chapter in book.chapters:

    cur.execute(
        """
        INSERT INTO chapters (book_id, chapter_number, title)
        VALUES (%s,%s,%s)
        RETURNING id
        """,
        (book_id, chapter.chapter_number, chapter.title)
    )

    chapter_id = cur.fetchone()[0]

    # Insert lessons
    for lesson in chapter.lessons:

        cur.execute(
            """
            INSERT INTO lessons (chapter_id, lesson_number, title)
            VALUES (%s,%s,%s)
            RETURNING id
            """,
            (chapter_id, lesson.lesson_number, lesson.title)
        )

        lesson_id = cur.fetchone()[0]

        # Insert sections
        for section in lesson.section:

            cur.execute(
                """
                INSERT INTO sections (lesson_id, section_number, section_title)
                VALUES (%s,%s,%s)
                RETURNING id
                """,
                (
                    lesson_id,
                    section.section_number,
                    section.section_title
                )
            )

            section_id = cur.fetchone()[0]

            if section.subsections:

                # Insert subsections
                for sub in section.subsections:

                    cur.execute(
                        """
                        INSERT INTO subsections
                        (section_id, subsection_number, subsection_title)
                        VALUES (%s,%s,%s)
                        RETURNING id
                        """,
                        (
                            section_id,
                            sub.subsection_number,
                            sub.subsection_title
                        )
                    )

                    subsection_id = cur.fetchone()[0]

                    # Insert content blocks
                    if sub.content_blocks:

                        for block in sub.content_blocks:

                            response = client.embeddings.create(
                                model="text-embedding-3-large",
                                input=block
                            )
                            embedding = response.data[0].embedding

                            cur.execute(
                                """
                                INSERT INTO content_blocks
                                (subsection_id, content, embedding)
                                VALUES (%s,%s,%s)
                                """,
                                (subsection_id, block, embedding)
                            )

conn.commit()

cur.close()
conn.close()

print("Insert and embed completed successfully")
