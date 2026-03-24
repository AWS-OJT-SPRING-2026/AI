import os
import psycopg2
from typing import Dict, Any, List
from openai import OpenAI
from src.quiz_gen.quiz_generator import get_db_connection
from src.models.schema import Book
from src.models.schema_question_bank import QuestionBank

class DBService:
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def insert_book(self, book: Book, subject_id: int):
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # Insert book
            cur.execute(
                "INSERT INTO books (book_name, subject_id) VALUES (%s, %s) RETURNING id",
                (book.book_name, subject_id)
            )
            book_id = cur.fetchone()[0]

            for chapter in book.chapters:
                cur.execute(
                    "INSERT INTO chapters (book_id, chapter_number, title) VALUES (%s, %s, %s) RETURNING id",
                    (book_id, chapter.chapter_number, chapter.title)
                )
                chapter_id = cur.fetchone()[0]

                for lesson in chapter.lessons:
                    cur.execute(
                        "INSERT INTO lessons (chapter_id, lesson_number, title) VALUES (%s, %s, %s) RETURNING id",
                        (chapter_id, lesson.lesson_number, lesson.title)
                    )
                    lesson_id = cur.fetchone()[0]

                    for section in lesson.section:
                        cur.execute(
                            "INSERT INTO sections (lesson_id, section_number, section_title) VALUES (%s, %s, %s) RETURNING id",
                            (lesson_id, section.section_number, section.section_title)
                        )
                        section_id = cur.fetchone()[0]

                        if section.content:
                            cur.execute(
                                "INSERT INTO subsections (section_id, subsection_number, subsection_title) VALUES (%s, %s, %s) RETURNING id",
                                (section_id, "1", None)
                            )
                            subsection_id = cur.fetchone()[0]

                            blocks = [b.strip() for b in section.content.split('\n\n') if b.strip()]
                            for block in blocks:
                                # Generate embedding
                                response = self.openai_client.embeddings.create(
                                    model="text-embedding-3-large",
                                    input=block
                                )
                                embedding = response.data[0].embedding

                                cur.execute(
                                    "INSERT INTO content_blocks (subsection_id, content, embedding) VALUES (%s, %s, %s)",
                                    (subsection_id, block, embedding)
                                )
            conn.commit()
            return book_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    def insert_quiz(self, data: Dict[str, Any], subject_id: int, userid: int = 1):
        # Validate data
        qb = QuestionBank.model_validate(data)
        
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # 1. Ensure user and question bank exist
            cur.execute("SELECT userid FROM users WHERE userid = %s", (userid,))
            if not cur.fetchone():
                cur.execute("INSERT INTO users (userid, roleid) VALUES (%s, 2)", (userid, )) # roleid 2 for teacher
            
            # Find or create question bank
            cur.execute("SELECT id FROM question_bank WHERE userid = %s AND subject_id = %s", (userid, subject_id))
            row = cur.fetchone()
            if row:
                bank_id = row[0]
            else:
                cur.execute(
                    "INSERT INTO question_bank (bank_name, userid, subject_id) VALUES (%s, %s, %s) RETURNING id",
                    (qb.bank_name or f"Bank - {subject_id}", userid, subject_id)
                )
                bank_id = cur.fetchone()[0]

            # 2. Insert questions
            for q in qb.questions:
                # Generate embedding if missing
                if not getattr(q, 'vector', None):
                    response = self.openai_client.embeddings.create(
                        model="text-embedding-3-large",
                        input=q.question_text
                    )
                    q.vector = response.data[0].embedding

                cur.execute(
                    """
                    INSERT INTO questions (question_text, image_url, explanation, difficulty_level, embedding, bank_id)
                    VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
                    """,
                    (q.question_text, q.image_url, q.explanation, q.difficulty_level, q.vector, bank_id)
                )
                question_id = cur.fetchone()[0]

                for ans in q.answers:
                    cur.execute(
                        "INSERT INTO answers (content, label, is_correct, question_id) VALUES (%s, %s, %s, %s)",
                        (ans.content, ans.label, ans.is_correct, question_id)
                    )
            
            conn.commit()
            return bank_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()
