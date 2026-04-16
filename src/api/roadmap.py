from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from src.api.subjects import get_db_connection

router = APIRouter()

class RoadmapLessonDetail(BaseModel):
    lessonid: int
    title: str
    time: int
    explanation: Optional[str]
    wrong_question_count: int
    priority_score: float

class RoadmapChapterDetail(BaseModel):
    id: int
    chapterid: int
    title: str
    order: int
    lessons: List[RoadmapLessonDetail]

class RoadmapResponse(BaseModel):
    roadmapid: int
    studentid: int
    subject_id: int
    subject_name: str
    total_time: int
    created_at: Optional[datetime] = None
    chapters: List[RoadmapChapterDetail]

class RoadmapRequest(BaseModel):
    userid: int
    subject_id: int
    total_weeks: int

@router.post("/generate", response_model=RoadmapResponse)
def generate_roadmap(req: RoadmapRequest):
    import logging
    import os
    error_log_file = os.path.join(os.getcwd(), "roadmap_api_error.log")
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Fetch subject name
        cur.execute("SELECT subject_name FROM subjects WHERE subjectid = %s", (req.subject_id,))
        subject_row = cur.fetchone()
        if not subject_row:
            raise HTTPException(status_code=404, detail="Subject not found")
        subject_name = subject_row[0]

        # 1.5 Check if user already has a roadmap for this subject
        cur.execute("""
            SELECT r.roadmapid 
            FROM roadmaps r
            JOIN roadmap_chapters rc ON r.roadmapid = rc.roadmapid
            JOIN chapters ch ON rc.chapterid = ch.id
            JOIN books b ON ch.book_id = b.id
            WHERE r.studentid = %s AND b.subject_id = %s
            LIMIT 1
        """, (req.userid, req.subject_id))
        existing_roadmap = cur.fetchone()
        if existing_roadmap:
            raise HTTPException(status_code=400, detail="Bạn đã tạo lộ trình cho môn học này rồi. Vui lòng xoá lộ trình cũ trước khi tạo mới.")

        # 2. Create Roadmap entry
        cur.execute(
            "INSERT INTO roadmaps (studentid, total_time, created_at) VALUES (%s, %s, NOW()) RETURNING roadmapid, created_at",
            (req.userid, req.total_weeks)
        )
        roadmap_row = cur.fetchone()
        roadmapid, created_at = roadmap_row

        # 3. Fetch chapters and lessons for the subject
        cur.execute("""
            SELECT ch.id, ch.title, ch.chapter_number
            FROM chapters ch
            JOIN books b ON ch.book_id = b.id
            WHERE b.subject_id = %s
            ORDER BY ch.chapter_number
        """, (req.subject_id,))
        chapter_rows = cur.fetchall()

        roadmap_chapters = []
        for i, ch_row in enumerate(chapter_rows):
            ch_id, ch_title, ch_num = ch_row
            
            # Create roadmap_chapter entry
            cur.execute(
                "INSERT INTO roadmap_chapters (roadmapid, chapterid, chapter_order) VALUES (%s, %s, %s) RETURNING id",
                (roadmapid, ch_id, i + 1)
            )
            rc_id = cur.fetchone()[0]

            # Fetch lessons for this chapter
            cur.execute("""
                SELECT l.id, l.title, l.lesson_number
                FROM lessons l
                WHERE l.chapter_id = %s
                ORDER BY l.lesson_number
            """, (ch_id,))
            lesson_rows = cur.fetchall()

            chapter_lessons = []
            for j, l_row in enumerate(lesson_rows):
                l_id, l_title, l_num = l_row
                
                # Logic to determine time/priority (simulated for now)
                # In a real AI implementation, this would use past performance data
                study_time = 60 # 60 minutes default
                priority = 1.0
                
                cur.execute(
                    """INSERT INTO roadmap_lessons 
                       (roadmap_chapter_id, lessonid, time, explanation, wrong_question_count, priority_score) 
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (rc_id, l_id, study_time, f"Tập trung học {l_title}", 0, priority)
                )
                
                chapter_lessons.append(RoadmapLessonDetail(
                    lessonid=l_id,
                    title=l_title,
                    time=study_time,
                    explanation=f"Tập trung học {l_title}",
                    wrong_question_count=0,
                    priority_score=priority
                ))
            
            roadmap_chapters.append(RoadmapChapterDetail(
                id=rc_id,
                chapterid=ch_id,
                title=ch_title,
                order=i + 1,
                lessons=chapter_lessons
            ))

        conn.commit()

        return RoadmapResponse(
            roadmapid=roadmapid,
            studentid=req.userid,
            subject_id=req.subject_id,
            subject_name=subject_name,
            total_time=req.total_weeks,
            created_at=created_at,
            chapters=roadmap_chapters
        )
    except Exception as e:
        conn.rollback()
        import traceback
        err_msg = traceback.format_exc()
        with open(error_log_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- ERROR at {datetime.now()} ---\n{err_msg}\n")
        print(err_msg)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/all/{userid}", response_model=List[RoadmapResponse])
def get_all_roadmaps(userid: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Fetch all roadmaps for the user
        cur.execute("""
            SELECT r.roadmapid, r.studentid, r.total_time, r.created_at, s.subjectid, s.subject_name
            FROM roadmaps r
            JOIN roadmap_chapters rc ON r.roadmapid = rc.roadmapid
            JOIN chapters ch ON rc.chapterid = ch.id
            JOIN books b ON ch.book_id = b.id
            JOIN subjects s ON b.subject_id = s.subjectid
            WHERE r.studentid = %s
            GROUP BY r.roadmapid, r.studentid, r.total_time, r.created_at, s.subjectid, s.subject_name
            ORDER BY r.created_at DESC
        """, (userid,))
        r_rows = cur.fetchall()
        
        all_roadmaps = []
        for r_row in r_rows:
            r_id, s_id, t_time, c_at, sub_id, sub_name = r_row
            
            # Fetch chapters
            cur.execute("""
                SELECT rc.id, rc.chapterid, ch.title, rc.chapter_order
                FROM roadmap_chapters rc
                JOIN chapters ch ON rc.chapterid = ch.id
                WHERE rc.roadmapid = %s
                ORDER BY rc.chapter_order
            """, (r_id,))
            rc_rows = cur.fetchall()
            
            chapters = []
            for rc_row in rc_rows:
                rc_pk, ch_id, ch_title, order = rc_row
                
                # Fetch lessons
                cur.execute("""
                    SELECT rl.lessonid, l.title, rl.time, rl.explanation, rl.wrong_question_count, rl.priority_score
                    FROM roadmap_lessons rl
                    JOIN lessons l ON rl.lessonid = l.id
                    WHERE rl.roadmap_chapter_id = %s
                    ORDER BY l.lesson_number
                """, (rc_pk,))
                l_rows = cur.fetchall()
                
                lessons = [RoadmapLessonDetail(
                    lessonid=r[0], title=r[1], time=r[2], explanation=r[3], 
                    wrong_question_count=r[4], priority_score=r[5]
                ) for r in l_rows]
                
                chapters.append(RoadmapChapterDetail(
                    id=rc_pk, chapterid=ch_id, title=ch_title, order=order, lessons=lessons
                ))
                
            all_roadmaps.append(RoadmapResponse(
                roadmapid=r_id,
                studentid=s_id,
                subject_id=sub_id,
                subject_name=sub_name,
                total_time=t_time,
                created_at=c_at,
                chapters=chapters
            ))
            
        return all_roadmaps
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.delete("/{roadmapid}")
def delete_roadmap(roadmapid: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Check if roadmap exists first (for robust error handling)
        cur.execute("SELECT roadmapid FROM roadmaps WHERE roadmapid = %s", (roadmapid,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Roadmap not found")

        # Delete lessons first
        cur.execute("""
            DELETE FROM roadmap_lessons 
            WHERE roadmap_chapter_id IN (
                SELECT id FROM roadmap_chapters WHERE roadmapid = %s
            )
        """, (roadmapid,))
        
        # Delete chapters next
        cur.execute("DELETE FROM roadmap_chapters WHERE roadmapid = %s", (roadmapid,))
        
        # Delete roadmap
        cur.execute("DELETE FROM roadmaps WHERE roadmapid = %s", (roadmapid,))
        
        conn.commit()
        return {"code": 200, "message": "Roadmap deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
