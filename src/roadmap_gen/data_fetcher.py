from typing import List, Tuple, Dict, Any
from .db_connector import get_db_connection

def fetch_wrong_questions(student_id: int, subject_id: int) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Lấy danh sách các câu hỏi mà học sinh làm sai trong các bài kiểm tra thuộc một môn học.
    
    Args:
        student_id (int): ID của học sinh trong bảng students.
        subject_id (int): ID của môn học.
        
    Returns:
        tuple (userid, list of wrong questions):
            userid (int): ID người dùng tương ứng của học sinh.
            wrong_questions (list): Mỗi phần tử là dict chứa:
                - question_id
                - question_text
                - selected_answer_label
                - correct_answer_label
                - correct_answer_content
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    wrong_questions = []
    user_id = None
    
    try:
        # Bước 1: Lấy userid từ student_id
        cur.execute("SELECT userid FROM students WHERE studentid = %s", (student_id,))
        result = cur.fetchone()
        if not result:
            raise ValueError(f"Không tìm thấy học sinh với studentid={student_id}")
        user_id = result[0]
        
        # Bước 2: Truy vấn các câu hỏi làm sai (is_correct = FALSE) của user_id trong subject_id
        # subject_id liên kết với question qua bảng question_bank
        # submissions liên kết với assignments (danh sách bài kiểm tra)
        query = """
            SELECT 
                q.id AS question_id,
                q.question_text,
                q.embedding,
                sa.selected_answer,
                ca.label AS correct_label,
                ca.content AS correct_content
            FROM submissions s
            JOIN assignments a ON s.assignmentid = a.assignmentid
            JOIN assignment_questions aq ON a.assignmentid = aq.assignmentid
            JOIN questions q ON aq.questionid = q.id
            JOIN question_bank qb ON q.bank_id = qb.id
            JOIN submission_answers sa ON s.submissionid = sa.submissionid AND q.id = sa.questionid
            JOIN answers ca ON q.id = ca.question_id AND ca.is_correct = TRUE
            WHERE s.userid = %s
              AND qb.subject_id = %s
              AND sa.is_correct = FALSE
        """
        cur.execute(query, (user_id, subject_id))
        rows = cur.fetchall()
        
        for row in rows:
            wrong_questions.append({
                "question_id": row[0],
                "question_text": row[1],
                "question_embedding": row[2],  # Lấy raw embedding str (dạng vector của pgvector)
                "selected_answer_label": row[3],
                "correct_answer_label": row[4],
                "correct_answer_content": row[5]
            })
            
    finally:
        cur.close()
        conn.close()
        
    return user_id, wrong_questions
