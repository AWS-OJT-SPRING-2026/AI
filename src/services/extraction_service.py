from typing import Dict, Any
from dotenv import load_dotenv
from src.models.schema import Book
from src.extract_doc.extract_document import extract_document
from src.extract_quiz.extract_question import extract_question

load_dotenv()


class ExtractionService:
    def extract_theory(self, file_path: str) -> Book:
        return extract_document(file_path)

    def extract_quiz(self, file_path: str) -> Dict[str, Any]:
        return extract_question(file_path)
