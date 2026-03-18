from typing import List, Dict, Any
from .db_connector import get_db_connection

def link_questions_to_lessons(wrong_questions: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Sử dụng embedding vector của câu hỏi để tìm kiếm nội dung bài học tương ứng gần nhất
    qua pgvector, từ đó nhóm các câu hỏi theo bài học.
    
    Args:
        wrong_questions (list): Danh sách các câu hỏi làm sai (bao gồm embedding).
        
    Returns:
        Dict[int, Dict]: Từ điển với key là lesson_id, value là dict chứa:
            - chapter_id
            - lesson_title
            - chapter_title
            - wrong_questions: list các câu hỏi thuộc bài học này
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    lesson_groups = {}
    
    try:
        for q in wrong_questions:
            embedding = q.get('question_embedding')
            if not embedding:
                print(f"Bỏ qua câu hỏi ID {q['question_id']} vì không có embedding.")
                continue
                
            # Truy vấn tìm content_block gần nhất (có độ tương đồng cao nhất => khoảng cách nhỏ nhất)
            # Truy ngược từ content_blocks -> subsections -> sections -> lessons -> chapters
            query = """
                SELECT 
                    c.id AS chapter_id,
                    c.title AS chapter_title,
                    l.id AS lesson_id,
                    l.title AS lesson_title
                FROM content_blocks cb
                JOIN subsections sub ON cb.subsection_id = sub.id
                JOIN sections sec ON sub.section_id = sec.id
                JOIN lessons l ON sec.lesson_id = l.id
                JOIN chapters c ON l.chapter_id = c.id
                ORDER BY cb.embedding <=> %s::vector
                LIMIT 1
            """
            cur.execute(query, (embedding,))
            result = cur.fetchone()
            
            if result:
                chapter_id, chapter_title, lesson_id, lesson_title = result
                
                if lesson_id not in lesson_groups:
                    lesson_groups[lesson_id] = {
                        "chapter_id": chapter_id,
                        "chapter_title": chapter_title,
                        "lesson_id": lesson_id,
                        "lesson_title": lesson_title,
                        "wrong_questions": []
                    }
                    
                # Xoá embedding ra khỏi data trước khi đưa cho LLM để giảm payload
                q_clean = {k: v for k, v in q.items() if k != 'question_embedding'}
                lesson_groups[lesson_id]["wrong_questions"].append(q_clean)
            else:
                print(f"Không tìm được bài học phù hợp cho câu hỏi ID {q['question_id']}.")
                
    finally:
        cur.close()
        conn.close()
        
    return lesson_groups
