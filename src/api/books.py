from fastapi import APIRouter, Depends, HTTPException
from typing import List, Literal, Optional
from src.quiz_gen.quiz_generator import get_db_connection, generate_quiz, save_quiz_to_db, calculate_difficulty_distribution, build_theory_text, fetch_existing_ai_questions_by_bank
from pydantic import BaseModel
from datetime import datetime
from src.core.security import get_current_user_id
from src.services.s3_service import s3_service
import logging
import traceback

logger = logging.getLogger(__name__)

router = APIRouter()

class BookResponse(BaseModel):
    id: int
    book_name: str
    subject_name: str
    uploadDate: datetime
    meta: str
    doc_type: Literal['theory', 'question']
    assigned_class_count: int
    owner_id: Optional[int] = None


class AssignedClassroomResponse(BaseModel):
    classid: int
    class_name: str
    subject_id: Optional[int] = None
    subject_name: str
    assigned_at: Optional[datetime] = None


class DocumentStatsResponse(BaseModel):
    chapters: int = 0
    lessons: int = 0
    sections: int = 0
    content_blocks: int = 0
    questions: int = 0
    answers: int = 0


class DocumentDetailResponse(BaseModel):
    id: int
    doc_type: Literal['theory', 'question']
    book_name: str
    subject_id: int
    subject_name: str
    uploadDate: datetime
    assigned_class_count: int
    assigned_classrooms: List[AssignedClassroomResponse]
    stats: DocumentStatsResponse


class DistributeRequest(BaseModel):
    subject_id: int
    class_ids: List[int]


def _validate_doc_type(doc_type: str) -> Literal['theory', 'question']:
    if doc_type not in ('theory', 'question'):
        raise HTTPException(status_code=400, detail='Invalid doc type')
    return doc_type


def _is_admin(cur, user_id: int) -> bool:
    """Return True when the user holds the ADMIN role.

    Uses a savepoint so that a query failure (e.g. wrong column name) does
    not abort the surrounding transaction.
    """
    try:
        cur.execute("SAVEPOINT sp_is_admin")
        cur.execute(
            """
            SELECT r.rolename
            FROM users u
            JOIN roles r ON r.roleid = u.roleid
            WHERE u.userid = %s
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT sp_is_admin")
        return row is not None and "ADMIN" in row[0].upper()
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT sp_is_admin")
        except Exception:
            pass
        return False


def _get_document_owner(cur, doc_type: Literal['theory', 'question'], doc_id: int) -> Optional[int]:
    """Return the owner's user_id for the document, or None if it cannot be determined."""
    if doc_type == 'theory':
        if not _has_column(cur, 'books', 'user_id'):
            return None
        cur.execute("SELECT user_id FROM books WHERE id = %s", (doc_id,))
    else:
        cur.execute("SELECT userid FROM question_bank WHERE id = %s", (doc_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _has_column(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return cur.fetchone() is not None


def _get_document_info(cur, doc_type: Literal['theory', 'question'], doc_id: int):
    if doc_type == 'theory':
        cur.execute(
            """
            SELECT b.id, b.book_name, b.subject_id, s.subject_name,
                   COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE book_id = b.id AND type='THEORY'), b.create_at) AS upload_date
            FROM books b
            LEFT JOIN subjects s ON b.subject_id = s.subjectid
            WHERE b.id = %s
            """,
            (doc_id,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Document not found')
        return row

    has_created_at = _has_column(cur, 'question_bank', 'created_at')
    if has_created_at:
        cur.execute(
            """
            SELECT q.id, q.bank_name, q.subject_id, s.subject_name,
                   COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE question_bank_id = q.id AND type='QUESTION'), q.created_at) AS upload_date
            FROM question_bank q
            LEFT JOIN subjects s ON q.subject_id = s.subjectid
            WHERE q.id = %s
            """,
            (doc_id,),
        )
    else:
        cur.execute(
            """
            SELECT q.id, q.bank_name, q.subject_id, s.subject_name,
                   COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE question_bank_id = q.id AND type='QUESTION'), NOW()) AS upload_date
            FROM question_bank q
            LEFT JOIN subjects s ON q.subject_id = s.subjectid
            WHERE q.id = %s
            """,
            (doc_id,),
        )

    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Document not found')
    return row

@router.get("", response_model=List[BookResponse])
def get_all_books(user_id: int = Depends(get_current_user_id)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        has_book_user_id = _has_column(cur, 'books', 'user_id')
        is_admin = _is_admin(cur, user_id)

        # Columns: id, book_name, subject_name, upload_date, doc_type, assigned_class_count, owner_id
        if has_book_user_id:
            if is_admin:
                # Admin sees every document from every teacher
                query = """
                    SELECT b.id, b.book_name, s.subject_name,
                           COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE book_id = b.id AND type='THEORY'), b.create_at) AS upload_date,
                           'theory' as doc_type,
                           COALESCE((SELECT COUNT(DISTINCT class_id) FROM classroom_materials WHERE book_id = b.id AND type='THEORY'), 0) AS assigned_class_count,
                           b.user_id AS owner_id
                    FROM books b
                    LEFT JOIN subjects s ON b.subject_id = s.subjectid
                    UNION ALL
                    SELECT q.id, q.bank_name, s.subject_name,
                           COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE question_bank_id = q.id AND type='QUESTION'), NOW()) as upload_date,
                           'question' as doc_type,
                           COALESCE((SELECT COUNT(DISTINCT class_id) FROM classroom_materials WHERE question_bank_id = q.id AND type='QUESTION'), 0) AS assigned_class_count,
                           q.userid AS owner_id
                    FROM question_bank q
                    LEFT JOIN subjects s ON q.subject_id = s.subjectid
                    ORDER BY upload_date DESC
                """
                cur.execute(query)
            else:
                # Teacher sees only their own documents
                query = """
                    SELECT b.id, b.book_name, s.subject_name,
                           COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE book_id = b.id AND type='THEORY'), b.create_at) AS upload_date,
                           'theory' as doc_type,
                           COALESCE((SELECT COUNT(DISTINCT class_id) FROM classroom_materials WHERE book_id = b.id AND type='THEORY'), 0) AS assigned_class_count,
                           b.user_id AS owner_id
                    FROM books b
                    LEFT JOIN subjects s ON b.subject_id = s.subjectid
                    WHERE b.user_id = %s
                    UNION ALL
                    SELECT q.id, q.bank_name, s.subject_name,
                           COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE question_bank_id = q.id AND type='QUESTION'), NOW()) as upload_date,
                           'question' as doc_type,
                           COALESCE((SELECT COUNT(DISTINCT class_id) FROM classroom_materials WHERE question_bank_id = q.id AND type='QUESTION'), 0) AS assigned_class_count,
                           q.userid AS owner_id
                    FROM question_bank q
                    LEFT JOIN subjects s ON q.subject_id = s.subjectid
                    WHERE q.userid = %s
                    ORDER BY upload_date DESC
                """
                cur.execute(query, (user_id, user_id))
        else:
            # Fallback: user_id column absent — return all, owner_id unknown
            query = """
                SELECT b.id, b.book_name, s.subject_name,
                       COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE book_id = b.id AND type='THEORY'), b.create_at) AS upload_date,
                       'theory' as doc_type,
                       COALESCE((SELECT COUNT(DISTINCT class_id) FROM classroom_materials WHERE book_id = b.id AND type='THEORY'), 0) AS assigned_class_count,
                       NULL AS owner_id
                FROM books b
                LEFT JOIN subjects s ON b.subject_id = s.subjectid
                UNION ALL
                SELECT q.id, q.bank_name, s.subject_name,
                       COALESCE((SELECT MAX(assigned_at) FROM classroom_materials WHERE question_bank_id = q.id AND type='QUESTION'), NOW()) as upload_date,
                       'question' as doc_type,
                       COALESCE((SELECT COUNT(DISTINCT class_id) FROM classroom_materials WHERE question_bank_id = q.id AND type='QUESTION'), 0) AS assigned_class_count,
                       NULL AS owner_id
                FROM question_bank q
                LEFT JOIN subjects s ON q.subject_id = s.subjectid
                ORDER BY upload_date DESC
            """
            cur.execute(query)

        rows = cur.fetchall()
        books = []
        for row in rows:
            name = row[1]
            ext = name.split('.')[-1].upper() if name and '.' in name else 'DOC'
            doc_type = row[4]
            meta = f"{ext} • {'Lý thuyết' if doc_type == 'theory' else 'Câu hỏi'}"
            books.append(BookResponse(
                id=row[0],
                book_name=row[1] or "Không tên",
                subject_name=row[2] or "N/A",
                uploadDate=row[3] or datetime.now(),
                meta=meta,
                doc_type=doc_type,
                assigned_class_count=row[5] or 0,
                owner_id=row[6],
            ))
        return books
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/{doc_type}/{doc_id}", response_model=DocumentDetailResponse)
def get_document_detail(
    doc_type: str,
    doc_id: int,
    user_id: int = Depends(get_current_user_id),
):
    _ = user_id  # token is required for teacher actions
    normalized_type = _validate_doc_type(doc_type)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        doc = _get_document_info(cur, normalized_type, doc_id)

        if normalized_type == 'theory':
            cur.execute("SELECT COUNT(*) FROM chapters WHERE book_id = %s", (doc_id,))
            chapters = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM lessons WHERE chapter_id IN (SELECT id FROM chapters WHERE book_id = %s)", (doc_id,))
            lessons = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM sections WHERE lesson_id IN (SELECT id FROM lessons WHERE chapter_id IN (SELECT id FROM chapters WHERE book_id = %s))", (doc_id,))
            sections = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM content_blocks WHERE subsection_id IN (SELECT id FROM subsections WHERE section_id IN (SELECT id FROM sections WHERE lesson_id IN (SELECT id FROM lessons WHERE chapter_id IN (SELECT id FROM chapters WHERE book_id = %s))))", (doc_id,))
            content_blocks = cur.fetchone()[0]
            stats = DocumentStatsResponse(
                chapters=chapters,
                lessons=lessons,
                sections=sections,
                content_blocks=content_blocks,
            )
            cur.execute(
                """
                SELECT c.classid, c.class_name, c.subjectid, s.subject_name, cm.assigned_at
                FROM classroom_materials cm
                JOIN classrooms c ON c.classid = cm.class_id
                LEFT JOIN subjects s ON s.subjectid = c.subjectid
                WHERE cm.type = 'THEORY' AND cm.book_id = %s
                ORDER BY cm.assigned_at DESC
                """,
                (doc_id,),
            )
        else:
            cur.execute("SELECT COUNT(*) FROM questions WHERE bank_id = %s", (doc_id,))
            questions = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM answers WHERE question_id IN (SELECT id FROM questions WHERE bank_id = %s)", (doc_id,))
            answers = cur.fetchone()[0]
            stats = DocumentStatsResponse(questions=questions, answers=answers)
            cur.execute(
                """
                SELECT c.classid, c.class_name, c.subjectid, s.subject_name, cm.assigned_at
                FROM classroom_materials cm
                JOIN classrooms c ON c.classid = cm.class_id
                LEFT JOIN subjects s ON s.subjectid = c.subjectid
                WHERE cm.type = 'QUESTION' AND cm.question_bank_id = %s
                ORDER BY cm.assigned_at DESC
                """,
                (doc_id,),
            )

        assigned_rows = cur.fetchall()
        assigned_classrooms = [
            AssignedClassroomResponse(
                classid=row[0],
                class_name=row[1],
                subject_id=row[2],
                subject_name=row[3] or 'N/A',
                assigned_at=row[4],
            )
            for row in assigned_rows
        ]

        return DocumentDetailResponse(
            id=doc[0],
            doc_type=normalized_type,
            book_name=doc[1] or 'Không tên',
            subject_id=doc[2],
            subject_name=doc[3] or 'N/A',
            uploadDate=doc[4] or datetime.now(),
            assigned_class_count=len(assigned_classrooms),
            assigned_classrooms=assigned_classrooms,
            stats=stats,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.post("/{doc_type}/{doc_id}/distribute")
def distribute_document(
    doc_type: str,
    doc_id: int,
    payload: DistributeRequest,
    user_id: int = Depends(get_current_user_id),
):
    normalized_type = _validate_doc_type(doc_type)
    class_ids = sorted(set(payload.class_ids))
    if not class_ids:
        raise HTTPException(status_code=400, detail='Vui lòng chọn ít nhất một lớp học')

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        doc = _get_document_info(cur, normalized_type, doc_id)
        if int(doc[2]) != int(payload.subject_id):
            raise HTTPException(status_code=400, detail='Môn học phân phối không khớp với tài liệu')

        cur.execute("SELECT teacherid FROM teachers WHERE userid = %s", (user_id,))
        teacher_row = cur.fetchone()
        if not teacher_row:
            raise HTTPException(status_code=403, detail='Bạn không phải giáo viên hợp lệ')

        teacher_id = teacher_row[0]
        cur.execute(
            """
            SELECT classid, subjectid
            FROM classrooms
            WHERE teacherid = %s
              AND classid = ANY(%s)
            """,
            (teacher_id, class_ids),
        )
        rows = cur.fetchall()

        if len(rows) != len(class_ids):
            raise HTTPException(status_code=403, detail='Bạn chỉ có thể phân phối cho lớp do mình phụ trách')

        wrong_subject = [row[0] for row in rows if int(row[1]) != int(payload.subject_id)]
        if wrong_subject:
            raise HTTPException(status_code=400, detail='Một số lớp không thuộc môn học đã chọn')

        material_type = 'THEORY' if normalized_type == 'theory' else 'QUESTION'
        for class_id in class_ids:
            cur.execute(
                "SELECT id FROM classroom_materials WHERE class_id = %s AND type = %s",
                (class_id, material_type),
            )
            existing = cur.fetchone()

            if existing:
                if normalized_type == 'theory':
                    cur.execute(
                        """
                        UPDATE classroom_materials
                        SET book_id = %s,
                            question_bank_id = NULL,
                            assigned_by_user_id = %s,
                            assigned_at = NOW()
                        WHERE id = %s
                        """,
                        (doc_id, user_id, existing[0]),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE classroom_materials
                        SET question_bank_id = %s,
                            book_id = NULL,
                            assigned_by_user_id = %s,
                            assigned_at = NOW()
                        WHERE id = %s
                        """,
                        (doc_id, user_id, existing[0]),
                    )
            else:
                if normalized_type == 'theory':
                    cur.execute(
                        """
                        INSERT INTO classroom_materials (class_id, type, book_id, question_bank_id, assigned_by_user_id, assigned_at)
                        VALUES (%s, 'THEORY', %s, NULL, %s, NOW())
                        """,
                        (class_id, doc_id, user_id),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO classroom_materials (class_id, type, book_id, question_bank_id, assigned_by_user_id, assigned_at)
                        VALUES (%s, 'QUESTION', NULL, %s, %s, NOW())
                        """,
                        (class_id, doc_id, user_id),
                    )

        conn.commit()
        return {
            'status': 'success',
            'distributed_count': len(class_ids),
            'doc_type': normalized_type,
            'doc_id': doc_id,
            'class_ids': class_ids,
        }
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{doc_type}/{doc_id}")
def delete_book(doc_type: str, doc_id: int, user_id: int = Depends(get_current_user_id)):
    normalized_type = _validate_doc_type(doc_type)

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        table = "books" if normalized_type == "theory" else "question_bank"

        # ── Ownership / permission check ──
        owner_id = _get_document_owner(cur, normalized_type, doc_id)
        if owner_id is not None and owner_id != user_id:
            if not _is_admin(cur, user_id):
                raise HTTPException(
                    status_code=403,
                    detail="Bạn không có quyền xóa tài liệu này.",
                )

        # ── Fetch file_url for S3 deletion (before touching DB) ──
        file_url: Optional[str] = None
        if _has_column(cur, table, "file_url"):
            cur.execute(f"SELECT file_url FROM {table} WHERE id = %s", (doc_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Document not found")
            file_url = row[0]
        else:
            cur.execute(f"SELECT id FROM {table} WHERE id = %s", (doc_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Document not found")

        # ── Delete from S3 first ──
        if file_url:
            try:
                found = s3_service.delete_document(file_url)
                if not found:
                    logger.warning(
                        "[DELETE] S3 object not found, continuing with DB delete: %s", file_url
                    )
            except RuntimeError as exc:
                logger.error("[DELETE S3 ERROR] %s", traceback.format_exc())
                raise HTTPException(
                    status_code=502,
                    detail=f"Không thể xóa file trên S3, tài liệu chưa bị xóa: {exc}",
                )
        else:
            logger.warning(
                "[DELETE] Không có file_url trong DB cho %s id=%s, bỏ qua bước xóa S3.",
                normalized_type, doc_id,
            )

        # Delete (cascade handles relationships for books, doing manual for questions)
        if normalized_type == 'theory':
            cur.execute("DELETE FROM classroom_materials WHERE type = 'THEORY' AND book_id = %s", (doc_id,))
            cur.execute("""
                DELETE FROM content_blocks WHERE subsection_id IN (
                    SELECT id FROM subsections WHERE section_id IN (
                        SELECT id FROM sections WHERE lesson_id IN (
                            SELECT id FROM lessons WHERE chapter_id IN (
                                SELECT id FROM chapters WHERE book_id = %s
                            )
                        )
                    )
                )
            """, (doc_id,))
            cur.execute("""
                DELETE FROM subsections WHERE section_id IN (
                    SELECT id FROM sections WHERE lesson_id IN (
                        SELECT id FROM lessons WHERE chapter_id IN (
                            SELECT id FROM chapters WHERE book_id = %s
                        )
                    )
                )
            """, (doc_id,))
            cur.execute("""
                DELETE FROM sections WHERE lesson_id IN (
                    SELECT id FROM lessons WHERE chapter_id IN (
                        SELECT id FROM chapters WHERE book_id = %s
                    )
                )
            """, (doc_id,))
            cur.execute("""
                DELETE FROM roadmap_lessons WHERE lessonid IN (
                    SELECT id FROM lessons WHERE chapter_id IN (
                        SELECT id FROM chapters WHERE book_id = %s
                    )
                )
            """, (doc_id,))
            cur.execute("""
                DELETE FROM roadmap_chapters WHERE chapterid IN (
                    SELECT id FROM chapters WHERE book_id = %s
                )
            """, (doc_id,))
            cur.execute("DELETE FROM lessons WHERE chapter_id IN (SELECT id FROM chapters WHERE book_id = %s)", (doc_id,))
            cur.execute("DELETE FROM chapters WHERE book_id = %s", (doc_id,))
            cur.execute("DELETE FROM books WHERE id = %s", (doc_id,))
        else:
            cur.execute("DELETE FROM classroom_materials WHERE type = 'QUESTION' AND question_bank_id = %s", (doc_id,))
            cur.execute("DELETE FROM question_content_blocks WHERE questionid IN (SELECT id FROM questions WHERE bank_id = %s)", (doc_id,))
            # Clear dependent rows first for databases where FK is not ON DELETE CASCADE.
            cur.execute("DELETE FROM submission_answers WHERE answer_ref_id IN (SELECT id FROM answers WHERE question_id IN (SELECT id FROM questions WHERE bank_id = %s))", (doc_id,))
            cur.execute("DELETE FROM submission_answers WHERE questionid IN (SELECT id FROM questions WHERE bank_id = %s)", (doc_id,))
            cur.execute("DELETE FROM assignment_questions WHERE questionid IN (SELECT id FROM questions WHERE bank_id = %s)", (doc_id,))
            cur.execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE bank_id = %s)", (doc_id,))
            cur.execute("DELETE FROM questions WHERE bank_id = %s", (doc_id,))
            cur.execute("DELETE FROM question_bank WHERE id = %s", (doc_id,))
            
        conn.commit()
        return {"status": "success", "message": f"{normalized_type} {doc_id} deleted successfully"}
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── Curriculum: list chapters + lessons for a theory book ────────────────────

class LessonResponse(BaseModel):
    id: int
    number: int
    title: str

class ChapterResponse(BaseModel):
    id: int
    number: int
    title: str
    lessons: List[LessonResponse] = []


class LessonContentItem(BaseModel):
    section_number: int
    section_title: str
    subsection_title: Optional[str] = None
    content: Optional[str] = None


@router.get("/theory/lessons/{lesson_id}/content", response_model=List[LessonContentItem])
def get_lesson_content(lesson_id: int, user_id: int = Depends(get_current_user_id)):
    """
    Return content for a lesson using LEFT JOINs from sections.
    Works even when content_blocks are missing — returns section structure regardless.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT
                s.section_number,
                s.section_title,
                sub.subsection_title,
                cb.content
            FROM sections s
            LEFT JOIN subsections sub ON sub.section_id = s.id
            LEFT JOIN content_blocks cb ON cb.subsection_id = sub.id
            WHERE s.lesson_id = %s
            ORDER BY s.section_number, sub.subsection_number, cb.id
            """,
            (lesson_id,),
        )
        rows = cur.fetchall()
        results = []
        for sec_num, sec_title, sub_title, content in rows:
            # Always include rows that have content; also include section headers even without content
            if content or not results or results[-1].section_number != (sec_num or 0):
                try:
                    sec_num_int = int(sec_num) if sec_num is not None else 0
                except (ValueError, TypeError):
                    sec_num_int = 0
                results.append(LessonContentItem(
                    section_number=sec_num_int,
                    section_title=sec_title or "",
                    subsection_title=sub_title if sub_title and sub_title.strip() else None,
                    content=content.strip() if content and content.strip() else None,
                ))
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/theory/lessons/{lesson_id}/debug")
def debug_lesson_structure(lesson_id: int, user_id: int = Depends(get_current_user_id)):
    """Debug: show raw row counts for a lesson to diagnose missing content."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM sections WHERE lesson_id = %s", (lesson_id,))
        sections = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM subsections WHERE section_id IN (SELECT id FROM sections WHERE lesson_id = %s)", (lesson_id,))
        subsections = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM content_blocks WHERE subsection_id IN (SELECT id FROM subsections WHERE section_id IN (SELECT id FROM sections WHERE lesson_id = %s))", (lesson_id,))
        content_blocks = cur.fetchone()[0]
        cur.execute("SELECT id, section_number, section_title FROM sections WHERE lesson_id = %s ORDER BY section_number LIMIT 5", (lesson_id,))
        sample_sections = [{"id": r[0], "number": r[1], "title": r[2]} for r in cur.fetchall()]
        return {
            "lesson_id": lesson_id,
            "sections_count": sections,
            "subsections_count": subsections,
            "content_blocks_count": content_blocks,
            "sample_sections": sample_sections,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.get("/theory/{book_id}/chapters", response_model=List[ChapterResponse])
def get_book_chapters(book_id: int, user_id: int = Depends(get_current_user_id)):
    """Return chapters + lessons for a theory book (curriculum detail view)."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT id, chapter_number, title FROM chapters WHERE book_id = %s ORDER BY chapter_number",
            (book_id,),
        )
        chapter_rows = cur.fetchall()

        chapters: List[ChapterResponse] = []
        for ch_id, ch_num, ch_title in chapter_rows:
            cur.execute(
                "SELECT id, lesson_number, title FROM lessons WHERE chapter_id = %s ORDER BY lesson_number",
                (ch_id,),
            )
            lessons = [
                LessonResponse(id=r[0], number=r[1], title=r[2])
                for r in cur.fetchall()
            ]
            chapters.append(ChapterResponse(id=ch_id, number=ch_num, title=ch_title or "", lessons=lessons))

        return chapters
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ── AI question generation for selected question banks ───────────────────────

class GenerateAIForBanksRequest(BaseModel):
    bank_ids: List[int]
    num_questions: int

class GenerateAIForBanksResponse(BaseModel):
    generated_count: int
    bank_ids: List[int]


@router.post("/question-banks/generate-ai", response_model=GenerateAIForBanksResponse)
def generate_ai_questions_for_banks(
    request: GenerateAIForBanksRequest,
    user_id: int = Depends(get_current_user_id),
):
    """
    Generate AI questions for the given question banks and save them (is_ai=True).
    Questions are generated from theory content of the same subject as each bank.
    """
    if not request.bank_ids or request.num_questions <= 0:
        raise HTTPException(status_code=400, detail="Cần ít nhất 1 ngân hàng và số câu > 0")

    conn = get_db_connection()
    cur = conn.cursor()
    total_generated = 0

    try:
        # Map bank_id -> subject_id (only for banks owned by this user)
        subject_bank_pairs: List[tuple] = []
        for bank_id in request.bank_ids:
            cur.execute(
                "SELECT subject_id FROM question_bank WHERE id = %s AND userid = %s",
                (bank_id, user_id),
            )
            row = cur.fetchone()
            if row and row[0]:
                subject_bank_pairs.append((row[0], bank_id))

        if not subject_bank_pairs:
            raise HTTPException(
                status_code=404,
                detail="Không tìm thấy môn học hợp lệ cho các ngân hàng đã chọn",
            )

        # Distribute questions equally across banks
        per_bank = max(1, request.num_questions // len(subject_bank_pairs))
        remainder = request.num_questions - per_bank * len(subject_bank_pairs)

        for idx, (subject_id, bank_id) in enumerate(subject_bank_pairs):
            num_for_this_bank = per_bank + (1 if idx < remainder else 0)

            # Find a theory book for this subject
            cur.execute(
                "SELECT id FROM books WHERE subject_id = %s ORDER BY id DESC LIMIT 1",
                (subject_id,),
            )
            book_row = cur.fetchone()
            if not book_row:
                continue  # No theory content available, skip

            book_id = book_row[0]

            # Fetch theory content for this book
            cur.execute(
                """
                SELECT b.book_name,
                       ch.chapter_number, ch.title,
                       l.lesson_number, l.title,
                       s.section_number, s.section_title,
                       sub.subsection_number, sub.subsection_title,
                       cb.content, cb.id
                FROM content_blocks cb
                JOIN subsections sub ON cb.subsection_id = sub.id
                JOIN sections s ON sub.section_id = s.id
                JOIN lessons l ON s.lesson_id = l.id
                JOIN chapters ch ON l.chapter_id = ch.id
                JOIN books b ON ch.book_id = b.id
                WHERE b.id = %s
                ORDER BY ch.chapter_number, l.lesson_number, s.section_number, sub.subsection_number, cb.id
                """,
                (book_id,),
            )
            rows = cur.fetchall()
            if not rows:
                continue

            content_blocks = [
                {
                    "book_name": r[0], "chapter_number": r[1], "chapter_title": r[2],
                    "lesson_number": r[3], "lesson_title": r[4],
                    "section_number": r[5], "section_title": r[6],
                    "subsection_number": r[7], "subsection_title": r[8],
                    "content": r[9], "content_block_id": r[10],
                }
                for r in rows
            ]

            theory_text = build_theory_text(content_blocks)
            existing_questions = fetch_existing_ai_questions_by_bank(bank_id)
            dist = calculate_difficulty_distribution(num_for_this_bank, None, None, None)

            quiz_data = generate_quiz(text=theory_text, dist=dist, existing_questions=existing_questions)
            inserted_ids = save_quiz_to_db(quiz_data=quiz_data, bank_id=bank_id)
            total_generated += len(inserted_ids)

        conn.commit()
        return GenerateAIForBanksResponse(generated_count=total_generated, bank_ids=request.bank_ids)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi sinh câu hỏi AI: {str(e)}")
    finally:
        cur.close()
        conn.close()
