from fastapi import APIRouter, HTTPException
from typing import List, Optional
from src.quiz_gen.quiz_generator import get_db_connection, generate_and_save_quiz
from pydantic import BaseModel
import random

router = APIRouter()

class Subject(BaseModel):
    subject_id: int
    subject_name: str

class Chapter(BaseModel):
    id: int
    title: str
    chapter_number: str

class Lesson(BaseModel):
    id: int
    title: str
    lesson_number: str

class QuestionRequest(BaseModel):
    subject_id: int
    lesson_ids: List[int]
    num_questions: int
    ai_questions: int
    userid: int = 1  # Default for now

class AnswerResponse(BaseModel):
    content: str
    label: str
    is_correct: bool

class QuestionResponse(BaseModel):
    id: int
    type: str # 'AI Generated' or 'Bank Question'
    subject: str
    question: str
    options: List[str]
    answer_ref_ids: List[int] # IDs from answers table for each option
    correct: int # Index of the correct answer
    explanation: str
    level: str

class SubmissionAnswer(BaseModel):
    question_id: int
    selected_answer: str
    is_correct: bool
    answer_ref_id: Optional[int] = None

class SubmissionRequest(BaseModel):
    userid: int
    assignmentid: Optional[int] = None
    score: float
    time_taken: int
    answers: List[SubmissionAnswer]

class SubmissionHistoryEntry(BaseModel):
    submissionid: int
    score: float
    time_taken: int
    submit_time: str
    quiz_name: Optional[str] = "Ôn tập"

class SubmissionHistoryResponse(BaseModel):
    history: List[SubmissionHistoryEntry]

@router.get("/", response_model=List[Subject])
def get_subjects():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT subject_id, subject_name FROM subjects ORDER BY subject_id")
        rows = cur.fetchall()
        return [{"subject_id": row[0], "subject_name": row[1]} for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/{subject_id}/chapters", response_model=List[Chapter])
def get_chapters(subject_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT ch.id, ch.title, ch.chapter_number
            FROM chapters ch
            JOIN books b ON ch.book_id = b.id
            WHERE b.subject_id = %s
            ORDER BY ch.chapter_number
        """
        cur.execute(query, (subject_id,))
        rows = cur.fetchall()
        return [{"id": row[0], "title": row[1], "chapter_number": row[2]} for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/{subject_id}/lessons", response_model=List[Lesson])
def get_lessons(subject_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        query = """
            SELECT l.id, l.title, l.lesson_number
            FROM lessons l
            JOIN chapters ch ON l.chapter_id = ch.id
            JOIN books b ON ch.book_id = b.id
            WHERE b.subject_id = %s
            ORDER BY ch.chapter_number, l.lesson_number
        """
        cur.execute(query, (subject_id,))
        rows = cur.fetchall()
        return [{"id": row[0], "title": row[1], "lesson_number": row[2]} for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/fetch-questions", response_model=List[QuestionResponse])
def fetch_questions_review(req: QuestionRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Fetch bank questions if needed
        bank_question_count = req.num_questions - req.ai_questions
        bank_questions = []
        result_formatted = []
        
        if bank_question_count > 0:
            # First attempt: Specific lessons
            if req.lesson_ids:
                query = """
                    SELECT q.id, q.question_text, q.explanation, q.difficulty_level, q.is_ai, s.subject_name
                    FROM questions q
                    JOIN question_bank qb ON q.bank_id = qb.id
                    JOIN subjects s ON qb.subject_id = s.subject_id
                    WHERE q.id IN (
                        SELECT qcb.questionid
                        FROM question_content_blocks qcb
                        JOIN content_blocks cb ON qcb.content_block_id = cb.id
                        JOIN subsections sub ON cb.subsection_id = sub.id
                        JOIN sections sec ON sub.section_id = sec.id
                        JOIN lessons l ON sec.lesson_id = l.id
                        WHERE l.id = ANY(%s)
                    ) AND q.is_ai = FALSE
                    ORDER BY RANDOM()
                    LIMIT %s
                """
                cur.execute(query, (req.lesson_ids, bank_question_count))
                rows = cur.fetchall()
                
                for row in rows:
                    bank_questions.append(row)

            # Fallback attempt: Subject level if not enough questions found for specific lessons
            remaining_bank_needed = bank_question_count - len(bank_questions)
            if remaining_bank_needed > 0:
                fallback_query = """
                    SELECT q.id, q.question_text, q.explanation, q.difficulty_level, q.is_ai, s.subject_name
                    FROM questions q
                    JOIN question_bank qb ON q.bank_id = qb.id
                    JOIN subjects s ON qb.subject_id = s.subject_id
                    WHERE s.subject_id = %s AND q.is_ai = FALSE
                    AND q.id NOT IN %s
                    ORDER BY RANDOM()
                    LIMIT %s
                """
                # Exclude already picked IDs
                picked_ids = [r[0] for r in bank_questions] if bank_questions else [-1]
                cur.execute(fallback_query, (req.subject_id, tuple(picked_ids), remaining_bank_needed))
                fallback_rows = cur.fetchall()
                for row in fallback_rows:
                    bank_questions.append(row)

            # Process all bank questions into QuestionResponse objects
            for row in bank_questions:
                q_id, text, expl, diff, is_ai, sub_name = row
                
                # Fetch answers for this question
                cur.execute("SELECT content, label, is_correct, id FROM answers WHERE question_id = %s ORDER BY label", (q_id,))
                ans_rows = cur.fetchall()
                
                options = [r[0] for r in ans_rows]
                correct_idx = next((i for i, r in enumerate(ans_rows) if r[2]), 0)
                
                level_map = {1: "Dễ", 2: "Trung bình", 3: "Khó"}
                
                # Check if we already have this question (due to various query overlaps)
                # We'll use result_formatted to store unique responses
                result_formatted.append(QuestionResponse(
                    id=q_id,
                    type="Bank Question",
                    subject=sub_name,
                    question=text,
                    options=options,
                    answer_ref_ids=[r[3] for r in ans_rows],
                    correct=correct_idx,
                    explanation=expl or "",
                    level=level_map.get(diff, "Trung bình")
                ))

        # 2. Generate AI questions if needed
        ai_questions_list = []
        if req.ai_questions > 0 and req.lesson_ids:
            # If no bank questions could be found at all, we might want to increase AI count to match total
            # but let's stick to requested counts for now, or maybe adjust if specifically needed.
            
            # For simplicity, we'll use the first selected lesson to generate questions
            # generate_and_save_quiz handles one lesson_id at a time
            for l_id in req.lesson_ids[:1]:
                result = generate_and_save_quiz(
                    userid=req.userid,
                    lesson_id=l_id,
                    total_questions=req.ai_questions
                )
                
                for q in result['quiz_data']['questions']:
                    options = [q['options'].get(l, "") for l in ["A", "B", "C", "D"]]
                    correct_idx = ord(q['correct_answer']) - ord('A')
                    
                    level_map = {1: "Dễ", 2: "Trung bình", 3: "Khó"}
                    
                    # Fetch real question ID from DB for AI questions since they were saved
                    # We can use the text to find it if needed, or if inserted_question_ids were returned
                    # Actually, we need the answer IDs too. Let's query by text (approximate) or index.
                    # Since generate_and_save_quiz doesn't return the mapping, let's query the newest matching questions for this user.
                    cur.execute("SELECT id FROM questions WHERE question_text = %s AND is_ai = TRUE ORDER BY id DESC LIMIT 1", (q['question_text'],))
                    new_q_id_row = cur.fetchone()
                    new_q_id = new_q_id_row[0] if new_q_id_row else random.randint(10000, 99999)

                    # Now fetch answer IDs for this new AI question
                    cur.execute("SELECT id FROM answers WHERE question_id = %s ORDER BY label", (new_q_id,))
                    new_ans_ids = [r[0] for r in cur.fetchall()]

                    ai_questions_list.append(QuestionResponse(
                        id=new_q_id, 
                        type="AI Generated",
                        subject=router.tags[0] if router.tags else "AI Support", 
                        question=q['question_text'],
                        options=options,
                        answer_ref_ids=new_ans_ids if new_ans_ids else [0]*len(options),
                        correct=correct_idx,
                        explanation=q['explanation'],
                        level=level_map.get(q['difficulty_level'], "Trung bình")
                    ))

        # Combine results
        final_questions = result_formatted + ai_questions_list
        return final_questions

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/submit-quiz")
def submit_quiz(req: SubmissionRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Insert into submissions
        # We use COALESCE/NULL for assignmentid if not provided
        query_sub = """
            INSERT INTO submissions (assignmentid, userid, score, time_taken, submit_time)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING submissionid
        """
        cur.execute(query_sub, (req.assignmentid, req.userid, req.score, req.time_taken))
        submission_id = cur.fetchone()[0]

        # 2. Insert answers
        query_ans = """
            INSERT INTO submission_answers (submissionid, questionid, answer_ref_id, selected_answer, is_correct)
            VALUES (%s, %s, %s, %s, %s)
        """
        for ans in req.answers:
            cur.execute(query_ans, (
                submission_id, 
                ans.question_id, 
                ans.answer_ref_id, 
                ans.selected_answer, 
                ans.is_correct
            ))

        conn.commit()
        return {"status": "success", "submission_id": submission_id}

    except Exception as e:
        conn.rollback()
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/submissions/{userid}", response_model=List[SubmissionHistoryEntry])
def get_submission_history(userid: int):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Fetch submissions with subject name (taking first question's subject as representative)
        query = """
            SELECT s.submissionid, s.score, s.time_taken, s.submit_time, sub.subject_name
            FROM submissions s
            LEFT JOIN LATERAL (
                SELECT qb.subject_id 
                FROM submission_answers sa
                JOIN questions q ON sa.questionid = q.id
                JOIN question_bank qb ON q.bank_id = qb.id
                WHERE sa.submissionid = s.submissionid
                LIMIT 1
            ) AS first_q ON TRUE
            LEFT JOIN subjects sub ON first_q.subject_id = sub.subject_id
            WHERE s.userid = %s
            ORDER BY s.submit_time DESC
            LIMIT 20
        """
        cur.execute(query, (userid,))
        rows = cur.fetchall()
        
        history = []
        for row in rows:
            history.append(SubmissionHistoryEntry(
                submissionid=row[0],
                score=row[1],
                time_taken=row[2],
                submit_time=row[3].strftime("%Y-%m-%d %H:%M") if row[3] else "",
                quiz_name=row[4] or "Ôn tập"
            ))
        return history
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
