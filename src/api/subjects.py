from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from src.quiz_gen.quiz_generator import get_db_connection, generate_and_save_quiz
from pydantic import BaseModel
import random
from src.core.security import get_current_user_id

router = APIRouter()


def _resolve_subject_columns(cur):
    """Hỗ trợ cả schema subjects kiểu subject_id/subject_name và subjectid/subjectname."""
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'subjects'
        """
    )
    cols = {row[0].lower() for row in cur.fetchall()}

    id_col = "subject_id" if "subject_id" in cols else "subjectid" if "subjectid" in cols else None
    name_col = "subject_name" if "subject_name" in cols else "subjectname" if "subjectname" in cols else None

    if not id_col or not name_col:
        raise RuntimeError("Subjects schema incompatible: missing subject id/name column.")

    return id_col, name_col

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
    userid: Optional[int] = None
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

class SubmissionDetailQuestion(BaseModel):
    id: int
    question: str
    options: List[str]
    selected: Optional[int]
    correct: int
    explanation: str
    subject: str
    level: str
    is_correct: bool

class SubmissionDetailResponse(BaseModel):
    submissionid: int
    score: float
    time_taken: int
    submit_time: str
    quiz_name: str
    questions: List[SubmissionDetailQuestion]

@router.get("/", response_model=List[Subject])
def get_subjects():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        subject_id_col, subject_name_col = _resolve_subject_columns(cur)
        cur.execute(
            f"SELECT {subject_id_col} AS subject_id, {subject_name_col} AS subject_name "
            f"FROM subjects ORDER BY {subject_id_col}"
        )
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
            ORDER BY l.lesson_number
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
        subject_id_col, subject_name_col = _resolve_subject_columns(cur)
        ai_error_message = None

        # 1. Fetch bank questions if needed
        bank_question_count = req.num_questions - req.ai_questions
        bank_questions = []
        result_formatted = []
        
        if bank_question_count > 0:
            # First attempt: Specific lessons
            if req.lesson_ids:
                query = f"""
                    SELECT q.id, q.question_text, q.explanation, q.difficulty_level, q.is_ai, s.{subject_name_col}
                    FROM questions q
                    JOIN question_bank qb ON q.bank_id = qb.id
                    JOIN subjects s ON qb.subject_id = s.{subject_id_col}
                    WHERE q.id IN (
                        SELECT qcb.questionid
                        FROM question_content_blocks qcb
                        JOIN content_blocks cb ON qcb.content_block_id = cb.id
                        JOIN subsections sub ON cb.subsection_id = sub.id
                        JOIN sections sec ON sub.section_id = sec.id
                        JOIN lessons l ON sec.lesson_id = l.id
                        WHERE l.id = ANY(%s::int[])
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
                fallback_query = f"""
                    SELECT q.id, q.question_text, q.explanation, q.difficulty_level, q.is_ai, s.{subject_name_col}
                    FROM questions q
                    JOIN question_bank qb ON q.bank_id = qb.id
                    JOIN subjects s ON qb.subject_id = s.{subject_id_col}
                    WHERE s.{subject_id_col} = %s AND q.is_ai = FALSE
                    AND q.id <> ALL(%s::int[])
                    ORDER BY RANDOM()
                    LIMIT %s
                """
                # Exclude already picked IDs
                picked_ids = [r[0] for r in bank_questions] if bank_questions else [-1]
                cur.execute(fallback_query, (req.subject_id, picked_ids, remaining_bank_needed))
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
            try:
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

                        cur.execute("SELECT id FROM questions WHERE question_text = %s AND is_ai = TRUE ORDER BY id DESC LIMIT 1", (q['question_text'],))
                        new_q_id_row = cur.fetchone()
                        new_q_id = new_q_id_row[0] if new_q_id_row else random.randint(10000, 99999)

                        cur.execute("SELECT id FROM answers WHERE question_id = %s ORDER BY label", (new_q_id,))
                        new_ans_ids = [r[0] for r in cur.fetchall()]

                        ai_questions_list.append(QuestionResponse(
                            id=new_q_id,
                            type="AI Generated",
                            subject=router.tags[0] if router.tags else "AI Support",
                            question=q['question_text'],
                            options=options,
                            answer_ref_ids=new_ans_ids if new_ans_ids else [0] * len(options),
                            correct=correct_idx,
                            explanation=q['explanation'],
                            level=level_map.get(q['difficulty_level'], "Trung bình")
                        ))
            except Exception as ai_error:
                print(f"[fetch-questions] AI generation failed: {ai_error}")
                ai_error_message = str(ai_error)
                if not result_formatted:
                    raise

        # Combine results
        final_questions = result_formatted + ai_questions_list
        if not final_questions:
            if ai_error_message:
                raise HTTPException(status_code=400, detail=f"Không tạo được câu hỏi AI: {ai_error_message}")
            raise HTTPException(status_code=400, detail="Không tìm thấy câu hỏi phù hợp cho lựa chọn hiện tại.")
        return final_questions

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.post("/submit-quiz")
def submit_quiz(req: SubmissionRequest, current_user_id: int = Depends(get_current_user_id)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Insert into submissions
        # We use COALESCE/NULL for assignmentid if not provided
        query_sub = """
            INSERT INTO submissions (assignmentid, userid, score, time_taken, submitted_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            RETURNING submissionid
        """
        cur.execute(query_sub, (req.assignmentid, current_user_id, req.score, req.time_taken))
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

    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/submissions/me", response_model=List[SubmissionHistoryEntry])
def get_submission_history_me(current_user_id: int = Depends(get_current_user_id)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Fetch submissions with subject name (taking first question's subject as representative)
        subject_id_col, subject_name_col = _resolve_subject_columns(cur)
        query = f"""
            SELECT s.submissionid, s.score, s.time_taken, s.submitted_at, sub.{subject_name_col}
            FROM submissions s
            LEFT JOIN LATERAL (
                SELECT qb.subject_id 
                FROM submission_answers sa
                JOIN questions q ON sa.questionid = q.id
                JOIN question_bank qb ON q.bank_id = qb.id
                WHERE sa.submissionid = s.submissionid
                LIMIT 1
            ) AS first_q ON TRUE
            LEFT JOIN subjects sub ON first_q.subject_id = sub.{subject_id_col}
            WHERE s.userid = %s
              AND s.assignmentid IS NULL
            ORDER BY s.submitted_at DESC
            LIMIT 20
        """
        cur.execute(query, (current_user_id,))
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
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()

@router.get("/submissions/{submissionid}/details", response_model=SubmissionDetailResponse)
def get_submission_history_details(submissionid: int, current_user_id: int = Depends(get_current_user_id)):
    import logging
    import os
    error_log_file = os.path.join(os.getcwd(), "subjects_api_error.log")
    logger = logging.getLogger(__name__)
    
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1. Fetch submission summary
        query_sub = """
            SELECT s.submissionid, s.score, s.time_taken, s.submitted_at
            FROM submissions s
            WHERE s.submissionid = %s
              AND s.userid = %s
              AND s.assignmentid IS NULL
        """
        cur.execute(query_sub, (submissionid, current_user_id))
        sub_row = cur.fetchone()
        if not sub_row:
            raise HTTPException(status_code=404, detail="Submission not found")
            
        # 2. Fetch answers and question details
        # Removed ORDER BY sa.id as it may not exist
        subject_id_col, subject_name_col = _resolve_subject_columns(cur)
        query_details = f"""
            SELECT
                q.id, q.question_text, q.explanation, q.difficulty_level, 
                sub.{subject_name_col}, sa.selected_answer, sa.is_correct
            FROM submission_answers sa
            JOIN questions q ON sa.questionid = q.id
            JOIN question_bank qb ON q.bank_id = qb.id
            JOIN subjects sub ON qb.subject_id = sub.{subject_id_col}
            WHERE sa.submissionid = %s
        """
        cur.execute(query_details, (submissionid,))
        detail_rows = cur.fetchall()
        
        level_map = {1: "Dễ", 2: "Trung bình", 3: "Khó"}
        questions_detail = []
        
        quiz_name = "Ôn tập"
        if detail_rows:
            quiz_name = detail_rows[0][4] # use subject name from first question

        for d_row in detail_rows:
            q_id, q_text, expl, diff, s_name, sel_ans_text, is_corr = d_row
            
            # Fetch options for this question
            # Using ORDER BY id if label is missing, but subjects.py uses label
            cur.execute("SELECT content, label, is_correct, id FROM answers WHERE question_id = %s ORDER BY label", (q_id,))
            ans_rows = cur.fetchall()
            
            options = [r[0] for r in ans_rows]
            correct_idx = next((i for i, r in enumerate(ans_rows) if r[2]), 0)
            
            # Find index of selected answer text in options
            sel_idx = None
            if sel_ans_text != "Unanswered":
                try:
                    sel_idx = options.index(sel_ans_text)
                except ValueError:
                    sel_idx = None

            questions_detail.append(SubmissionDetailQuestion(
                id=q_id,
                question=q_text,
                options=options,
                selected=sel_idx,
                correct=correct_idx,
                explanation=expl or "",
                subject=s_name,
                level=level_map.get(diff, "Trung bình"),
                is_correct=is_corr
            ))
            
        return SubmissionDetailResponse(
            submissionid=sub_row[0],
            score=sub_row[1],
            time_taken=sub_row[2],
            submit_time=sub_row[3].strftime("%Y-%m-%d %H:%M") if sub_row[3] else "",
            quiz_name=quiz_name,
            questions=questions_detail
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        with open(error_log_file, "a", encoding="utf-8") as f:
            f.write(f"\n--- ERROR at {submissionid} ---\n{err_msg}\n")
        print(err_msg)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
