import os
import json
from typing import Dict, Any, Optional, List, Tuple
from openai import OpenAI
from dotenv import load_dotenv
import psycopg2

load_dotenv()

# ==========================================
# 1. Prompt Template Cấu hình
# ==========================================
PROMPT_TEMPLATE = """Bạn là một chuyên gia giáo dục. Hãy tạo bài trắc nghiệm dựa trên đoạn văn bản được cung cấp.

Yêu cầu sinh câu hỏi:
- Tạo ĐÚNG {num_questions} câu hỏi trắc nghiệm liên quan đến nội dung văn bản.
- Phân bổ độ khó bắt buộc như sau:
  + {num_level_1} câu mức độ 1 (Dễ)
  + {num_level_2} câu mức độ 2 (Trung bình)
  + {num_level_3} câu mức độ 3 (Khó)
- Mỗi câu hỏi có đúng 4 đáp án (A, B, C, D).
- Chỉ có đúng 1 đáp án đúng cho mỗi câu.
- Kèm theo giải thích chi tiết cho đáp án đúng.
- Trả về độ khó (`difficulty_level`) là SỐ NGUYÊN (1, 2, hoặc 3).
- Không được trả về bất kỳ văn bản nào ngoài chuẩn JSON. 
- Không sử dụng định dạng markdown (ví dụ: không dùng ```json). 
- Không thêm bất kỳ chú thích nào.
{existing_questions_section}

Format kết quả BẮT BUỘC trả về dưới dạng JSON chính xác như sau:
{{
  "quiz_id": "quiz_001",
  "questions": [
    {{
      "question_id": 1,
      "question_text": "Nội dung câu hỏi?",
      "options": {{
        "A": "Đáp án A",
        "B": "Đáp án B",
        "C": "Đáp án C",
        "D": "Đáp án D"
      }},
      "correct_answer": "A",
      "explanation": "Giải thích vì sao đáp án lại đúng.",
      "difficulty_level": 1
    }}
  ]
}}

Văn bản đầu vào:
{text}
"""

# ==========================================
# 2. Database Connection
# ==========================================
def get_db_connection():
    """
    Tạo kết nối PostgreSQL sử dụng biến môi trường.
    """
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        database=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USERNAME", "postgres"),
        password=os.getenv("DB_PASSWORD", "")
    )
    return conn


# ==========================================
# 3. Hàm truy xuất lý thuyết từ Database
# ==========================================
def _parse_content_rows(rows) -> List[Dict[str, Any]]:
    """Helper: chuyển các row từ DB thành danh sách dict."""
    results = []
    for row in rows:
        results.append({
            "book_name": row[0],
            "chapter_number": row[1],
            "chapter_title": row[2],
            "lesson_number": row[3],
            "lesson_title": row[4],
            "section_number": row[5],
            "section_title": row[6],
            "subsection_number": row[7],
            "subsection_title": row[8],
            "content": row[9],
            "content_block_id": row[10],
        })
    return results


_CONTENT_SELECT = """
    SELECT 
        b.book_name,
        ch.chapter_number, ch.title AS chapter_title,
        l.lesson_number, l.title AS lesson_title,
        s.section_number, s.section_title,
        sub.subsection_number, sub.subsection_title,
        cb.content, cb.id AS content_block_id
    FROM content_blocks cb
    JOIN subsections sub ON cb.subsection_id = sub.id
    JOIN sections s ON sub.section_id = s.id
    JOIN lessons l ON s.lesson_id = l.id
    JOIN chapters ch ON l.chapter_id = ch.id
    JOIN books b ON ch.book_id = b.id
"""


def fetch_content_by_subject(subject_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            _CONTENT_SELECT + """
            WHERE b.subject_id = %s
            ORDER BY b.id, ch.chapter_number, l.lesson_number,
                     s.section_number, sub.subsection_number, cb.id
            """,
            (subject_id,)
        )
        return _parse_content_rows(cur.fetchall())
    finally:
        cur.close()
        conn.close()


def fetch_content_by_book(book_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            _CONTENT_SELECT + """
            WHERE b.id = %s
            ORDER BY ch.chapter_number, l.lesson_number,
                     s.section_number, sub.subsection_number, cb.id
            """,
            (book_id,)
        )
        return _parse_content_rows(cur.fetchall())
    finally:
        cur.close()
        conn.close()


def fetch_content_by_chapter(chapter_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            _CONTENT_SELECT + """
            WHERE ch.id = %s
            ORDER BY l.lesson_number, s.section_number,
                     sub.subsection_number, cb.id
            """,
            (chapter_id,)
        )
        return _parse_content_rows(cur.fetchall())
    finally:
        cur.close()
        conn.close()


def fetch_content_by_lesson(lesson_id: int) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            _CONTENT_SELECT + """
            WHERE l.id = %s
            ORDER BY s.section_number, sub.subsection_number, cb.id
            """,
            (lesson_id,)
        )
        return _parse_content_rows(cur.fetchall())
    finally:
        cur.close()
        conn.close()


def build_theory_text(content_blocks: List[Dict[str, Any]]) -> str:
    if not content_blocks:
        return ""
    
    text_parts = []
    current_book = None
    current_chapter = None
    current_lesson = None
    current_section = None

    for block in content_blocks:
        book_key = block["book_name"]
        if book_key != current_book:
            current_book = book_key
            current_chapter = None
            current_lesson = None
            current_section = None
            text_parts.append(f"\n=== Tài liệu: {block['book_name']} ===")

        chapter_key = block["chapter_number"]
        if chapter_key != current_chapter:
            current_chapter = chapter_key
            text_parts.append(f"\n--- Chương {block['chapter_number']}: {block['chapter_title']} ---")

        lesson_key = block["lesson_number"]
        if lesson_key != current_lesson:
            current_lesson = lesson_key
            text_parts.append(f"\nBài {block['lesson_number']}: {block['lesson_title']}")

        section_key = block["section_number"]
        if section_key != current_section:
            current_section = section_key
            text_parts.append(f"\n{block['section_number']}. {block['section_title']}")

        text_parts.append(block["content"])

    return "\n".join(text_parts)


# ==========================================
# 3b. Xử lý User, Subject và Bank
# ==========================================
def fetch_existing_ai_questions_by_bank(bank_id: int) -> List[str]:
    """Lấy các câu hỏi đã sinh trong ngân hàng này để tránh lặp."""
    if not bank_id:
        return []
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT question_text
            FROM questions
            WHERE bank_id = %s AND is_ai = TRUE
            """,
            (bank_id,)
        )
        rows = cur.fetchall()
        return [row[0] for row in rows]
    finally:
        cur.close()
        conn.close()


def _get_subject_id_from_book(book_id: int) -> Optional[int]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT subject_id FROM books WHERE id = %s", (book_id,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()
        conn.close()


def _get_subject_id_from_chapter(chapter_id: int) -> Optional[int]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT b.subject_id
            FROM chapters ch
            JOIN books b ON ch.book_id = b.id
            WHERE ch.id = %s
            """,
            (chapter_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()
        conn.close()

def _get_subject_id_from_lesson(lesson_id: int) -> Optional[int]:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT b.subject_id
            FROM lessons l
            JOIN chapters ch ON l.chapter_id = ch.id
            JOIN books b ON ch.book_id = b.id
            WHERE l.id = %s
            """,
            (lesson_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()
        conn.close()


def get_or_create_question_bank(userid: int, subject_id: int) -> int:
    """Tạo hoặc lấy ra question_bank của userid với môn học."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Tự động đảm bảo userid tồn tại trong bảng users
        cur.execute("SELECT userid FROM users WHERE userid = %s", (userid,))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (userid, roleid) VALUES (%s, %s)", (userid, 3)) # Tạo roleid tạm

        cur.execute(
            "SELECT id FROM question_bank WHERE userid = %s AND subject_id = %s",
            (userid, subject_id)
        )
        row = cur.fetchone()
        if row:
            return row[0]
        
        # Lấy tên môn học
        cur.execute("SELECT subject_name FROM subjects WHERE subject_id = %s", (subject_id,))
        subject_row = cur.fetchone()
        subject_name = subject_row[0] if subject_row else f"Subject_{subject_id}"

        cur.execute(
            "INSERT INTO question_bank (bank_name, userid, subject_id) VALUES (%s, %s, %s) RETURNING id",
            (f"Bank - User {userid} - {subject_name}", userid, subject_id)
        )
        bank_id = cur.fetchone()[0]
        conn.commit()
        return bank_id
    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Lỗi tạo/lấy question bank: {e}")
    finally:
        cur.close()
        conn.close()


def _build_existing_questions_section(existing_questions: List[str]) -> str:
    if not existing_questions:
        return ""
    
    questions_list = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(existing_questions))
    return (
        f"\n"
        f"QUAN TRỌNG - Các câu hỏi sau đã có trong ngân hàng, hãy RẤT TRÁNH tạo lại câu hỏi tương tự:\n"
        f"{questions_list}\n"
    )


def calculate_difficulty_distribution(total: int, l1: Optional[int], l2: Optional[int], l3: Optional[int]) -> Dict[int, int]:
    """Tính toán số lượng mỗi độ khó cần tạo."""
    dist = {1: l1 or 0, 2: l2 or 0, 3: l3 or 0}
    
    provided = sum(dist.values())
    
    if provided > total:
        print("[Cảnh báo] Tổng số lượng chỉ định theo độ khó vượt qua total. Cập nhật total.")
        total = provided
        
    remaining = total - provided
    
    # Logic phân phát: Ưu tiên thêm vào level 2, sau đó là 1, cuối là 3 
    # Mức độ 1 có thể nhiều ngang 2, mức 3 luôn chiếm ít hơn
    while remaining > 0:
        if dist[2] <= dist[1] and dist[2] <= dist[3] * 2 + 1:
            dist[2] += 1
        elif dist[1] <= dist[3] * 2 + 1:
            dist[1] += 1
        else:
            dist[3] += 1
        remaining -= 1
        
    return dist


# ==========================================
# 4. Service gọi OpenAI API
# ==========================================
class QuizGeneratorService:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("Không tìm thấy OPENAI_API_KEY.")
        self.client = OpenAI(api_key=self.api_key)

    def _validate_quiz_schema(self, quiz_data: dict) -> bool:
        if "questions" not in quiz_data:
            return False
            
        questions = quiz_data.get("questions", [])
        if not isinstance(questions, list) or len(questions) == 0:
            return False
            
        for q in questions:
            required_keys = {"question_id", "question_text", "options", "correct_answer", "explanation", "difficulty_level"}
            if not required_keys.issubset(q.keys()):
                return False
            if q["difficulty_level"] not in [1, 2, 3]:
                return False
                
            options = q.get("options", {})
            if not isinstance(options, dict) or not {"A", "B", "C", "D"}.issubset(options.keys()):
                return False
                
        return True

    def generate(self, text: str, dist: dict, existing_questions: List[str] = None, retries: int = 1) -> dict:
        total = sum(dist.values())
        existing_section = _build_existing_questions_section(existing_questions or [])
        prompt = PROMPT_TEMPLATE.format(
            num_questions=total,
            num_level_1=dist[1],
            num_level_2=dist[2],
            num_level_3=dist[3],
            text=text,
            existing_questions_section=existing_section
        )

        for attempt in range(retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant designed to output strictly valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                )
                
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("OpenAI API trả về nội dung rỗng.")

                quiz_data = json.loads(content)
                
                if not self._validate_quiz_schema(quiz_data):
                    raise ValueError("JSON trả về thiếu các trường bắt buộc, cấu trúc không hợp lệ, hoặc difficulty_level không phải 1,2,3.")
                    
                return quiz_data

            except Exception as e:
                print(f"[Attempt {attempt + 1}/{retries + 1}] Lỗi sinh câu hỏi: {e}")
                if attempt == retries:
                    raise RuntimeError(f"Sinh câu hỏi thất bại sau {retries + 1} lần thử: {str(e)}")


def generate_quiz(text: str, dist: dict, existing_questions: List[str] = None) -> dict:
    service = QuizGeneratorService()
    return service.generate(text=text, dist=dist, existing_questions=existing_questions)


# ==========================================
# 6. Lưu câu hỏi AI vào Database
# ==========================================
def save_quiz_to_db(quiz_data: dict, bank_id: int) -> List[int]:
    """Lưu bộ câu hỏi vào database trực tiếp liên kết với bank_id."""
    conn = get_db_connection()
    cur = conn.cursor()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    inserted_question_ids = []

    try:
        questions = quiz_data.get("questions", [])

        for q in questions:
            question_text = q["question_text"]
            explanation = q.get("explanation", "")
            correct_answer = q["correct_answer"]
            options = q["options"]
            diff_level = q.get("difficulty_level", 2)

            # Sinh embedding
            response = client.embeddings.create(
                model="text-embedding-3-large",
                input=question_text
            )
            embedding = response.data[0].embedding

            # Insert vào database, is_ai = TRUE
            cur.execute(
                """
                INSERT INTO questions 
                    (question_text, image_url, explanation, difficulty_level, embedding, bank_id, is_ai)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    question_text,
                    None,           # image_url
                    explanation,
                    diff_level,
                    embedding,
                    bank_id,
                    True
                )
            )
            question_id = cur.fetchone()[0]
            inserted_question_ids.append(question_id)

            for label in ["A", "B", "C", "D"]:
                content = options.get(label, "")
                is_correct = (label == correct_answer)

                cur.execute(
                    """
                    INSERT INTO answers (content, label, is_correct, question_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (content, label, is_correct, question_id)
                )

        conn.commit()
        print(f"Đã lưu {len(inserted_question_ids)} câu hỏi AI vào database (Bank ID: {bank_id}).")
        return inserted_question_ids

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Lỗi lưu DB: {e}")
    finally:
        cur.close()
        conn.close()


# ==========================================
# 8. Pipeline Hoàn Chỉnh
# ==========================================
def generate_and_save_quiz(
    userid: int,
    subject_id: int = None,
    book_id: int = None,
    chapter_id: int = None,
    lesson_id: int = None,
    total_questions: int = 10,
    level_1: int = None,
    level_2: int = None,
    level_3: int = None
) -> dict:
    
    # 1. Resolve Subject ID & Lấy Theory Text
    if lesson_id:
        resolved_subject_id = subject_id or _get_subject_id_from_lesson(lesson_id)
        content_blocks = fetch_content_by_lesson(lesson_id)
    elif chapter_id:
        resolved_subject_id = subject_id or _get_subject_id_from_chapter(chapter_id)
        content_blocks = fetch_content_by_chapter(chapter_id)
    elif book_id:
        resolved_subject_id = subject_id or _get_subject_id_from_book(book_id)
        content_blocks = fetch_content_by_book(book_id)
    elif subject_id:
        resolved_subject_id = subject_id
        content_blocks = fetch_content_by_subject(subject_id)
    else:
        raise ValueError("Phải cung cấp ít nhất một trong: subject_id, book_id, chapter_id, lesson_id.")

    if not resolved_subject_id:
        raise ValueError("Không xác định được môn học (subject_id). Dữ liệu lỗi hoặc chưa có.")
    
    if not content_blocks:
        raise ValueError("Không tìm thấy nội dung lý thuyết cho nguồn đã cho.")

    theory_text = build_theory_text(content_blocks)
    
    # 2. Bank ID và chống trùng
    bank_id = get_or_create_question_bank(userid, resolved_subject_id)
    existing_questions = fetch_existing_ai_questions_by_bank(bank_id)
    
    # 3. Tính toán phân bổ
    dist = calculate_difficulty_distribution(total_questions, level_1, level_2, level_3)
    print(f"Sẽ tạo {sum(dist.values())} câu hỏi. Phân bổ: Dễ: {dist[1]}, TB: {dist[2]}, Khó: {dist[3]}")

    # 4. Sinh AI
    quiz_data = generate_quiz(text=theory_text, dist=dist, existing_questions=existing_questions)

    # 5. Lưu vào database trực tiếp với bank_id
    question_ids = save_quiz_to_db(quiz_data=quiz_data, bank_id=bank_id)

    return {
        "quiz_data": quiz_data,
        "inserted_question_ids": question_ids,
        "total_content_blocks": len(content_blocks),
        "bank_id": bank_id,
        "subject_id": resolved_subject_id,
        "distribution": dist
    }


# ==========================================
# 9. CLI Interface
# ==========================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI Quiz Generator theo User Bank")
    parser.add_argument("--userid", type=int, required=True, help="ID của User (Học sinh/Giáo viên) để gán Bank")
    parser.add_argument("--subject-id", type=int, default=None, help="Lấy từ subject_id")
    parser.add_argument("--book-id", type=int, default=None, help="Lấy từ book_id")
    parser.add_argument("--chapter-id", type=int, default=None, help="Lấy từ chapter_id")
    parser.add_argument("--lesson-id", type=int, default=None, help="Lấy từ lesson_id (mới)")
    
    parser.add_argument("--total-questions", type=int, default=10, help="Tổng câu")
    parser.add_argument("--level-1", type=int, default=None, help="Câu mức 1 (Dễ)")
    parser.add_argument("--level-2", type=int, default=None, help="Câu mức 2 (Trung bình)")
    parser.add_argument("--level-3", type=int, default=None, help="Câu mức 3 (Khó)")

    args = parser.parse_args()

    try:
        result = generate_and_save_quiz(
            userid=args.userid,
            subject_id=args.subject_id,
            book_id=args.book_id,
            chapter_id=args.chapter_id,
            lesson_id=args.lesson_id,
            total_questions=args.total_questions,
            level_1=args.level_1,
            level_2=args.level_2,
            level_3=args.level_3
        )

        print("\n=== Kết quả ===")
        print(f"Bank ID: {result['bank_id']}")
        print(f"Số lượng lưu: {len(result['inserted_question_ids'])}")
        print(f"Question IDs: {result['inserted_question_ids']}")

    except Exception as e:
        print(f"\n[LỖI]: {e}")