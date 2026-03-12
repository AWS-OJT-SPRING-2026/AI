import os
import json
from typing import Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

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
# 2. Service gọi OpenAI API
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

    def generate(self, text: str, retries: int = 1) -> dict:
        """
        Gửi request đến OpenAI để sinh câu hỏi.
        Nếu JSON bị lỗi format, hệ thống sẽ retry theo số lần chỉ định (mặc định 1 lần).
        """
        prompt = PROMPT_TEMPLATE.format(num_questions="3-5", text=text)

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
# 3. Hàm giao tiếp chính (Main Wrapper)
# ==========================================
def generate_quiz(text: str) -> dict:
    """
    Hàm giao tiếp (wrapper) dùng để tích hợp một cách nhanh chóng.
    Nhận vào `text` và trả về danh sách bộ câu hỏi (dict/JSON).
    """
    service = QuizGeneratorService()
    return service.generate(text=text)

# ==========================================
# 4. Ví dụ sử dụng khi chạy trực tiếp file
# ==========================================
if __name__ == "__main__":
    
    sample_text = (
        "Bài toán quy hoạch tuyến tính (hai biến) là bài toán tìm giá trị lớn nhất, giá trị nhỏ nhất của "
        "biểu thức dạng F = F(x, y) = ax + by (a và b là các số thực không đồng thời bằng 0). "
        "Đây là một nhánh của toán học tối ưu hóa, giúp giải quyết các bài toán cấp phát tài nguyên, "
        "kinh tế và lập lịch. Các ràng buộc của biến thường được cho bởi các hệ bất phương trình tuyến tính."
    )
    
    print("Đang tạo câu hỏi trắc nghiệm bằng API, vui lòng chờ...\n")
    try:
        # Gọi thẳng function do yêu cầu đề bài
        result = generate_quiz(text=sample_text)
        
        # Màn hình JSON trả về
        print("Kết quả JSON:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"\n[LỖI]: {e}")
