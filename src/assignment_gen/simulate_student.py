"""
Simulate Student - Giả lập học sinh làm bài kiểm tra.

Script này tạo dữ liệu giả lập cho việc học sinh làm bài assignment:
- Tự động tạo học sinh nếu chưa có trong database.
- Lấy tất cả assignments hoặc assignment cụ thể.
- Giả lập câu trả lời (chọn ngẫu nhiên đáp án với xác suất đúng tùy chỉnh).
- Lưu kết quả vào submissions và submission_answers.
"""

import os
import random
from datetime import datetime, timedelta
from typing import List, Optional
import psycopg2
from dotenv import load_dotenv

load_dotenv()


# ==========================================
# 1. Database Connection
# ==========================================
def get_db_connection():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USERNAME", "postgres"),
        password=os.getenv("DB_PASSWORD", "")
    )
    return conn


# ==========================================
# 2. Tạo học sinh giả lập
# ==========================================
SAMPLE_STUDENTS = [
    {"full_name": "Nguyễn Văn An", "gender": "Nam", "date_of_birth": "2008-03-15"},
    {"full_name": "Trần Thị Bình", "gender": "Nữ", "date_of_birth": "2008-07-22"},
    {"full_name": "Lê Hoàng Cường", "gender": "Nam", "date_of_birth": "2008-01-10"},
    {"full_name": "Phạm Minh Dũng", "gender": "Nam", "date_of_birth": "2008-11-05"},
    {"full_name": "Hoàng Thị Em", "gender": "Nữ", "date_of_birth": "2008-09-18"},
    {"full_name": "Vũ Đức Phong", "gender": "Nam", "date_of_birth": "2008-06-30"},
    {"full_name": "Đặng Thu Giang", "gender": "Nữ", "date_of_birth": "2008-04-12"},
    {"full_name": "Bùi Quốc Huy", "gender": "Nam", "date_of_birth": "2008-08-25"},
    {"full_name": "Ngô Thị Lan", "gender": "Nữ", "date_of_birth": "2008-02-14"},
    {"full_name": "Đỗ Thanh Khoa", "gender": "Nam", "date_of_birth": "2008-12-01"},
]


def ensure_students(num_students: int = 5) -> List[int]:
    """
    Đảm bảo có đủ học sinh trong database.
    Tạo user và gán vào bảng students, trả về danh sách userid.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Lấy danh sách userid đã có trong bảng students
        cur.execute("SELECT userid FROM students WHERE userid IS NOT NULL ORDER BY userid")
        existing_ids = [row[0] for row in cur.fetchall()]

        if len(existing_ids) >= num_students:
            print(f"Đã có {len(existing_ids)} học sinh (users) trong DB, sử dụng {num_students} người.")
            return existing_ids[:num_students]

        # Tạo thêm học sinh
        num_to_create = num_students - len(existing_ids)
        
        cur.execute("SELECT COALESCE(MAX(userid), 0) FROM users")
        next_user_id = cur.fetchone()[0] + 1
        
        cur.execute("SELECT COALESCE(MAX(studentid), 0) FROM students")
        next_student_id = cur.fetchone()[0] + 1

        print(f"Đang tạo thêm {num_to_create} học sinh (users)...")
        new_ids = []
        for i in range(num_to_create):
            sample = SAMPLE_STUDENTS[i % len(SAMPLE_STUDENTS)]
            uid = next_user_id + i
            sid = next_student_id + i

            # Tạo user (Giả sử roleid = 3 là học sinh)
            cur.execute("INSERT INTO users (userid, roleid) VALUES (%s, %s)", (uid, 3))

            suffix = f" {(i // len(SAMPLE_STUDENTS)) + 1}" if i >= len(SAMPLE_STUDENTS) else ""
            full_name = sample["full_name"] + suffix

            cur.execute(
                """
                INSERT INTO students (studentid, userid, full_name, date_of_birth, gender)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (sid, uid, full_name, sample["date_of_birth"], sample["gender"])
            )
            new_ids.append(uid)

        conn.commit()
        all_ids = existing_ids + new_ids
        print(f"Tổng cộng {len(all_ids)} học sinh (đã tạo thêm {num_to_create}).")
        return all_ids[:num_students]

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Lỗi khi tạo học sinh: {e}")
    finally:
        cur.close()
        conn.close()


# ==========================================
# 3. Lấy thông tin assignment và câu hỏi
# ==========================================
def get_assignment_questions(assignment_id: int) -> List[dict]:
    """
    Lấy danh sách câu hỏi và đáp án của một assignment.
    
    Returns:
        List[dict] với mỗi dict chứa question info và danh sách answers.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT q.id, q.question_text, q.difficulty_level
            FROM assignment_questions aq
            JOIN questions q ON aq.questionid = q.id
            WHERE aq.assignmentid = %s
            ORDER BY q.id
            """,
            (assignment_id,)
        )
        questions = []
        for row in cur.fetchall():
            qid = row[0]
            # Lấy các đáp án cho câu hỏi
            cur.execute(
                """
                SELECT id, content, label, is_correct
                FROM answers
                WHERE question_id = %s
                ORDER BY label
                """,
                (qid,)
            )
            answers = [
                {
                    "id": a[0],
                    "content": a[1],
                    "label": a[2],
                    "is_correct": a[3],
                }
                for a in cur.fetchall()
            ]
            questions.append({
                "id": qid,
                "question_text": row[1],
                "difficulty_level": row[2],
                "answers": answers,
            })
        return questions
    finally:
        cur.close()
        conn.close()


def get_all_assignment_ids() -> List[int]:
    """Lấy tất cả assignment IDs trong database."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT assignmentid, title FROM assignments ORDER BY assignmentid")
        rows = cur.fetchall()
        for row in rows:
            print(f"  Assignment #{row[0]}: {row[1]}")
        return [row[0] for row in rows]
    finally:
        cur.close()
        conn.close()


# ==========================================
# 4. Giả lập làm bài
# ==========================================
def simulate_student_answer(answers: List[dict], correct_probability: float = 0.6) -> dict:
    """
    Giả lập học sinh chọn đáp án cho một câu hỏi.
    
    Params:
        answers: Danh sách đáp án (mỗi đáp án có id, label, is_correct).
        correct_probability: Xác suất chọn đúng (0.0 - 1.0).
    
    Returns:
        dict chứa answer_id, selected_label, is_correct.
    """
    if not answers:
        return None

    correct_answers = [a for a in answers if a["is_correct"]]
    wrong_answers = [a for a in answers if not a["is_correct"]]

    # Quyết định chọn đúng hay sai
    if random.random() < correct_probability and correct_answers:
        selected = random.choice(correct_answers)
    elif wrong_answers:
        selected = random.choice(wrong_answers)
    else:
        selected = random.choice(answers)

    return {
        "answer_id": selected["id"],
        "selected_label": selected["label"],
        "is_correct": selected["is_correct"],
    }


def simulate_submission(
    assignment_id: int,
    user_id: int,
    correct_probability: float = 0.6,
) -> dict:
    """
    Giả lập một học sinh (theo userid) làm một bài assignment.
    """
    questions = get_assignment_questions(assignment_id)
    if not questions:
        raise ValueError(f"Assignment #{assignment_id} không có câu hỏi nào.")

    # Giả lập thời gian làm bài (30s - 120s mỗi câu)
    time_taken = sum(random.randint(30, 120) for _ in questions)

    # Giả lập câu trả lời
    answers_result = []
    num_correct = 0
    for q in questions:
        result = simulate_student_answer(q["answers"], correct_probability)
        if result:
            if result["is_correct"]:
                num_correct += 1
            answers_result.append({
                "question_id": q["id"],
                **result,
            })

    # Tính điểm (thang 10)
    score = round((num_correct / len(questions)) * 10, 2) if questions else 0

    # Lưu vào database
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        submitted_at = datetime.now() - timedelta(minutes=random.randint(0, 60))

        cur.execute(
            """
            INSERT INTO submissions (assignmentid, userid, score, time_taken, submitted_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING submissionid
            """,
            (assignment_id, user_id, score, time_taken, submitted_at)
        )
        submission_id = cur.fetchone()[0]

        # Lưu từng câu trả lời (thêm answer_ref_id)
        for ans in answers_result:
            cur.execute(
                """
                INSERT INTO submission_answers (submissionid, questionid, answer_ref_id, selected_answer, is_correct)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    submission_id,
                    ans["question_id"],
                    ans["answer_id"], # Liên kết tới bảng answers theo yêu cầu DB mới
                    ans["selected_label"],
                    ans["is_correct"],
                )
            )

        conn.commit()

        return {
            "submission_id": submission_id,
            "assignment_id": assignment_id,
            "user_id": user_id,
            "score": score,
            "num_correct": num_correct,
            "total_questions": len(questions),
            "time_taken": time_taken,
        }

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Lỗi khi lưu submission: {e}")
    finally:
        cur.close()
        conn.close()


# ==========================================
# 5. Pipeline giả lập toàn bộ
# ==========================================
def simulate_all(
    assignment_ids: List[int] = None,
    user_ids: List[int] = None,
    num_students: int = 5,
    correct_probability: float = 0.6
) -> List[dict]:
    """
    Giả lập làm bài cho các học sinh cụ thể trên các assignments cụ thể.
    """
    # Nếu user_ids được set từ CLI trực tiếp, dùng luôn (bỏ qua num_students nếu có user_ids cụ thể)
    if user_ids:
        active_user_ids = user_ids
    else:
        # Nếu không có, tự get hoặc tạo
        active_user_ids = ensure_students(num_students)

    # Xác định assignments cần giả lập
    if not assignment_ids:
        print("Tìm tất cả assignments trong database:")
        assignment_ids = get_all_assignment_ids()
        if not assignment_ids:
            raise ValueError("Không tìm thấy assignment nào trong database.")

    all_results = []
    for a_id in assignment_ids:
        print(f"\n--- Giả lập Assignment #{a_id} ---")
        for u_id in active_user_ids:
            # Thay đổi xác suất nhẹ cho mỗi học sinh (tạo sự đa dạng)
            student_prob = max(0.1, min(0.95, correct_probability + random.uniform(-0.15, 0.15)))

            result = simulate_submission(
                assignment_id=a_id,
                user_id=u_id,
                correct_probability=student_prob,
            )
            all_results.append(result)
            print(
                f"  Học sinh (UserID {u_id}): "
                f"{result['num_correct']}/{result['total_questions']} đúng, "
                f"điểm = {result['score']}, "
                f"thời gian = {result['time_taken']}s"
            )

    return all_results


# ==========================================
# 6. CLI
# ==========================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Simulate Student - Giả lập học sinh làm bài kiểm tra")
    parser.add_argument(
        "--assignment-ids", type=int, nargs="+", default=None,
        help="Danh sách ID assignment cụ thể (nếu không chọn, giả lập tất cả assignments)"
    )
    parser.add_argument(
        "--user-ids", type=int, nargs="+", default=None,
        help="Danh sách ID học sinh (userid) cụ thể (nếu không nhập, tạo giả lập num-students)"
    )
    parser.add_argument(
        "--num-students", type=int, default=5,
        help="Số lượng học sinh sinh giả lập (mặc định 5). Bị bỏ qua nếu `--user-ids` có truyền vào."
    )
    parser.add_argument(
        "--correct-probability", type=float, default=0.6,
        help="Xác suất trả lời đúng trung bình (0.0 - 1.0, mặc định 0.6)"
    )

    args = parser.parse_args()

    try:
        results = simulate_all(
            assignment_ids=args.assignment_ids,
            user_ids=args.user_ids,
            num_students=args.num_students,
            correct_probability=args.correct_probability,
        )

        print("\n=== Tổng kết ===")
        print(f"Tổng số submissions: {len(results)}")
        if results:
            avg_score = sum(r["score"] for r in results) / len(results)
            print(f"Điểm trung bình: {avg_score:.2f}")

            # Thống kê theo assignment
            assignment_groups = {}
            for r in results:
                aid = r["assignment_id"]
                if aid not in assignment_groups:
                    assignment_groups[aid] = []
                assignment_groups[aid].append(r["score"])

            for aid, scores in assignment_groups.items():
                avg = sum(scores) / len(scores)
                print(f"  Assignment #{aid}: {len(scores)} submissions, điểm TB = {avg:.2f}")

    except Exception as e:
        print(f"\n[LỖI]: {e}")
