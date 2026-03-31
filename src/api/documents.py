"""
Document API — Upload and Delete endpoints for teacher documents.

Upload flow (POST /upload):
1. Upload PDF to AWS S3 (stream via upload_fileobj)
2. Extract & persist to personal repository (books / question_bank)
3. Distribute to classroom via classroom_materials (insert-only)

Delete flow (DELETE /{doc_type}/{doc_id}):
1. Fetch the stored S3 file_url from DB
2. Delete file from S3 (NoSuchKey → warning, continue)
3. Delete DB record + related classroom_materials rows
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from typing import Literal
import os
import tempfile
import traceback
import logging

from botocore.exceptions import ClientError

from src.core.security import get_current_user_id
from src.services.extraction_service import ExtractionService
from src.services.db_service import DBService
from src.services.s3_service import s3_service

logger = logging.getLogger(__name__)

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
    1. Upload file lên AWS S3 (stream trực tiếp, không lưu local vĩnh viễn)
    2. Lưu vào KHO TÀI LIỆU CÁ NHÂN:
       - `THEORY` → tạo record trong bảng `books` (kèm `user_id`, `file_url`)
       - `QUESTION` → tạo record trong bảng `question_bank` (kèm `userid`, `file_url`)
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

    # ── STEP 0: Remember old S3 URL (if any) so we can delete it after re-upload ──
    # When the same file is uploaded again we keep only the newest S3 object.
    old_s3_url: str | None = None
    try:
        existing = db_service.get_existing_document(
            doc_type=type,
            filename=file.filename,
            subject_id=subject_id,
            user_id=user_id,
        )
        if existing is not None:
            _, old_s3_url = existing   # may be None if column absent / not yet set
    except Exception:
        pass  # non-fatal — proceed with full upload

    # ── Write to a temporary file (required for LlamaCloud extraction) ──
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)

    try:
        # Persist to disk so the extraction service can open it by path
        with open(temp_path, "wb") as buf:
            content = await file.read()
            buf.write(content)

        # ── STEP 1: Upload to S3 ──
        # Re-open the temp file so upload_fileobj streams from the beginning.
        try:
            with open(temp_path, "rb") as f_obj:
                s3_key, s3_url = s3_service.upload_document(
                    file_obj=f_obj,
                    user_id=user_id,
                    doc_type=type,
                    original_filename=file.filename,
                )
        except (ClientError, RuntimeError) as exc:
            print(f"[S3 UPLOAD ERROR] {traceback.format_exc()}")
            raise HTTPException(
                status_code=502,
                detail=f"Không thể upload file lên S3: {exc}"
            )

        # ── STEP 2 & 3: Extract + persist to DB (single transaction) ──
        result = db_service.upload_document_transaction(
            file_path=temp_path,
            class_id=class_id,
            subject_id=subject_id,
            doc_type=type,
            user_id=user_id,
            extraction_service=extraction_service,
            original_filename=file.filename,
            s3_url=s3_url,
        )

        # ── Delete the old S3 file now that the new one is committed ──
        if old_s3_url and old_s3_url != s3_url:
            try:
                s3_service.delete_document(old_s3_url)
            except RuntimeError:
                logger.warning("[UPLOAD] Could not delete old S3 file: %s", old_s3_url)

        # Build response message
        if type == "THEORY":
            message = (
                f"Tài liệu lý thuyết đã được upload và phân phối về lớp thành công "
                f"(Book ID: {result['record_id']})"
            )
        else:
            message = (
                f"Ngân hàng câu hỏi đã được upload và phân phối về lớp thành công "
                f"(Bank ID: {result['record_id']})"
            )

        return {
            "status": "success",
            "message": message,
            "s3_key": s3_key,
            **result,
        }

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        print(f"[UPLOAD ERROR] {traceback.format_exc()}")
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi xử lý tài liệu: {exc}"
        )
    finally:
        # ── Clean up temp files ──
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


@router.delete("/{doc_type}/{doc_id}")
async def delete_document(
    doc_type: Literal["THEORY", "QUESTION"],
    doc_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """
    Xóa tài liệu của giáo viên.

    **Luồng xử lý:**
    1. Lấy `file_url` (S3) từ DB theo `doc_type` và `doc_id`.
    2. Xóa file trên S3:
       - Thành công hoặc file không tồn tại (đã xóa trước) → tiếp tục.
       - Lỗi AWS khác → trả về 502, KHÔNG xóa DB.
    3. Xóa record trong DB kèm các dòng `classroom_materials` liên quan.

    **Yêu cầu:** Bearer Token JWT hợp lệ.
    """
    # ── STEP 1: Fetch S3 file_url from DB ──
    try:
        file_url = db_service.get_document_file_url(doc_type, doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # ── STEP 2: Delete from S3 (before touching DB) ──
    if file_url:
        try:
            found_on_s3 = s3_service.delete_document(file_url)
            if not found_on_s3:
                logger.warning(
                    "[DELETE] S3 object not found, proceeding with DB deletion: %s", file_url
                )
        except RuntimeError as exc:
            logger.error("[DELETE S3 ERROR] %s", traceback.format_exc())
            raise HTTPException(
                status_code=502,
                detail=f"Không thể xóa file trên S3, tài liệu chưa bị xóa: {exc}",
            )
    else:
        logger.warning(
            "[DELETE] Không có file_url trong DB cho %s id=%s, bỏ qua bước xóa S3.",
            doc_type, doc_id,
        )

    # ── STEP 3: Delete from DB ──
    try:
        db_service.delete_document_from_db(doc_type, doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("[DELETE DB ERROR] %s", traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Lỗi xóa tài liệu khỏi cơ sở dữ liệu: {exc}",
        )

    doc_label = "Tài liệu lý thuyết" if doc_type == "THEORY" else "Ngân hàng câu hỏi"
    return {
        "status": "success",
        "message": f"{doc_label} (id={doc_id}) đã được xóa thành công.",
        "doc_type": doc_type,
        "doc_id": doc_id,
        "deleted_by": user_id,
    }
