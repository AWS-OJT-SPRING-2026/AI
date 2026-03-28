from fastapi import APIRouter, HTTPException
from typing import List, Optional
from src.quiz_gen.quiz_generator import get_db_connection
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class BookResponse(BaseModel):
    id: int
    book_name: str
    subject_name: str
    create_at: datetime
    meta: str
    doc_type: str

@router.get("", response_model=List[BookResponse])
def get_all_books():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT b.id, b.book_name, s.subject_name, b.create_at, 'theory' as doc_type
            FROM books b
            LEFT JOIN subjects s ON b.subject_id = s.subjectid
            UNION ALL
            SELECT q.id, q.bank_name as book_name, s.subject_name, (SELECT created_at FROM users WHERE userid = q.userid LIMIT 1) as create_at, 'question' as doc_type
            FROM question_bank q
            LEFT JOIN subjects s ON q.subject_id = s.subjectid
            ORDER BY create_at DESC
        """
        cur.execute(query)
        rows = cur.fetchall()
        
        books = []
        for row in rows:
            name = row[1]
            ext = name.split('.')[-1].upper() if name and '.' in name else 'DOC'
            doc_type = row[4]
            if doc_type == 'theory':
                meta = f"{ext} • Lý thuyết"
            else:
                meta = f"{ext} • Câu hỏi"
            
            books.append(BookResponse(
                id=row[0],
                book_name=row[1] or "Không tên",
                subject_name=row[2] or "N/A",
                create_at=row[3] or datetime.now(),
                meta=meta,
                doc_type=doc_type
            ))
        return books
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{doc_type}/{doc_id}")
def delete_book(doc_type: str, doc_id: int):
    if doc_type not in ('theory', 'question'):
        raise HTTPException(status_code=400, detail="Invalid doc type")
        
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        table = "books" if doc_type == "theory" else "question_bank"
        
        # Check if exists
        cur.execute(f"SELECT id FROM {table} WHERE id = %s", (doc_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Delete (cascade handles relationships for books, doing manual for questions)
        if doc_type == 'theory':
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
            cur.execute("DELETE FROM answers WHERE question_id IN (SELECT id FROM questions WHERE bank_id = %s)", (doc_id,))
            cur.execute("DELETE FROM questions WHERE bank_id = %s", (doc_id,))
            cur.execute("DELETE FROM question_bank WHERE id = %s", (doc_id,))
            
        conn.commit()
        return {"status": "success", "message": f"{doc_type} {doc_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
