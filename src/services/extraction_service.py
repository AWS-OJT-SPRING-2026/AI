import os
import json
from typing import Dict, Any, Optional
from llama_cloud_services import LlamaExtract
from llama_cloud import ExtractConfig
from dotenv import load_dotenv
from src.models.schema import Book
from src.models.schema_question_bank import QuestionBank

load_dotenv()

class ExtractionService:
    def __init__(self):
        self.api_key = os.getenv("LLAMA_CLOUD_API_KEY")
        if not self.api_key:
            raise ValueError("LLAMA_CLOUD_API_KEY not found in environment variables.")
        self.extractor = LlamaExtract(api_key=self.api_key)

    def extract_theory(self, file_path: str) -> Book:
        json_data = {
            "dataSchema": {
                "additionalProperties": False,
                "properties": {
                    "book_name": {"description": "Tên sách", "type": "string"},
                    "chapters": {
                        "description": "Danh sách các chương trong sách giáo khoa.",
                        "items": {
                            "properties": {
                                "chapter_number": {"description": "Số thứ tự chương", "type": "string"},
                                "title": {"description": "Tiêu đề chương", "type": "string"},
                                "lessons": {
                                    "items": {
                                        "properties": {
                                            "lesson_number": {"description": "Số thứ tự bài học", "type": "string"},
                                            "title": {"description": "Tiêu đề bài học", "type": "string"},
                                            "section": {
                                                "items": {
                                                    "properties": {
                                                        "section_number": {"type": "string"},
                                                        "section_title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                                                        "content": {
                                                            "type": ["string", "null"],
                                                            "description": "Toàn bộ nội dung văn bản dưới mục này, bao gồm cả các tiểu mục. Bao gồm văn bản, ví dụ, định nghĩa."
                                                        }
                                                    },
                                                    "required": ["section_number", "section_title", "content"],
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
            },
            "config": {
                "extraction_target": "PER_DOC",
                "extraction_mode": "MULTIMODAL",
                "extract_model": "openai-gpt-4-1",
                "system_prompt": "Bạn là chuyên gia trích xuất tài liệu giáo dục. Hãy trích xuất nội dung sách giáo khoa thành JSON có cấu trúc.",
                "chunk_mode": "SECTION"
            }
        }
        
        data_schema = json_data["dataSchema"]
        config = ExtractConfig(**json_data["config"])
        result = self.extractor.extract(data_schema, config, file_path)
        return Book.model_validate(result.data)

    def extract_quiz(self, file_path: str) -> Dict[str, Any]:
        json_data = {
            "dataSchema": {
                "type": "object",
                "required": ["bank_name", "questions"],
                "properties": {
                    "bank_name": {"type": "string", "description": "Tên ngân hàng câu hỏi"},
                    "questions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["question_text", "difficulty_level", "answers"],
                            "properties": {
                                "question_text": {"type": "string"},
                                "image_url": {"type": ["string", "null"]},
                                "difficulty_level": {"type": "integer"},
                                "explanation": {"type": ["string", "null"]},
                                "answers": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["content", "label", "is_correct"],
                                        "properties": {
                                            "label": {"type": "string"},
                                            "content": {"type": "string"},
                                            "is_correct": {"type": "boolean"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "config": {
                "extraction_target": "PER_DOC",
                "extraction_mode": "MULTIMODAL",
                "extract_model": "openai-gpt-4-1",
                "system_prompt": "Hãy trích xuất ngân hàng câu hỏi trắc nghiệm từ tài liệu PDF.",
                "chunk_mode": "SECTION"
            }
        }
        
        data_schema = json_data["dataSchema"]
        config = ExtractConfig(**json_data["config"])
        result = self.extractor.extract(data_schema, config, file_path)
        return result.data
