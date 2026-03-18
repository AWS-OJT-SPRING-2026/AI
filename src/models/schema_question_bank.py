# Thêm vào app/models/schema.py (bên cạnh class Book hiện có)
from pydantic import BaseModel
from typing import Optional, Literal
# ─── Question Bank Models ────────────────────────────────────────────────────
class Answer(BaseModel):
    content: str
    label: str #A, B, C, D ,...
    is_correct: bool

class Question(BaseModel):
    question_text: str
    image_url: Optional[str] = None
    answers: list[Answer]
    explanation: Optional[str] = None
    vector: list[float] # Vector embedding
    difficulty_level: int

class QuestionBank(BaseModel):
    bank_name: str
    questions: list[Question]