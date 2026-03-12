import json
import os
import psycopg2
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

# Load JSON
with open("./app/extract_doc/output_doc.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Validate bằng Pydantic
book = Book.model_validate(data)

# Insert book
cur.execute(
    "INSERT INTO books (book_name) VALUES (%s) RETURNING id",
    (book.book_name,)
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
