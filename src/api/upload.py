from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
import os
import shutil
import tempfile
from src.services.extraction_service import ExtractionService
from src.services.db_service import DBService

router = APIRouter()
extraction_service = ExtractionService()
db_service = DBService()

@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    subject_id: int = Form(...),
    doc_type: str = Form(...), # "theory" or "question"
    userid: int = Form(1),
    classid: Optional[int] = Form(None)
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # 1. Save file to temporary location
    temp_dir = tempfile.mkdtemp()
    temp_path = os.path.join(temp_dir, file.filename)
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. Process based on doc_type
        if doc_type == "theory":
            # Extract
            data = extraction_service.extract_theory(temp_path)
            # Insert (userid used as user_id for the books table)
            record_id = db_service.insert_book(data, subject_id, user_id=userid)
            return {"status": "success", "message": "Theory document processed successfully", "book_id": record_id}
            
        elif doc_type == "question":
            # Extract
            data = extraction_service.extract_quiz(temp_path)
            # Insert
            record_id = db_service.insert_quiz(data, subject_id, userid)
            return {"status": "success", "message": "Question bank processed successfully", "bank_id": record_id}
            
        else:
            raise HTTPException(status_code=400, detail="Invalid doc_type. Must be 'theory' or 'question'.")

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 3. Clean up
        if os.path.exists(temp_path):
            os.remove(temp_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
