from typing import List, Dict, Any
from .db_connector import get_db_connection

def save_roadmap_to_db(student_id: int, total_time_hours: float, chapters_data: Dict[int, Dict[str, Any]]) -> int:
    """
    Lưu lộ trình học tập vào cơ sở dữ liệu.
    
    Args:
        student_id (int): ID học sinh.
        total_time_hours (float): Tổng thời gian học tập.
        chapters_data (dict): Dữ liệu theo format {chapter_id: {"chapter_order": int, "lessons": [...]}}
        
    Returns:
        int: Roadmap ID vừa được tạo.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    roadmap_id = None
    
    try:
        # 1. Tạo roadmap
        cur.execute(
            """
            INSERT INTO roadmaps (studentid, total_time) 
            VALUES (%s, %s) RETURNING roadmapid
            """,
            (student_id, total_time_hours)
        )
        roadmap_id = cur.fetchone()[0]
        
        # 2. Tạo roadmap_chapters và roadmap_lessons
        for chapter_id, chapter_info in chapters_data.items():
            cur.execute(
                """
                INSERT INTO roadmap_chapters (roadmapid, chapterid, chapter_order)
                VALUES (%s, %s, %s) RETURNING id
                """,
                (roadmap_id, chapter_id, chapter_info["chapter_order"])
            )
            roadmap_chapter_id = cur.fetchone()[0]
            
            for lesson in chapter_info["lessons"]:
                cur.execute(
                    """
                    INSERT INTO roadmap_lessons 
                    (roadmap_chapter_id, lessonid, time, explain, wrong_question_count, priority_score)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        roadmap_chapter_id,
                        lesson["lesson_id"],
                        lesson["time"],
                        lesson.get("explain", ""),
                        lesson["wrong_question_count"],
                        lesson.get("priority_score", 0.0)
                    )
                )
                
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
        
    return roadmap_id
