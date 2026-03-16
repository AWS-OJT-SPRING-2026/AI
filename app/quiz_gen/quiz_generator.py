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
- Tạo từ {num_questions} câu hỏi trắc nghiệm liên quan đến nội dung văn bản.
- Mỗi câu hỏi có đúng 4 đáp án (A, B, C, D).
- Chỉ có đúng 1 đáp án đúng cho mỗi câu.
- Kèm theo giải thích chi tiết cho đáp án đúng.
- Không được trả về bất kỳ văn bản nào ngoài chuẩn JSON. 
- Không sử dụng định dạng markdown (ví dụ: không dùng ```json). 
- Không thêm bất kỳ chú thích nào.
{existing_questions_section}
Format kết quả BẮT BUỘC trả về dưới dạng JSON chính xác như sau:
{{
  "quiz_id": "quiz_001",
  "topic": "Chủ đề chính của đoạn văn",
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
      "explanation": "Giải thích vì sao đáp án lại đúng."
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
        host="localhost",
        database=os.getenv("DATABASE_NAME"),
        user="postgres",
        password=os.getenv("POSTGRESQL_PASSWORD")
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
    """
    Truy xuất tất cả content_blocks của một môn học (subject_id).
    Tổng hợp lý thuyết từ TẤT CẢ các cuốn sách thuộc môn đó.
    """
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
    """
    Truy xuất tất cả content_blocks của một cuốn sách (book_id).
    """
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
    """
    Truy xuất tất cả content_blocks của một chương (chapter_id).
    """
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


def build_theory_text(content_blocks: List[Dict[str, Any]]) -> str:
    """
    Ghép tất cả content_blocks thành một chuỗi văn bản lý thuyết 
    để đưa vào prompt cho OpenAI.
    """
    if not content_blocks:
        return ""
    
    text_parts = []
    current_book = None
    current_chapter = None
    current_lesson = None
    current_section = None

    for block in content_blocks:
        # Thêm header sách nếu chuyển sách mới (khi dùng subject_id, có nhiều sách)
        book_key = block["book_name"]
        if book_key != current_book:
            current_book = book_key
            current_chapter = None
            current_lesson = None
            current_section = None
            text_parts.append(f"\n=== Tài liệu: {block['book_name']} ===")

        # Thêm header chương nếu chuyển chương mới
        chapter_key = block["chapter_number"]
        if chapter_key != current_chapter:
            current_chapter = chapter_key
            text_parts.append(f"\n--- Chương {block['chapter_number']}: {block['chapter_title']} ---")

        # Thêm header bài học nếu chuyển bài mới
        lesson_key = block["lesson_number"]
        if lesson_key != current_lesson:
            current_lesson = lesson_key
            text_parts.append(f"\nBài {block['lesson_number']}: {block['lesson_title']}")

        # Thêm header mục nếu chuyển mục mới
        section_key = block["section_number"]
        if section_key != current_section:
            current_section = section_key
            text_parts.append(f"\n{block['section_number']}. {block['section_title']}")

        # Thêm nội dung
        text_parts.append(block["content"])

    return "\n".join(text_parts)


# ==========================================
# 3b. Truy xuất câu hỏi AI đã tạo trước đó theo subject_id
# ==========================================
def fetch_existing_ai_questions_by_subject(subject_id: int) -> List[str]:
    """
    Truy xuất các câu hỏi AI đã tạo trước đó liên quan đến nội dung của môn học.
    Sử dụng cosine similarity giữa embedding câu hỏi và embedding content_blocks
    của tất cả sách thuộc môn đó.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT q.question_text
            FROM questions q
            WHERE q.is_ai = TRUE
            AND EXISTS (
                SELECT 1
                FROM content_blocks cb
                JOIN subsections sub ON cb.subsection_id = sub.id
                JOIN sections s ON sub.section_id = s.id
                JOIN lessons l ON s.lesson_id = l.id
                JOIN chapters ch ON l.chapter_id = ch.id
                JOIN books b ON ch.book_id = b.id
                WHERE b.subject_id = %s
                AND (q.embedding <=> cb.embedding) < 0.5
            )
            """,
            (subject_id,)
        )
        rows = cur.fetchall()
        return [row[0] for row in rows]
    finally:
        cur.close()
        conn.close()


def _get_subject_id_from_book(book_id: int) -> Optional[int]:
    """Lấy subject_id từ book_id."""
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
    """Lấy subject_id từ chapter_id."""
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


def _build_existing_questions_section(existing_questions: List[str]) -> str:
    """
    Tạo phần prompt liệt kê các câu hỏi đã có để AI tránh tạo trùng.
    """
    if not existing_questions:
        return ""
    
    questions_list = "\n".join(f"  {i+1}. {q}" for i, q in enumerate(existing_questions))
    return (
        f"\n"
        f"QUAN TRỌNG - Các câu hỏi sau đã được tạo trước đó. "
        f"KHÔNG ĐƯỢC tạo câu hỏi trùng lặp hoặc tương tự với bất kỳ câu nào dưới đây:\n"
        f"{questions_list}\n"
    )


# ==========================================
# 4. Service gọi OpenAI API
# ==========================================
class QuizGeneratorService:
    def __init__(self, api_key: Optional[str] = None):
        """
        Khởi tạo service với API key.
        Nếu không truyền vào, hệ thống tự động đọc từ biến môi trường OPENAI_API_KEY.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("Không tìm thấy OPENAI_API_KEY. Vui lòng thiết lập biến môi trường hoặc đưa qua tham số.")
        
        # Khởi tạo client của openai>=1.0.0
        self.client = OpenAI(api_key=self.api_key)

    def _validate_quiz_schema(self, quiz_data: dict) -> bool:
        """
        Hàm validate schema cơ bản để đảm bảo output đúng cấu trúc yêu cầu.
        """
        if "quiz_id" not in quiz_data or "topic" not in quiz_data or "questions" not in quiz_data:
            return False
            
        questions = quiz_data.get("questions", [])
        if not isinstance(questions, list) or len(questions) == 0:
            return False
            
        for q in questions:
            required_keys = {"question_id", "question_text", "options", "correct_answer", "explanation"}
            if not required_keys.issubset(q.keys()):
                return False
                
            options = q.get("options", {})
            if not isinstance(options, dict) or not {"A", "B", "C", "D"}.issubset(options.keys()):
                return False
                
        return True

    def generate(self, text: str, num_questions: int = 5, existing_questions: List[str] = None, retries: int = 1) -> dict:
        """
        Gửi request đến OpenAI để sinh câu hỏi.
        Nếu JSON bị lỗi format, hệ thống sẽ retry theo số lần chỉ định (mặc định 1 lần).
        existing_questions: danh sách câu hỏi đã tạo trước đó cần tránh.
        """
        existing_section = _build_existing_questions_section(existing_questions or [])
        prompt = PROMPT_TEMPLATE.format(
            num_questions=num_questions,
            text=text,
            existing_questions_section=existing_section
        )

        # Vòng lặp bao gồm cả lần gọi ban đầu và các lần retries bổ sung
        for attempt in range(retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini", # Có thể thay đổi thành gpt-4o tùy chất lượng mong muốn
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant designed to output strictly valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}, # Đảm bảo output luôn dưới định dạng JSON
                    temperature=0.7,
                )
                
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("OpenAI API trả về nội dung rỗng.")

                # Parse JSON string thành Dictionary của Python
                quiz_data = json.loads(content)
                
                # Kiểm định JSON output có đúng format ta đã yêu cầu chưa
                if not self._validate_quiz_schema(quiz_data):
                    raise ValueError("JSON trả về thiếu các trường bắt buộc hoặc cấu trúc không hợp lệ.")
                    
                return quiz_data

            except json.JSONDecodeError as e:
                print(f"[Attempt {attempt + 1}/{retries + 1}] Lỗi parse JSON: {e}")
                if attempt == retries:
                    raise RuntimeError(f"Sinh câu hỏi thất bại sau {retries + 1} lần thử do lỗi định dạng JSON.")
            except ValueError as e:
                print(f"[Attempt {attempt + 1}/{retries + 1}] Lỗi Schema/Data: {e}")
                if attempt == retries:
                    raise RuntimeError(f"Sinh câu hỏi thất bại sau {retries + 1} lần thử: {str(e)}")
            except Exception as e:
                print(f"[Attempt {attempt + 1}/{retries + 1}] Lỗi từ OpenAI API: {e}")
                if attempt == retries:
                    raise RuntimeError(f"Gọi OpenAI API thất bại: {str(e)}")


# ==========================================
# 5. Hàm giao tiếp chính (Main Wrapper)
# ==========================================
def generate_quiz(text: str, num_questions: int = 5, existing_questions: List[str] = None) -> dict:
    """
    Hàm giao tiếp (wrapper) dùng để tích hợp một cách nhanh chóng.
    Nhận vào `text`, số lượng câu hỏi, và danh sách câu hỏi cần tránh.
    """
    service = QuizGeneratorService()
    return service.generate(text=text, num_questions=num_questions, existing_questions=existing_questions)


# ==========================================
# 6. Lưu câu hỏi AI vào Database
# ==========================================
def save_quiz_to_db(quiz_data: dict, topic_id: int) -> List[int]:
    """
    Lưu bộ câu hỏi được AI tạo ra vào database.
    - Mỗi question được insert vào bảng `questions` với is_ai = TRUE.
    - Mỗi answer (A, B, C, D) được insert vào bảng `answers`.
    - Embedding được tạo cho mỗi question_text bằng OpenAI.
    
    Trả về danh sách question IDs đã được insert.
    """
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

            # Sinh embedding cho câu hỏi
            response = client.embeddings.create(
                model="text-embedding-3-large",
                input=question_text
            )
            embedding = response.data[0].embedding

            # Insert vào bảng questions với is_ai = TRUE
            cur.execute(
                """
                INSERT INTO questions 
                    (question_text, image_url, explanation, difficulty_level, embedding, topic_id, is_ai)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    question_text,
                    None,           # image_url: AI không tạo hình ảnh
                    explanation,
                    "medium",       # difficulty_level mặc định
                    embedding,
                    topic_id,
                    True            # is_ai = TRUE theo yêu cầu README
                )
            )
            question_id = cur.fetchone()[0]
            inserted_question_ids.append(question_id)

            # Insert đáp án vào bảng answers
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
        print(f"Đã lưu {len(inserted_question_ids)} câu hỏi AI vào database.")
        return inserted_question_ids

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Lỗi khi lưu quiz vào database: {e}")
    finally:
        cur.close()
        conn.close()


# ==========================================
# 7. Tự động tạo Topic nếu chưa có
# ==========================================
def get_or_create_topic(topic_name: str, bank_id: int = None, subject_id: int = None) -> int:
    """
    Tìm topic theo tên, nếu chưa có thì tự động tạo mới.
    Nếu bank_id không được cung cấp, sẽ tự tạo một question_bank mới (kèm subject_id nếu có).
    
    Returns:
        topic_id đã tồn tại hoặc mới tạo.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Kiểm tra topic đã tồn tại chưa
        cur.execute(
            "SELECT id FROM topics WHERE topic_name = %s",
            (topic_name,)
        )
        row = cur.fetchone()
        if row:
            print(f"Đã tìm thấy topic '{topic_name}' với id = {row[0]}")
            return row[0]

        # Nếu chưa có bank_id, tạo question_bank mới (kèm subject_id)
        if not bank_id:
            cur.execute(
                "INSERT INTO question_bank (bank_name, subject_id) VALUES (%s, %s) RETURNING id",
                (f"AI Generated - {topic_name}", subject_id)
            )
            bank_id = cur.fetchone()[0]
            print(f"Đã tạo question_bank mới với id = {bank_id}")

        # Tạo topic mới
        cur.execute(
            "INSERT INTO topics (topic_name, bank_id) VALUES (%s, %s) RETURNING id",
            (topic_name, bank_id)
        )
        topic_id = cur.fetchone()[0]
        conn.commit()
        print(f"Đã tạo topic mới '{topic_name}' với id = {topic_id}")
        return topic_id

    except Exception as e:
        conn.rollback()
        raise RuntimeError(f"Lỗi khi tạo topic: {e}")
    finally:
        cur.close()
        conn.close()


# ==========================================
# 8. Pipeline: Lấy lý thuyết → Sinh quiz → Lưu DB
# ==========================================
def generate_and_save_quiz(
    topic_id: int = None,
    subject_id: int = None,
    book_id: int = None,
    chapter_id: int = None,
    num_questions: int = 5
) -> dict:
    """
    Pipeline hoàn chỉnh:
    1. Truy xuất lý thuyết từ database (theo subject_id, book_id, hoặc chapter_id).
    2. Sinh câu hỏi trắc nghiệm bằng OpenAI.
    3. Lưu câu hỏi vào database với is_ai = TRUE.
    
    Params:
        topic_id: ID của topic (tùy chọn). Nếu không có, sẽ tự tạo topic mới.
        subject_id: Lấy lý thuyết tổng hợp từ tất cả sách thuộc môn học.
        book_id: Lấy lý thuyết theo cuốn sách.
        chapter_id: Lấy lý thuyết theo chương.
        num_questions: Số lượng câu hỏi muốn tạo (mặc định 5).
    
    Returns:
        dict chứa quiz_data và danh sách question_ids đã lưu.
    """
    # Bước 1: Truy xuất lý thuyết từ database
    if chapter_id:
        content_blocks = fetch_content_by_chapter(chapter_id)
    elif book_id:
        content_blocks = fetch_content_by_book(book_id)
    elif subject_id:
        content_blocks = fetch_content_by_subject(subject_id)
    else:
        raise ValueError("Phải cung cấp ít nhất một trong: subject_id, book_id, hoặc chapter_id.")

    if not content_blocks:
        raise ValueError("Không tìm thấy nội dung lý thuyết trong database với ID đã cho.")

    # Ghép content thành văn bản lý thuyết
    theory_text = build_theory_text(content_blocks)
    print(f"Đã truy xuất {len(content_blocks)} content blocks từ database.")

    # Bước 1b: Xác định subject_id và lấy câu hỏi đã tạo trước đó
    resolved_subject_id = subject_id
    if not resolved_subject_id and book_id:
        resolved_subject_id = _get_subject_id_from_book(book_id)
    elif not resolved_subject_id and chapter_id:
        resolved_subject_id = _get_subject_id_from_chapter(chapter_id)

    existing_questions = []
    if resolved_subject_id:
        existing_questions = fetch_existing_ai_questions_by_subject(resolved_subject_id)
        if existing_questions:
            print(f"Tìm thấy {len(existing_questions)} câu hỏi đã tạo trước đó cho môn này. Sẽ tránh trùng lặp.")

    # Bước 2: Sinh câu hỏi trắc nghiệm
    print("Đang tạo câu hỏi trắc nghiệm bằng OpenAI API...")
    quiz_data = generate_quiz(text=theory_text, num_questions=num_questions, existing_questions=existing_questions)

    # Bước 3: Nếu chưa có topic_id, tự tạo topic từ tên chủ đề AI trả về
    if not topic_id:
        topic_name = quiz_data.get("topic", "AI Generated Quiz")
        topic_id = get_or_create_topic(topic_name=topic_name, subject_id=resolved_subject_id)

    # Bước 4: Lưu vào database
    question_ids = save_quiz_to_db(quiz_data=quiz_data, topic_id=topic_id)

    return {
        "quiz_data": quiz_data,
        "inserted_question_ids": question_ids,
        "total_content_blocks": len(content_blocks),
        "topic_id": topic_id,
        "subject_id": resolved_subject_id
    }


# ==========================================
# 9. Ví dụ sử dụng khi chạy trực tiếp file
# ==========================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Quiz Generator - Tạo câu hỏi trắc nghiệm từ lý thuyết trong DB")
    parser.add_argument("--topic-id", type=int, default=None, help="ID của topic (tùy chọn, nếu không có sẽ tự tạo mới)")
    parser.add_argument("--subject-id", type=int, default=None, help="ID môn học - lấy lý thuyết tổng hợp từ tất cả sách của môn")
    parser.add_argument("--book-id", type=int, default=None, help="ID cuốn sách để lấy lý thuyết")
    parser.add_argument("--chapter-id", type=int, default=None, help="ID chương để lấy lý thuyết")
    parser.add_argument("--num-questions", type=int, default=5, help="Số lượng câu hỏi muốn tạo (mặc định 5)")

    args = parser.parse_args()

    try:
        result = generate_and_save_quiz(
            topic_id=args.topic_id,
            subject_id=args.subject_id,
            book_id=args.book_id,
            chapter_id=args.chapter_id,
            num_questions=args.num_questions,
        )

        print("\n=== Kết quả ===")
        print(f"Subject ID: {result['subject_id']}")
        print(f"Topic ID: {result['topic_id']}")
        print(f"Số content blocks đã truy xuất: {result['total_content_blocks']}")
        print(f"Số câu hỏi đã lưu: {len(result['inserted_question_ids'])}")
        print(f"Question IDs: {result['inserted_question_ids']}")
        print("\nQuiz JSON:")
        print(json.dumps(result["quiz_data"], ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"\n[LỖI]: {e}")
