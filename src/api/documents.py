"""
Document Upload API — Teacher document upload endpoint.

Handles the full 3-step upload flow:
1. Save uploaded file temporarily
2. Extract & persist to personal repository (books / question_bank)
3. Distribute to classroom via classroom_materials (insert-only)

All DB operations run in a single transaction with automatic rollback on failure.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Literal
import os
import shutil
import tempfile
import traceback

from src.core.security import get_current_user_id
from src.services.extraction_service import ExtractionService
from src.services.db_service import DBService

router = APIRouter()
extraction_service = ExtractionService()
db_service = DBService()


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(..., description="File PDF tài liệu cần upload"),
    class_id: int = Form(..., description="ID của lớp học nhận tài liệu"),
    subject_id: int = Form(..., description="ID môn học"),
    type: Literal["THEORY", "QUESTION"] = Form(..., description="Loại tài liệu: THEORY (Lý thuyết) hoặc QUESTION (Câu hỏi)"),
    user_id: int = Depends(get_current_user_id),
):
    """
    Upload tài liệu cho giáo viên.
    
    **Luồng xử lý:**
    1. Lưu file tạm → trích xuất nội dung (Theory hoặc Question Bank)
    2. Lưu vào KHO TÀI LIỆU CÁ NHÂN:
       - `THEORY` → tạo record trong bảng `books` (kèm `user_id`)
       - `QUESTION` → tạo record trong bảng `question_bank` (kèm `userid`)
        3. Phân phối về LỚP HỌC qua bảng `classroom_materials`:
           - Luôn tạo record mới (INSERT)
           - Không ghi đè record cũ

    **Yêu cầu:** Bearer Token JWT hợp lệ (giáo viên đã đăng nhập).
    """
    # ── Validate file type ──
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Chỉ hỗ trợ file PDF. Vui lòng chọn file có đuôi .pdf"
        )

    # ── Save file to temporary location ──
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)

    try:
        # Write uploaded file to disk
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # ── Execute the 3-step transaction ──
        result = db_service.upload_document_transaction(
            file_path=temp_path,
            class_id=class_id,
            subject_id=subject_id,
            doc_type=type,
            user_id=user_id,
            extraction_service=extraction_service,
        )

        # Build response message
        if type == "THEORY":
            message = f"Tài liệu lý thuyết đã được upload và phân phối về lớp thành công (Book ID: {result['record_id']})"
        else:
            message = f"Ngân hàng câu hỏi đã được upload và phân phối về lớp thành công (Bank ID: {result['record_id']})"

        return {
            "status": "success",
            "message": message,
            **result,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"[UPLOAD ERROR] {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi xử lý tài liệu: {str(e)}"
        )
    finally:
        # ── Clean up temp files ──
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
