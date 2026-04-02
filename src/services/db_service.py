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
        self._run_migrations()

    def _run_migrations(self) -> None:
        """
        Idempotent schema migrations — run once at startup.
        Adds columns that the application requires but that may not exist
        in older database deployments.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "ALTER TABLE books ADD COLUMN IF NOT EXISTS user_id INTEGER"
            )
            cur.execute(
                "ALTER TABLE books ADD COLUMN IF NOT EXISTS create_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )
            cur.execute(
                "ALTER TABLE books ADD COLUMN IF NOT EXISTS file_url TEXT"
            )
            cur.execute(
                "ALTER TABLE question_bank ADD COLUMN IF NOT EXISTS file_url TEXT"
            )
            cur.execute(
                "ALTER TABLE question_bank ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )
            cur.execute(
                "ALTER TABLE classroom_materials ADD COLUMN IF NOT EXISTS assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            )
            cur.execute(
                "ALTER TABLE classroom_materials ALTER COLUMN assigned_at SET DEFAULT CURRENT_TIMESTAMP"
            )
            cur.execute(
                "UPDATE classroom_materials SET assigned_at = CURRENT_TIMESTAMP WHERE assigned_at IS NULL"
            )
            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'fk_books_user_id'
                    ) THEN
                        ALTER TABLE books
                        ADD CONSTRAINT fk_books_user_id
                        FOREIGN KEY (user_id) REFERENCES users(userid) ON DELETE CASCADE;
                    END IF;
                END $$;
                """
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            # Non-fatal: log and continue — app can still run without these columns
            import logging
            logging.warning("[DBService] Migration warning: %s", exc)
        finally:
            cur.close()
            conn.close()

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

    def _lessons_has_estimated_time_column(self, cur) -> bool:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'lessons'
              AND column_name = 'estimated_time'
            LIMIT 1
            """
        )
        return cur.fetchone() is not None

    def _word_count(self, text: str) -> int:
        return len([token for token in (text or "").split() if token.strip()])

    def _estimate_lesson_time(self, lesson) -> int:
        total_words = 0
        for section in (lesson.section or []):
            if section.subsections:
                for sub in section.subsections:
                    for block in (sub.content_blocks or []):
                        total_words += self._word_count(block)
            elif section.content:
                total_words += self._word_count(section.content)
        return max(1, round(total_words / 200))

    def _books_has_file_url_column(self, cur) -> bool:
        """Return True when books.file_url exists in current DB schema."""
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'books'
              AND column_name  = 'file_url'
            LIMIT 1
            """
        )
        return cur.fetchone() is not None

    def _question_bank_has_file_url_column(self, cur) -> bool:
        """Return True when question_bank.file_url exists in current DB schema."""
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name   = 'question_bank'
              AND column_name  = 'file_url'
            LIMIT 1
            """
        )
        return cur.fetchone() is not None

    def _find_existing_book_id(self, cur, book_name: str, subject_id: int, user_id: int) -> Optional[int]:
        if self._books_has_user_id_column(cur):
            cur.execute(
                """
                SELECT id
                FROM books
                WHERE book_name = %s
                  AND subject_id = %s
                  AND user_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (book_name, subject_id, user_id),
            )
        else:
            cur.execute(
                """
                SELECT id
                FROM books
                WHERE book_name = %s
                  AND subject_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (book_name, subject_id),
            )
        row = cur.fetchone()
        return row[0] if row else None

    def _clear_book_hierarchy(self, cur, book_id: int):
        cur.execute(
            """
            DELETE FROM content_blocks
            WHERE subsection_id IN (
                SELECT ss.id
                FROM subsections ss
                JOIN sections s ON s.id = ss.section_id
                JOIN lessons l ON l.id = s.lesson_id
                JOIN chapters c ON c.id = l.chapter_id
                WHERE c.book_id = %s
            )
            """,
            (book_id,),
        )
        cur.execute(
            """
            DELETE FROM subsections
            WHERE section_id IN (
                SELECT s.id
                FROM sections s
                JOIN lessons l ON l.id = s.lesson_id
                JOIN chapters c ON c.id = l.chapter_id
                WHERE c.book_id = %s
            )
            """,
            (book_id,),
        )
        cur.execute(
            """
            DELETE FROM sections
            WHERE lesson_id IN (
                SELECT l.id
                FROM lessons l
                JOIN chapters c ON c.id = l.chapter_id
                WHERE c.book_id = %s
            )
            """,
            (book_id,),
        )
        cur.execute(
            """
            DELETE FROM lessons
            WHERE chapter_id IN (
                SELECT id FROM chapters WHERE book_id = %s
            )
            """,
            (book_id,),
        )
        cur.execute("DELETE FROM chapters WHERE book_id = %s", (book_id,))

    def _find_existing_bank_id(self, cur, bank_name: str, subject_id: int, userid: int) -> Optional[int]:
        cur.execute(
            """
            SELECT id
            FROM question_bank
            WHERE bank_name = %s
              AND subject_id = %s
              AND userid = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (bank_name, subject_id, userid),
        )
        row = cur.fetchone()
        return row[0] if row else None

    def _clear_question_bank_content(self, cur, bank_id: int):
        cur.execute(
            """
            DELETE FROM answers
            WHERE question_id IN (
                SELECT id FROM questions WHERE bank_id = %s
            )
            """,
            (bank_id,),
        )
        cur.execute("DELETE FROM questions WHERE bank_id = %s", (bank_id,))

    def get_existing_document(
        self,
        doc_type: str,
        filename: str,
        subject_id: int,
        user_id: int,
    ) -> Optional[tuple[int, Optional[str]]]:
        """
        Check whether a document with the same filename already belongs to this
        user + subject combination.

        Returns:
            (record_id, file_url)  — file_url may be None if column is absent/NULL
            None                   — no matching record found
        """
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if doc_type == "THEORY":
                has_uid = self._books_has_user_id_column(cur)
                has_url = self._books_has_file_url_column(cur)
                url_col = "file_url" if has_url else "NULL"
                if has_uid:
                    cur.execute(
                        f"SELECT id, {url_col} FROM books "
                        f"WHERE book_name = %s AND subject_id = %s AND user_id = %s "
                        f"ORDER BY id DESC LIMIT 1",
                        (filename, subject_id, user_id),
                    )
                else:
                    cur.execute(
                        f"SELECT id, {url_col} FROM books "
                        f"WHERE book_name = %s AND subject_id = %s "
                        f"ORDER BY id DESC LIMIT 1",
                        (filename, subject_id),
                    )
            elif doc_type == "QUESTION":
                has_url = self._question_bank_has_file_url_column(cur)
                url_col = "file_url" if has_url else "NULL"
                cur.execute(
                    f"SELECT id, {url_col} FROM question_bank "
                    f"WHERE bank_name = %s AND subject_id = %s AND userid = %s "
                    f"ORDER BY id DESC LIMIT 1",
                    (filename, subject_id, user_id),
                )
            else:
                return None

            row = cur.fetchone()
            if row is None:
                return None
            return (row[0], row[1])
        finally:
            cur.close()
            conn.close()

    def insert_book(self, book: Book, subject_id: int, user_id: Optional[int] = None):
        """
        Insert a Book (theory document) into the `books` table and its nested structure.
        Now supports the `user_id` column to track the creator.

        Returns the new book ID.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            book_id, _ = self._insert_book_in_tx(cur, book, subject_id, user_id or 0)
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
            bank_id, _ = self._insert_quiz_in_tx(cur, qb.model_dump(), subject_id, userid)

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
                INSERT INTO classroom_materials (class_id, type, book_id, question_bank_id, assigned_by_user_id, assigned_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
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
        original_filename: Optional[str] = None,
        s3_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete 3-step upload transaction:

        1. Extract document content from file (theory or question).
        2. Save to personal repository (books or question_bank), storing the S3 URL
           in the file_url column when it exists in the target table.
        3. Distribute to classroom via classroom_materials (insert-only).

        All database operations share a single connection/transaction.
        On any error, ALL changes are rolled back.
        """
        conn = get_db_connection()
        cur = conn.cursor()

        try:
            # ═══════════ STEP 1: Extract content from uploaded file ═══════════
            incoming_name = original_filename or os.path.basename(file_path)

            if doc_type == "THEORY":
                extracted_data = extraction_service.extract_theory(file_path)
                extracted_data.book_name = incoming_name
            elif doc_type == "QUESTION":
                extracted_data = extraction_service.extract_quiz(file_path)
                extracted_data["bank_name"] = incoming_name
            else:
                raise ValueError(f"Invalid doc_type: {doc_type}. Must be 'THEORY' or 'QUESTION'.")

            # ═══════════ STEP 2: Save to personal repository ═══════════
            if doc_type == "THEORY":
                record_id, upserted = self._insert_book_in_tx(
                    cur, extracted_data, subject_id, user_id, file_url=s3_url
                )
                book_id = record_id
                question_bank_id = None
            else:  # QUESTION
                record_id, upserted = self._insert_quiz_in_tx(
                    cur, extracted_data, subject_id, user_id, file_url=s3_url
                )
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
                "upserted": upserted,
                "file_url": s3_url,
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

    def _insert_book_in_tx(self, cur, book: Book, subject_id: int, user_id: int, file_url: Optional[str] = None) -> tuple[int, bool]:
        """Insert or update a Book (theory) within an existing DB transaction."""
        existing_book_id = self._find_existing_book_id(cur, book.book_name, subject_id, user_id)
        upserted = existing_book_id is not None
        lessons_has_estimated = self._lessons_has_estimated_time_column(cur)
        has_user_id = self._books_has_user_id_column(cur)
        has_file_url = self._books_has_file_url_column(cur)

        if upserted:
            book_id = existing_book_id
            if has_user_id and has_file_url:
                cur.execute(
                    "UPDATE books SET book_name = %s, subject_id = %s, user_id = %s, file_url = %s WHERE id = %s",
                    (book.book_name, subject_id, user_id, file_url, book_id),
                )
            elif has_user_id:
                cur.execute(
                    "UPDATE books SET book_name = %s, subject_id = %s, user_id = %s WHERE id = %s",
                    (book.book_name, subject_id, user_id, book_id),
                )
            elif has_file_url:
                cur.execute(
                    "UPDATE books SET book_name = %s, subject_id = %s, file_url = %s WHERE id = %s",
                    (book.book_name, subject_id, file_url, book_id),
                )
            else:
                cur.execute(
                    "UPDATE books SET book_name = %s, subject_id = %s WHERE id = %s",
                    (book.book_name, subject_id, book_id),
                )
            self._clear_book_hierarchy(cur, book_id)
        else:
            if has_user_id and has_file_url:
                cur.execute(
                    "INSERT INTO books (book_name, subject_id, user_id, file_url) VALUES (%s, %s, %s, %s) RETURNING id",
                    (book.book_name, subject_id, user_id, file_url),
                )
            elif has_user_id:
                cur.execute(
                    "INSERT INTO books (book_name, subject_id, user_id) VALUES (%s, %s, %s) RETURNING id",
                    (book.book_name, subject_id, user_id)
                )
            elif has_file_url:
                cur.execute(
                    "INSERT INTO books (book_name, subject_id, file_url) VALUES (%s, %s, %s) RETURNING id",
                    (book.book_name, subject_id, file_url),
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
                estimated_time = self._estimate_lesson_time(lesson)
                if lessons_has_estimated:
                    cur.execute(
                        "INSERT INTO lessons (chapter_id, lesson_number, title, estimated_time) VALUES (%s, %s, %s, %s) RETURNING id",
                        (chapter_id, lesson.lesson_number, lesson.title, estimated_time)
                    )
                else:
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
        return book_id, upserted

    def _insert_quiz_in_tx(self, cur, data: Dict[str, Any], subject_id: int, userid: int, file_url: Optional[str] = None) -> tuple[int, bool]:
        """Insert or update a Question Bank within an existing DB transaction."""
        qb = QuestionBank.model_validate(data)

        # Ensure user exists
        cur.execute("SELECT userid FROM users WHERE userid = %s", (userid,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (userid, roleid) VALUES (%s, 2)", (userid,))

        bank_name = qb.bank_name or f"Bank - {subject_id}"
        existing_bank_id = self._find_existing_bank_id(cur, bank_name, subject_id, userid)
        upserted = existing_bank_id is not None
        has_file_url = self._question_bank_has_file_url_column(cur)

        if upserted:
            bank_id = existing_bank_id
            if has_file_url:
                cur.execute(
                    "UPDATE question_bank SET bank_name = %s, subject_id = %s, userid = %s, file_url = %s WHERE id = %s",
                    (bank_name, subject_id, userid, file_url, bank_id),
                )
            else:
                cur.execute(
                    "UPDATE question_bank SET bank_name = %s, subject_id = %s, userid = %s WHERE id = %s",
                    (bank_name, subject_id, userid, bank_id),
                )
            self._clear_question_bank_content(cur, bank_id)
        else:
            if has_file_url:
                cur.execute(
                    "INSERT INTO question_bank (bank_name, userid, subject_id, file_url) VALUES (%s, %s, %s, %s) RETURNING id",
                    (bank_name, userid, subject_id, file_url),
                )
            else:
                cur.execute(
                    "INSERT INTO question_bank (bank_name, userid, subject_id) VALUES (%s, %s, %s) RETURNING id",
                    (bank_name, userid, subject_id)
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

        return bank_id, upserted

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
            INSERT INTO classroom_materials (class_id, type, book_id, question_bank_id, assigned_by_user_id, assigned_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (class_id, material_type, book_id, question_bank_id, assigned_by_user_id)
        )
        material_id = cur.fetchone()[0]

        return material_id

    # ──────────────────────────────────────────────────────────────────────────
    # Delete helpers
    # ──────────────────────────────────────────────────────────────────────────

    def get_document_file_url(self, doc_type: str, doc_id: int) -> Optional[str]:
        """
        Fetch the stored S3 file_url for a document.

        Returns None when:
        - The record does not exist (raises ValueError).
        - The file_url column is absent or NULL.

        Raises:
            ValueError: if doc_type is invalid or the record is not found.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if doc_type == "THEORY":
                # Check whether the file_url column exists before querying it
                if self._books_has_file_url_column(cur):
                    cur.execute(
                        "SELECT file_url FROM books WHERE id = %s", (doc_id,)
                    )
                else:
                    cur.execute("SELECT NULL FROM books WHERE id = %s", (doc_id,))
            elif doc_type == "QUESTION":
                if self._question_bank_has_file_url_column(cur):
                    cur.execute(
                        "SELECT file_url FROM question_bank WHERE id = %s", (doc_id,)
                    )
                else:
                    cur.execute(
                        "SELECT NULL FROM question_bank WHERE id = %s", (doc_id,)
                    )
            else:
                raise ValueError(
                    f"doc_type không hợp lệ: '{doc_type}'. Chỉ chấp nhận 'THEORY' hoặc 'QUESTION'."
                )

            row = cur.fetchone()
            if row is None:
                raise ValueError(
                    f"Không tìm thấy tài liệu {doc_type} với id={doc_id}."
                )
            return row[0]  # may be None if column is NULL
        finally:
            cur.close()
            conn.close()

    def delete_document_from_db(self, doc_type: str, doc_id: int) -> None:
        """
        Delete a document record and all related data from the database.

        Deletion order (to respect FK constraints):
        1. Remove rows in classroom_materials that reference this document.
        2. Delete the main record (books or question_bank); cascade handles
           child tables (chapters → lessons → … → content_blocks  /
           questions → answers).

        Raises:
            ValueError: if doc_type is invalid or the record is not found.
        """
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            if doc_type == "THEORY":
                # Verify record exists
                cur.execute("SELECT id FROM books WHERE id = %s", (doc_id,))
                if cur.fetchone() is None:
                    raise ValueError(
                        f"Không tìm thấy tài liệu THEORY với id={doc_id}."
                    )
                # 1. Remove classroom_materials references
                cur.execute(
                    "DELETE FROM classroom_materials WHERE book_id = %s", (doc_id,)
                )
                # 2. Delete book (cascades to chapters → lessons → sections
                #    → subsections → content_blocks)
                cur.execute("DELETE FROM books WHERE id = %s", (doc_id,))

            elif doc_type == "QUESTION":
                cur.execute(
                    "SELECT id FROM question_bank WHERE id = %s", (doc_id,)
                )
                if cur.fetchone() is None:
                    raise ValueError(
                        f"Không tìm thấy tài liệu QUESTION với id={doc_id}."
                    )
                # 1. Remove classroom_materials references
                cur.execute(
                    "DELETE FROM classroom_materials WHERE question_bank_id = %s",
                    (doc_id,),
                )
                # 2. Delete question_bank (cascades to questions → answers)
                cur.execute(
                    "DELETE FROM question_bank WHERE id = %s", (doc_id,)
                )
            else:
                raise ValueError(
                    f"doc_type không hợp lệ: '{doc_type}'. Chỉ chấp nhận 'THEORY' hoặc 'QUESTION'."
                )

            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise exc
        finally:
            cur.close()
            conn.close()
