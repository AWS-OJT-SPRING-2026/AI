import os
import psycopg2
from typing import Dict, Any, List, Optional
from openai import OpenAI
from src.quiz_gen.quiz_generator import get_db_connection
from src.models.schema import Book
from src.models.schema_question_bank import QuestionBank

class DBService:
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _books_has_user_id_column(self, cur) -> bool:
        """Return True when books.user_id exists in current DB schema."""
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'books'
              AND column_name = 'user_id'
            LIMIT 1
            """
        )
        return cur.fetchone() is not None

    def insert_book(self, book: Book, subject_id: int, user_id: Optional[int] = None):
        """
        Insert a Book (theory document) into the `books` table and its nested structure.
        Now supports the `user_id` column to track the creator.
        
        Returns the new book ID.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # Support both new schema (with user_id) and legacy schema (without user_id).
            if self._books_has_user_id_column(cur):
                cur.execute(
                    "INSERT INTO books (book_name, subject_id, user_id) VALUES (%s, %s, %s) RETURNING id",
                    (book.book_name, subject_id, user_id)
                )
            else:
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

                        if section.subsections:
                            for sub in section.subsections:
                                cur.execute(
                                    "INSERT INTO subsections (section_id, subsection_number, subsection_title) VALUES (%s, %s, %s) RETURNING id",
                                    (section_id, sub.subsection_number, sub.subsection_title)
                                )
                                subsection_id = cur.fetchone()[0]
                                for block in (sub.content_blocks or []):
                                    block = block.strip()
                                    if not block:
                                        continue
                                    response = self.openai_client.embeddings.create(
                                        model="text-embedding-3-large",
                                        input=block
                                    )
                                    embedding = response.data[0].embedding
                                    cur.execute(
                                        "INSERT INTO content_blocks (subsection_id, content, embedding) VALUES (%s, %s, %s)",
                                        (subsection_id, block, embedding)
                                    )
                        elif section.content:
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
        """
        Insert a Question Bank into the `question_bank` table.
        Always creates a NEW record (personal repository for the teacher).
        
        Returns the new bank ID.
        """
        # Validate data
        qb = QuestionBank.model_validate(data)
        
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            # 1. Ensure user exists
            cur.execute("SELECT userid FROM users WHERE userid = %s", (userid,))
            if not cur.fetchone():
                cur.execute("INSERT INTO users (userid, roleid) VALUES (%s, 2)", (userid, )) # roleid 2 for teacher
            
            # 2. Always create a NEW question bank record (personal repository)
            cur.execute(
                "INSERT INTO question_bank (bank_name, userid, subject_id) VALUES (%s, %s, %s) RETURNING id",
                (qb.bank_name or f"Bank - {subject_id}", userid, subject_id)
            )
            bank_id = cur.fetchone()[0]

            # 3. Insert questions
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
                    INSERT INTO questions (question_text, image_url, explanation, difficulty_level, embedding, bank_id, is_ai)
                    VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                    """,
                    (q.question_text, q.image_url, q.explanation, q.difficulty_level, q.vector, bank_id, False)
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

    def upsert_classroom_material(
        self,
        class_id: int,
        material_type: str,
        book_id: Optional[int],
        question_bank_id: Optional[int],
        assigned_by_user_id: int,
    ) -> int:
        """
        Insert a NEW record into `classroom_materials` table.

        NOTE:
        - A classroom can have multiple documents of the same type.
        - This method intentionally does NOT update existing rows.

        Returns the classroom_material ID.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO classroom_materials (class_id, type, book_id, question_bank_id, assigned_by_user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (class_id, material_type, book_id, question_bank_id, assigned_by_user_id)
            )
            material_id = cur.fetchone()[0]

            conn.commit()
            return material_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    def upload_document_transaction(
        self,
        file_path: str,
        class_id: int,
        subject_id: int,
        doc_type: str,
        user_id: int,
        extraction_service,
    ) -> Dict[str, Any]:
        """
        Complete 3-step upload transaction:
        
        1. Extract document content from file (theory or question).
        2. Save to personal repository (books or question_bank).
        3. Distribute to classroom via classroom_materials (insert-only).

        All database operations share a single connection/transaction.
        On any error, ALL changes are rolled back.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            # ═══════════ STEP 1: Extract content from uploaded file ═══════════
            if doc_type == "THEORY":
                extracted_data = extraction_service.extract_theory(file_path)
            elif doc_type == "QUESTION":
                extracted_data = extraction_service.extract_quiz(file_path)
            else:
                raise ValueError(f"Invalid doc_type: {doc_type}. Must be 'THEORY' or 'QUESTION'.")

            # ═══════════ STEP 2: Save to personal repository ═══════════
            if doc_type == "THEORY":
                record_id = self._insert_book_in_tx(cur, extracted_data, subject_id, user_id)
                book_id = record_id
                question_bank_id = None
            else:  # QUESTION
                record_id = self._insert_quiz_in_tx(cur, extracted_data, subject_id, user_id)
                book_id = None
                question_bank_id = record_id

            # ═══════════ STEP 3: Distribute to classroom (insert a new row) ═══════════
            material_id = self._insert_classroom_material_in_tx(
                cur, class_id, doc_type, book_id, question_bank_id, user_id
            )

            # ═══════════ COMMIT all changes ═══════════
            conn.commit()

            return {
                "status": "success",
                "type": doc_type,
                "record_id": record_id,
                "classroom_material_id": material_id,
                "class_id": class_id,
                "subject_id": subject_id,
                "assigned_by": user_id,
            }

        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cur.close()
            conn.close()

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers: execute within an EXISTING transaction (cursor)
    # ──────────────────────────────────────────────────────────────────────────

    def _insert_book_in_tx(self, cur, book: Book, subject_id: int, user_id: int) -> int:
        """Insert a Book (theory) within an existing DB transaction."""
        # Support both new schema (with user_id) and legacy schema (without user_id).
        if self._books_has_user_id_column(cur):
            cur.execute(
                "INSERT INTO books (book_name, subject_id, user_id) VALUES (%s, %s, %s) RETURNING id",
                (book.book_name, subject_id, user_id)
            )
        else:
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

                    if section.subsections:
                        for sub in section.subsections:
                            cur.execute(
                                "INSERT INTO subsections (section_id, subsection_number, subsection_title) VALUES (%s, %s, %s) RETURNING id",
                                (section_id, sub.subsection_number, sub.subsection_title)
                            )
                            subsection_id = cur.fetchone()[0]
                            for block in (sub.content_blocks or []):
                                block = block.strip()
                                if not block:
                                    continue
                                response = self.openai_client.embeddings.create(
                                    model="text-embedding-3-large",
                                    input=block
                                )
                                embedding = response.data[0].embedding
                                cur.execute(
                                    "INSERT INTO content_blocks (subsection_id, content, embedding) VALUES (%s, %s, %s)",
                                    (subsection_id, block, embedding)
                                )
                    elif section.content:
                        cur.execute(
                            "INSERT INTO subsections (section_id, subsection_number, subsection_title) VALUES (%s, %s, %s) RETURNING id",
                            (section_id, "1", None)
                        )
                        subsection_id = cur.fetchone()[0]

                        blocks = [b.strip() for b in section.content.split('\n\n') if b.strip()]
                        for block in blocks:
                            response = self.openai_client.embeddings.create(
                                model="text-embedding-3-large",
                                input=block
                            )
                            embedding = response.data[0].embedding
                            cur.execute(
                                "INSERT INTO content_blocks (subsection_id, content, embedding) VALUES (%s, %s, %s)",
                                (subsection_id, block, embedding)
                            )
        return book_id

    def _insert_quiz_in_tx(self, cur, data: Dict[str, Any], subject_id: int, userid: int) -> int:
        """Insert a Question Bank within an existing DB transaction."""
        qb = QuestionBank.model_validate(data)

        # Ensure user exists
        cur.execute("SELECT userid FROM users WHERE userid = %s", (userid,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (userid, roleid) VALUES (%s, 2)", (userid,))

        # Always create a NEW question bank record
        cur.execute(
            "INSERT INTO question_bank (bank_name, userid, subject_id) VALUES (%s, %s, %s) RETURNING id",
            (qb.bank_name or f"Bank - {subject_id}", userid, subject_id)
        )
        bank_id = cur.fetchone()[0]

        # Insert questions
        for q in qb.questions:
            if not getattr(q, 'vector', None):
                response = self.openai_client.embeddings.create(
                    model="text-embedding-3-large",
                    input=q.question_text
                )
                q.vector = response.data[0].embedding

            cur.execute(
                """
                INSERT INTO questions (question_text, image_url, explanation, difficulty_level, embedding, bank_id, is_ai)
                VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (q.question_text, q.image_url, q.explanation, q.difficulty_level, q.vector, bank_id, False)
            )
            question_id = cur.fetchone()[0]

            for ans in q.answers:
                cur.execute(
                    "INSERT INTO answers (content, label, is_correct, question_id) VALUES (%s, %s, %s, %s)",
                    (ans.content, ans.label, ans.is_correct, question_id)
                )

        return bank_id

    def _insert_classroom_material_in_tx(
        self,
        cur,
        class_id: int,
        material_type: str,
        book_id: Optional[int],
        question_bank_id: Optional[int],
        assigned_by_user_id: int,
    ) -> int:
        """Insert a new classroom_material row within an existing transaction."""
        cur.execute(
            """
            INSERT INTO classroom_materials (class_id, type, book_id, question_bank_id, assigned_by_user_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (class_id, material_type, book_id, question_bank_id, assigned_by_user_id)
        )
        material_id = cur.fetchone()[0]

        return material_id
