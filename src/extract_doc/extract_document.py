from llama_cloud_services import LlamaExtract
from llama_cloud import ExtractConfig
import os
import json
from dotenv import load_dotenv
from src.models.schema import Book

load_dotenv()

_data_schema = {
    "additionalProperties": False,
    "properties": {
        "book_name": {
            "description": "Tên sách",
            "type": "string"
        },
        "chapters": {
            "description": "Danh sách các chương trong sách giáo khoa.",
            "items": {
                "description": "Đại diện cho một chương học chuyên biệt trong sách giáo khoa.",
                "properties": {
                    "chapter_number": {
                        "description": "Số thứ tự chương (ví dụ: 1, 2, 3). Tăng dần 1 đơn vị cho mỗi chương.",
                        "type": "string"
                    },
                    "title": {
                        "description": "Tiêu đề đầy đủ của chương.",
                        "type": "string"
                    },
                    "lessons": {
                        "description": "Danh sách các bài học trong chương, được sắp xếp theo thứ tự.",
                        "items": {
                            "description": "Đại diện cho một bài học trong chương.",
                            "properties": {
                                "lesson_number": {
                                    "description": "Số thứ tự bài học trong chương (ví dụ: 1, 2, 3). Tăng dần 1 đơn vị cho mỗi bài.",
                                    "type": "string"
                                },
                                "title": {
                                    "description": "Tiêu đề đầy đủ của bài học như xuất hiện trong sách giáo khoa.",
                                    "type": "string"
                                },
                                "section": {
                                    "description": "Danh sách có thứ tự các mục lớn trong bài học.",
                                    "items": {
                                        "description": "Một mục lớn trong bài học.",
                                        "properties": {
                                            "section_number": {
                                                "description": "Số thứ tự hoặc ký hiệu của mục (ví dụ: 1, 2, 3, a, b).",
                                                "type": "string"
                                            },
                                            "section_title": {
                                                "anyOf": [{"description": "Tiêu đề của mục nếu xuất hiện dưới dạng tiêu đề trong văn bản.", "type": "string"}, {"type": "null"}],
                                                "description": "Tiêu đề của mục nếu xuất hiện dưới dạng tiêu đề trong văn bản."
                                            },
                                            "subsections": {
                                                "anyOf": [{
                                                    "description": "Danh sách các tiểu mục trong mục, mỗi tiểu mục chứa các khối nội dung.",
                                                    "items": {
                                                        "description": "Một tiểu mục trong mục lớn.",
                                                        "properties": {
                                                            "subsection_number": {
                                                                "description": "Số thứ tự hoặc ký hiệu của tiểu mục (ví dụ: 1, 2, a, b).",
                                                                "type": "string"
                                                            },
                                                            "subsection_title": {
                                                                "anyOf": [{"description": "Tiêu đề của tiểu mục nếu xuất hiện trong văn bản.", "type": "string"}, {"type": "null"}],
                                                                "description": "Tiêu đề của tiểu mục nếu xuất hiện trong văn bản."
                                                            },
                                                            "content_blocks": {
                                                                "anyOf": [{
                                                                    "description": "Danh sách các khối nội dung văn bản trong tiểu mục, như đoạn văn, giải thích, ví dụ hoặc định nghĩa.",
                                                                    "items": {"type": "string"},
                                                                    "type": "array"
                                                                }, {"type": "null"}],
                                                                "description": "Danh sách các khối nội dung văn bản trong tiểu mục, như đoạn văn, giải thích, ví dụ hoặc định nghĩa."
                                                            }
                                                        },
                                                        "required": ["subsection_number", "subsection_title", "content_blocks"],
                                                        "type": "object"
                                                    },
                                                    "type": "array"
                                                }, {"type": "null"}],
                                                "description": "Danh sách các tiểu mục trong mục, mỗi tiểu mục chứa các khối nội dung."
                                            }
                                        },
                                        "required": ["section_number", "section_title", "subsections"],
                                        "type": "object"
                                    },
                                    "type": "array"
                                }
                            },
                            "required": ["lesson_number", "title", "section"],
                            "type": "object"
                        },
                        "type": "array"
                    }
                },
                "required": ["chapter_number", "title", "lessons"],
                "type": "object"
            },
            "type": "array"
        }
    },
    "required": ["book_name", "chapters"],
    "type": "object"
}

_config = ExtractConfig(
    extraction_target="PER_DOC",
    extraction_mode="MULTIMODAL",
    extract_model="openai-gpt-4-1",
    system_prompt="""Bạn là hệ thống trích xuất thông tin. Tài liệu này sử dụng tiếng Việt.
Nhiệm vụ của bạn là đọc nội dung sách giáo khoa và chuyển đổi thành định dạng JSON có cấu trúc, tuân thủ chặt chẽ schema được cung cấp.
Lưu ý: Mục lục chỉ cung cấp tổng quan về nội dung và không chứa nội dung bài học.

Quy tắc trích xuất:
1. Giữ nguyên cấu trúc phân cấp:
   Sách → Chương → Bài học → Mục → Tiểu mục → Khối nội dung.
2. Với mỗi chương:
   * Trích xuất `chapter_number`
   * Trích xuất `title` (tiêu đề chương)
   * Trích xuất tất cả các bài học trong chương.
3. Với mỗi bài học:
   * Trích xuất `lesson_number`
   * Trích xuất `title` (tiêu đề bài học)
   * Trích xuất tất cả các mục theo thứ tự.
4. Với mỗi mục (`section`):
   * Trích xuất `section_number` nếu có.
   * Trích xuất `section_title` nếu có.
   * Trích xuất tất cả các tiểu mục (`subsections`) trong mục theo thứ tự.
5. Với mỗi tiểu mục (`subsection`):
   * Trích xuất `subsection_number` nếu có.
   * Trích xuất `subsection_title` nếu có.
   * Trích xuất nội dung văn bản vào `content_blocks`.
6. `content_blocks` chỉ được chứa các đoạn văn bản thuần túy như:
   * Đoạn văn
   * Ví dụ
   * Định nghĩa
   * Giải thích
Lưu ý: Các số trong các trường như chương, bài học, mục và tiểu mục phải theo thứ tự tăng dần. Nếu không theo thứ tự tăng dần, có thể bạn đã mắc lỗi.
- Giữ nguyên thứ tự các chương, bài học, mục và tiểu mục đúng như chúng xuất hiện trong tài liệu.
- Nếu một mục không có tiểu mục rõ ràng, tạo một tiểu mục duy nhất để chứa toàn bộ nội dung của mục đó.
- KHÔNG bịa đặt thông tin. Chỉ trích xuất những gì có trong tài liệu.
- Nếu một trường không xuất hiện trong văn bản, trả về `null` hoặc bỏ qua theo quy tắc schema.
- Đầu ra phải là JSON hợp lệ, khớp chặt chẽ với schema.
Mục tiêu của bạn là chuyển đổi trung thực nội dung sách giáo khoa chưa có cấu trúc thành dữ liệu giáo dục có cấu trúc.""",
    use_reasoning=True,
    cite_sources=True,
    citation_bbox=True,
    confidence_scores=False,
    chunk_mode="SECTION",
    high_resolution_mode=False,
    invalidate_cache=False,
)


def extract_document(file_path: str) -> Book:
    api_key = os.getenv("LLAMA_CLOUD_API_KEY")
    extractor = LlamaExtract(api_key=api_key)
    result = extractor.extract(_data_schema, _config, file_path)
    return Book.model_validate(result.data)


if __name__ == "__main__":
    file = "src/extract_doc/template_doc.pdf"
    try:
        book = extract_document(file)
        print("Extraction validated successfully")
        print(book.book_name)
        output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_doc.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(book.model_dump(), f, ensure_ascii=False, indent=4)
    except Exception as e:
        print("Error:", e)
