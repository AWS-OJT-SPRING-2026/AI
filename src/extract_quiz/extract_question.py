from llama_cloud_services import LlamaExtract
from llama_cloud import ExtractConfig
import os
import json
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

_data_schema = {
    "type": "object",
    "required": ["bank_name", "questions"],
    "properties": {
        "bank_name": {
            "type": "string",
            "description": "Tên ngân hàng câu hỏi"
        },
        "questions": {
            "type": "array",
            "description": "Danh sách câu hỏi",
            "items": {
                "type": "object",
                "required": ["question_text", "difficulty_level", "answers"],
                "properties": {
                    "question_text": {
                        "type": "string",
                        "description": "Nội dung câu hỏi"
                    },
                    "image_url": {
                        "type": ["string", "null"],
                        "description": "URL hình ảnh nếu có"
                    },
                    "difficulty_level": {
                        "type": "integer",
                        "description": "Mức độ câu hỏi: 1 (dễ), 2 (trung bình), 3 (khó)"
                    },
                    "explanation": {
                        "type": ["string", "null"],
                        "description": "Lời giải hoặc giải thích"
                    },
                    "answers": {
                        "type": "array",
                        "description": "Danh sách đáp án",
                        "items": {
                            "type": "object",
                            "required": ["content", "label", "is_correct"],
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "description": "Nhãn đáp án: A, B, C, D"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "Nội dung đáp án"
                                },
                                "is_correct": {
                                    "type": "boolean",
                                    "description": "Đáp án đúng hay không"
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

_config = ExtractConfig(
    extraction_target="PER_DOC",
    extraction_mode="MULTIMODAL",
    extract_model="openai-gpt-4-1",
    system_prompt="""Bạn là hệ thống trích xuất ngân hàng câu hỏi.

Cố gắng trích xuất theo cấu trúc:

Question Bank
 → Question
   → Answers

Quy tắc:

1. Trích xuất tên ngân hàng câu hỏi vào `bank_name` (nếu không rõ, hãy tự đặt phù hợp).

2. Với mỗi câu hỏi:
   - `question_text`: nội dung câu hỏi
   - `difficulty_level`: Trả về số nguyên 1, 2, hoặc 3 (1 = dễ, 2 = trung bình, 3 = khó)
   - `explanation`: lời giải nếu có
   - `image_url`: nếu câu hỏi có hình

3. Với câu trắc nghiệm:
   - Tách từng đáp án A,B,C,D
   - Gán label tương ứng
   - Đánh dấu đáp án đúng `is_correct=true`

4. Không tự tạo dữ liệu. Nếu không có thì trả null.

5. Đảm bảo JSON hợp lệ theo schema.
""",
    chunk_mode="SECTION",
)


def extract_question(file_path: str) -> Dict[str, Any]:
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    extractor = LlamaExtract(api_key=api_key)
    result = extractor.extract(_data_schema, _config, file_path)
    return result.data


if __name__ == "__main__":
    file = "src/extract_quiz/quiz_template.pdf"
    try:
        data = extract_question(file)
        output_path = "src/extract_quiz/output_questions.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("Extraction completed")
    except Exception as e:
        print("Error:", e)
