from fastapi import APIRouter, Depends, HTTPException
from typing import List, Literal, Optional
from src.quiz_gen.quiz_generator import get_db_connection
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
