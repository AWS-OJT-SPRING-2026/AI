from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class AssignmentCreateRequest(BaseModel):
    title: str = Field(..., description="Tiêu đề assignment")
    subject_id: int = Field(..., description="ID môn học")
    chapter_ids: List[int] = Field(..., min_length=1, description="Danh sách chapter IDs cần lấy câu hỏi")
    total_questions: int = Field(..., gt=0, description="Tổng số câu hỏi trong assignment")
    num_ai_questions: int = Field(default=0, ge=0, description="Số câu hỏi tạo bằng AI (mặc định 0 = chỉ lấy từ DB)")
    userid: int = Field(..., description="ID của người dùng (Giáo viên hoặc Học sinh)")
    classid: Optional[int] = Field(default=None, description="ID lớp học")
    deadline: Optional[datetime] = Field(default=None, description="Hạn nộp (VD: 2026-12-31T23:59:59)")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Bài tập Tiếng Anh Học Kỳ 1",
                "subject_id": 1,
                "chapter_ids": [101, 102],
                "total_questions": 10,
                "num_ai_questions": 2,
                "userid": 99,
                "classid": 10,
                "deadline": "2026-12-31T23:59:59"
            }
        }

class AssignmentCreateResponse(BaseModel):
    assignment_id: int
    title: str
    total_questions: int
    db_question_ids: List[int]
    ai_question_ids: List[int]
    status: str
