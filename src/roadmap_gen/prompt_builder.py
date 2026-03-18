from typing import Dict, Any

def build_lesson_explain_prompt(lesson_title: str, wrong_questions: list) -> str:
    """
    Xây dựng prompt gửi tới OpenAI để giải thích tại sao học sinh cần ôn tập môn học này dựa trên các câu sai.
    
    Args:
        lesson_title (str): Tiêu đề của bài học.
        wrong_questions (list): Danh sách các câu hỏi thuộc bài học này mà học sinh làm sai.
            Mỗi câu có: question_text, selected_answer_label, correct_answer_label, correct_answer_content.
            
    Returns:
        str: Prompt hoàn chỉnh
    """
    questions_context = ""
    for idx, q in enumerate(wrong_questions, 1):
        questions_context += f"Câu hỏi {idx}: {q.get('question_text')}\n"
        questions_context += f"- Lựa chọn sai của học sinh: {q.get('selected_answer_label')}\n"
        questions_context += f"- Đáp án đúng: {q.get('correct_answer_label')} - {q.get('correct_answer_content')}\n\n"
        
    prompt = f"""Bạn là một giáo viên tận tâm đang phân tích kết quả bài kiểm tra của một học sinh.
Vừa qua, học sinh đã làm sai một số câu hỏi thuộc bài học: "{lesson_title}".

DƯỚI ĐÂY LÀ DANH SÁCH CÁC CÂU HỎI HỌC SINH ĐÃ LÀM SAI TRONG BÀI THI:
{questions_context.strip()}

YÊU CẦU DÀNH CHO BẠN:
1. Phân tích điểm mù kiến thức của học sinh: Dựa vào sự khác biệt giữa "lựa chọn sai của học sinh" và "đáp án đúng", hãy chỉ ra học sinh đang nhầm lẫn ở điểm nào phần kiến thức này.
2. Tại sao cần ôn tập lại bài học này: Đưa ra lời khuyên hoặc lý do thuyết phục (explain) tại sao học sinh cần dành thời gian để ôn luyện lại kiến thức bài "{lesson_title}".
3. Viết ở ngôi thứ ba thân thiện, hướng trực tiếp đến học sinh (ví dụ: "Em đang bị nhầm lẫn giữa...", "Để cải thiện, em cần ôn tập...").
4. Cấu trúc trả về BẮT BUỘC phải là định dạng JSON cực ngắn gọn chứa đúng một key "explain".

Format kết quả BẮT BUỘC theo cấu trúc JSON sau:
{{
  "explain": "Đoạn giải thích chi tiết khoảng 3-4 câu hướng dẫn học sinh."
}}
"""
    return prompt
