import json
import argparse
from typing import Dict, Any

from .data_fetcher import fetch_wrong_questions
from .embedding_linker import link_questions_to_lessons
from .time_allocator import allocate_time
from .prompt_builder import build_lesson_explain_prompt
from .openai_service import OpenAIService
from .db_saver import save_roadmap_to_db

def generate_roadmap(student_id: int, subject_id: int, total_time_hours: float) -> int:
    """
    Hàm chức năng chính để sinh roadmap học tập dựa trên kết quả bài kiểm tra và lưu vào database.
    
    Args:
        student_id (int): ID của học sinh trong bảng students.
        subject_id (int): ID của môn học.
        total_time_hours (float): Tổng quỹ thời gian (giờ) người dùng cấp.
        
    Returns:
        int: ID của roadmap vừa được tạo trong database.
    """
    print(f"Bắt đầu quy trình tạo roadmap cho học sinh {student_id}, môn {subject_id}, thời gian {total_time_hours}h...")
    
    # Bước 1: Lấy các câu trả lời sai
    print("1. Đang truy xuất dữ liệu câu sai...")
    user_id, wrong_questions = fetch_wrong_questions(student_id, subject_id)
    if not wrong_questions:
        print("-> Học sinh chưa làm sai câu nào hoặc chưa có dữ liệu bài kiểm tra môn này.")
        return -1
    print(f"-> Tìm thấy {len(wrong_questions)} câu bị sai.")
    
    # Bước 2: Liên kết với bài học qua embedding
    print("2. Đang phân tích content blocks và link với bài học...")
    lesson_groups = link_questions_to_lessons(wrong_questions)
    if not lesson_groups:
        print("-> Không thể ánh xạ bất kỳ câu sai nào vào các bài học trong hệ thống.")
        return -1
    print(f"-> Đã ánh xạ vào {len(lesson_groups)} bài học cần ôn tập.")
        
    # Bước 3: Phân bổ thời gian
    print("3. Đang phân bổ thời gian hợp lý dựa trên trọng số câu sai...")
    allocated_times = allocate_time(lesson_groups, total_time_hours)
    
    # Bước 4: Tạo Explain bằng OpenAI cho từng bài học và format lại dữ liệu
    print("4. Đang kết nối OpenAI để sinh lời khuyên (explain) cho từng bài học...")
    service = OpenAIService()
    
    # Gom nhóm theo chapter để import vào DB dễ hơn
    chapters_data = {}
    
    for lesson_id, group in lesson_groups.items():
        chapter_id = group["chapter_id"]
        
        if chapter_id not in chapters_data:
            # Tạm thời để chapter_order = thứ tự thêm vào từ xa (hoặc rank tuỳ ý nếu schema hỗ trợ)
            chapters_data[chapter_id] = {
                "chapter_order": len(chapters_data) + 1,
                "lessons": []
            }
            
        time_for_lesson = allocated_times.get(lesson_id, 0.0)
        
        # Tạo prompt và gọi OpenAI
        prompt = build_lesson_explain_prompt(
            lesson_title=group["lesson_title"],
            wrong_questions=group["wrong_questions"]
        )
        
        try:
            llm_result = service.generate_json_response(prompt=prompt, retries=1)
            explain_text = llm_result.get("explain", "Cần ôn tập bài học này để củng cố kiến thức.")
        except Exception as e:
            print(f"-> [CẢNH BÁO] Không thể sinh explain cho bài học `{group['lesson_title']}`, dùng text mặc định. Lỗi: {e}")
            explain_text = "Cần ôn tập bài học này để củng cố kiến thức."
            
        # Tính toán mức độ ưu tiên tạm thời
        priority_score = time_for_lesson / total_time_hours if total_time_hours > 0 else 0
        
        chapters_data[chapter_id]["lessons"].append({
            "lesson_id": lesson_id,
            "time": time_for_lesson,
            "explain": explain_text,
            "wrong_question_count": len(group["wrong_questions"]),
            "priority_score": round(priority_score, 2)
        })
        print(f"  + Bài [{group['lesson_title']}]: {len(group['wrong_questions'])} lỗi -> {time_for_lesson}h")
        
    # Bước 5: Lưu dữ liệu
    print("5. Đang lưu thông tin Roadmap vào cơ sở dữ liệu...")
    roadmap_id = save_roadmap_to_db(student_id, total_time_hours, chapters_data)
    
    print(f"\n✅ Hoàn thành! Roadmap ID đã tạo: {roadmap_id}")
    return roadmap_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sinh roadmap cá nhân hoá bằng AI dựa trên lịch sử kiểm tra.")
    parser.add_argument("--student-id", type=int, required=True, help="ID của học sinh (bảng students).")
    parser.add_argument("--subject-id", type=int, required=True, help="ID của môn học (bảng subjects).")
    parser.add_argument("--total-time", type=float, required=True, help="Quỹ thời gian (tính bằng giờ).")
    
    args = parser.parse_args()
    
    try:
        generate_roadmap(args.student_id, args.subject_id, args.total_time)
    except Exception as err:
        print(f"\n[LỖI CHƯƠNG TRÌNH]: {err}")
