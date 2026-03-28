from fastapi import APIRouter, HTTPException
from typing import List
from pydantic import BaseModel
from src.quiz_gen.quiz_generator import get_db_connection

router = APIRouter()

class ClassroomResponse(BaseModel):
    classid: int
    class_name: str
    subject_id: int
    teacherid: int

@router.get("/", response_model=List[ClassroomResponse])
def get_classrooms():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Fetch classrooms with subjectid (aliased to subject_id for consistency)
        cur.execute("SELECT classid, class_name, subjectid, teacherid FROM classrooms ORDER BY class_name")
        rows = cur.fetchall()
        return [
            {
                "classid": row[0],
                "class_name": row[1],
                "subject_id": row[2],
                "teacherid": row[3]
            } for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
