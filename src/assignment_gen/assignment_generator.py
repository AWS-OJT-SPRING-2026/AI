import os
import json
import random
from typing import List, Optional
from datetime import datetime
import psycopg2
from dotenv import load_dotenv

# Import các hàm từ quiz_generator
from src.quiz_gen.quiz_generator import (
    get_db_connection,
    generate_and_save_quiz,
)

load_dotenv()


# ==========================================
# 1. Lấy câu hỏi có sẵn trong DB theo subject + chapters
# ==========================================
def fetch_existing_questions_by_chapters(
    subject_id: int,
    chapter_ids: List[int],
    is_ai: Optional[bool] = None
) -> List[dict]:
    """
    Truy xuất các câu hỏi trong database liên quan đến subject và chapters cụ thể.
    Sử dụng cosine similarity giữa embedding câu hỏi và content_blocks của chapters.
    
    Params:
        subject_id: ID môn học.
        chapter_ids: Danh sách chapter IDs cần lấy câu hỏi.
        is_ai: Lọc theo is_ai (True/False/None=tất cả).
    
    Returns:
        Danh sách dict chứa thông tin câu hỏi (id, question_text, difficulty_level, is_ai).
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Tạo placeholder cho danh sách chapter_ids
        placeholders = ",".join(["%s"] * len(chapter_ids))

        # Điều kiện is_ai
        ai_condition = ""
        if is_ai is True:
            ai_condition = "AND q.is_ai = TRUE"
        elif is_ai is False:
            ai_condition = "AND q.is_ai = FALSE"

        query = f"""
            SELECT DISTINCT q.id, q.question_text, q.difficulty_level, q.is_ai
            FROM questions q
            JOIN question_bank qb ON q.bank_id = qb.id
            WHERE qb.subject_id = %s
            {ai_condition}
            AND EXISTS (
                SELECT 1
                FROM content_blocks cb
                JOIN subsections sub ON cb.subsection_id = sub.id
                JOIN sections s ON sub.section_id = s.id
                JOIN lessons l ON s.lesson_id = l.id
                WHERE l.chapter_id IN ({placeholders})
                AND (q.embedding <=> cb.embedding) < 0.5
            )
            ORDER BY q.id
        """

        params = [subject_id] + chapter_ids
        cur.execute(query, params)
        rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "question_text": row[1],
                "difficulty_level": row[2],
                "is_ai": row[3],
            }
            for row in rows
        ]
    finally:
        cur.close()
        conn.close()


# ==========================================
# 2. Tạo assignment và lưu vào DB
# ==========================================
def create_assignment(
    title: str,
    subject_id: int,
    chapter_ids: List[int],
    total_questions: int,
    num_ai_questions: int = 0,
    userid: int = None,
    classid: int = None,
    deadline: datetime = None,
) -> dict:
    """
    Tạo một assignment bằng cách tổng hợp câu hỏi từ database và câu hỏi AI.
    
    Params:
        title: Tiêu đề assignment.
        subject_id: ID môn học.
        chapter_ids: Danh sách chapter IDs cần lấy câu hỏi.
        total_questions: Tổng số câu hỏi trong assignment.
        num_ai_questions: Số câu hỏi tạo bằng AI (0 = chỉ lấy từ DB).
        userid: ID của người dùng (Giáo viên hoặc Học sinh) để gán bài kiểm tra và làm Bank.
        classid: ID lớp học (tùy chọn).
        deadline: Hạn nộp (tùy chọn).
    
    Returns:
        dict chứa thông tin assignment đã tạo.
    """
    if num_ai_questions > total_questions:
        raise ValueError("Số câu AI không được lớn hơn tổng số câu hỏi.")

    if num_ai_questions < 0:
        raise ValueError("Số câu AI không được âm.")

    num_db_questions = total_questions - num_ai_questions

    # ---- Bước 1: Lấy câu hỏi từ database (is_ai = False) ----
    selected_db_question_ids = []
    if num_db_questions > 0:
        print(f"Đang tìm {num_db_questions} câu hỏi có sẵn trong DB (is_ai=False)...")
        db_questions_non_ai = fetch_existing_questions_by_chapters(
            subject_id=subject_id,
            chapter_ids=chapter_ids,
            is_ai=False
        )

        selected_db = []
        if len(db_questions_non_ai) >= num_db_questions:
            selected_db = random.sample(db_questions_non_ai, num_db_questions)
        else:
            selected_db = db_questions_non_ai
            gap = num_db_questions - len(selected_db)
            print(f"[CẢNH BÁO] Chỉ tìm thấy {len(selected_db)} câu hỏi không-phải-AI. Đang lấy thêm {gap} câu hỏi có sẵn (is_ai=True) từ DB...")
            
            # Bù đắp bằng câu hỏi is_ai=True có sẵn
            db_questions_ai = fetch_existing_questions_by_chapters(
                subject_id=subject_id,
                chapter_ids=chapter_ids,
                is_ai=True
            )
            
            if len(db_questions_ai) >= gap:
                selected_db.extend(random.sample(db_questions_ai, gap))
            else:
                print(f"[CẢNH BÁO] DB chỉ có thêm {len(db_questions_ai)} câu hỏi AI có sẵn. Sẽ dùng tất cả.")
                selected_db.extend(db_questions_ai)

        selected_db_question_ids = [q["id"] for q in selected_db]
        print(f"Đã chọn {len(selected_db_question_ids)} câu hỏi từ DB (kết hợp nếu cần).")

    # ---- Bước 2: Tạo câu hỏi bằng AI (nếu cần) ----
    ai_question_ids = []
    if num_ai_questions > 0:
        if not userid:
            raise ValueError("Cần cung cấp userid để lưu câu hỏi AI gắn với ngân hàng của user.")
        print(f"Đang tạo thêm {num_ai_questions} câu hỏi CHƯA TỪNG CÓ BẰNG AI...")

        # Sử dụng chapter đầu tiên nếu có, hoặc subject_id
        result = generate_and_save_quiz(
            userid=userid,
            subject_id=subject_id,
            chapter_id=chapter_ids[0] if len(chapter_ids) == 1 else None,
            total_questions=num_ai_questions,
        )
        ai_question_ids = result["inserted_question_ids"]
        print(f"Đã tạo thêm {len(ai_question_ids)} câu hỏi AI mới.")

    # ---- Bước 3: Gộp tất cả question IDs ----
    all_question_ids = selected_db_question_ids + ai_question_ids
    if not all_question_ids:
        raise ValueError("Không có câu hỏi nào được chọn hoặc tạo ra.")

    # ---- Bước 4: Lưu assignment vào database ----
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        now = datetime.now()

        cur.execute(
            """
            INSERT INTO assignments (classid, userid, title, type, status, created_at, updated_at, deadline)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING assignmentid
            """,
            (
                classid,
                userid,
                title,
                "quiz",
                "draft",
                now,
                now,
                deadline,
            )
        )
        assignment_id = cur.fetchone()[0]

        # Link câu hỏi vào assignment
        for qid in all_question_ids:
            cur.execute(
                "INSERT INTO assignment_questions (assignmentid, questionid) VALUES (%s, %s)",
                (assignment_id, qid)
            )

        conn.commit()
        print(f"Đã tạo assignment (id={assignment_id}) với {len(all_question_ids)} câu hỏi.")

        return {
            "assignment_id": assignment_id,
            "title": title,
            "total_questions": len(all_question_ids),
            "db_question_ids": selected_db_question_ids,
            "ai_question_ids": ai_question_ids,
            "status": "draft",
        }

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Lỗi khi lưu assignment vào database: {e}")
    finally:
        cur.close()
        conn.close()


# ==========================================
# 3. CLI
# ==========================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Assignment Generator - Tạo bài tập từ câu hỏi DB + AI"
    )
    parser.add_argument("--title", type=str, required=True, help="Tiêu đề assignment")
    parser.add_argument("--subject-id", type=int, required=True, help="ID môn học")
    parser.add_argument(
        "--chapter-ids", type=int, nargs="+", required=True,
        help="Danh sách chapter IDs (có thể chọn nhiều, cách nhau bằng dấu cách)"
    )
    parser.add_argument("--total-questions", type=int, required=True, help="Tổng số câu hỏi")
    parser.add_argument(
        "--num-ai-questions", type=int, default=0,
        help="Số câu hỏi tạo bằng AI (mặc định 0 = chỉ lấy từ DB)"
    )
    parser.add_argument("--class-id", type=int, default=None, help="ID lớp học (tùy chọn)")
    parser.add_argument("--userid", type=int, required=True, help="ID người dùng (Học sinh/Giáo viên)")
    parser.add_argument("--deadline", type=str, default=None, help="Hạn nộp (format: YYYY-MM-DD HH:MM:SS)")

    args = parser.parse_args()

    # Parse deadline
    deadline = None
    if args.deadline:
        try:
            deadline = datetime.strptime(args.deadline, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            print("[LỖI] Deadline phải theo format: YYYY-MM-DD HH:MM:SS")
            exit(1)

    try:
        result = create_assignment(
            title=args.title,
            subject_id=args.subject_id,
            chapter_ids=args.chapter_ids,
            total_questions=args.total_questions,
            num_ai_questions=args.num_ai_questions,
            userid=args.userid,
            classid=args.class_id,
            deadline=deadline,
        )

        print("\n=== Kết quả ===")
        print(f"Assignment ID: {result['assignment_id']}")
        print(f"Tiêu đề: {result['title']}")
        print(f"Tổng số câu hỏi: {result['total_questions']}")
        print(f"Câu hỏi từ DB: {len(result['db_question_ids'])} - IDs: {result['db_question_ids']}")
        print(f"Câu hỏi AI: {len(result['ai_question_ids'])} - IDs: {result['ai_question_ids']}")
        print(f"Trạng thái: {result['status']}")

    except Exception as e:
        print(f"\n[LỖI]: {e}")
