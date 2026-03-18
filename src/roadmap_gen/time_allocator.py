from typing import Dict, Any

def allocate_time(lesson_groups: Dict[int, Dict[str, Any]], total_time_hours: float) -> Dict[int, float]:
    """
    Phân bổ tổng thời gian ôn tập cho từng bài học tỷ lệ thuận với số lượng câu sai.
    
    Args:
        lesson_groups (dict): Dữ liệu các bài học đã được nhóm (key: lesson_id).
        total_time_hours (float): Tổng quỹ thời gian ôn tập.
        
    Returns:
        Dict[int, float]: Từ điển ánh xạ lesson_id với thời gian ôn tập (giờ).
    """
    if not lesson_groups or total_time_hours <= 0:
        return {}
        
    total_wrong_questions = sum(len(group["wrong_questions"]) for group in lesson_groups.values())
    
    if total_wrong_questions == 0:
        return {}
        
    allocated_times = {}
    remaining_time = total_time_hours
    
    # Tính toán cơ bản
    for lesson_id, group in lesson_groups.items():
        wrong_count = len(group["wrong_questions"])
        
        # Công thức: (số câu sai bài học / tổng câu sai) * tổng quỹ thời gian
        time_hours = (wrong_count / total_wrong_questions) * total_time_hours
        
        allocated_times[lesson_id] = round(time_hours, 2)
        
    # Đảm bảo tổng chính xác (xử lý do sai số làm tròn)
    total_allocated = sum(allocated_times.values())
    diff = round(total_time_hours - total_allocated, 2)
    
    if diff != 0 and allocated_times:
        # Cộng/trừ phần dư vào bài hc có nhiều câu sai nhất
        max_lesson_id = max(lesson_groups.keys(), key=lambda l: len(lesson_groups[l]["wrong_questions"]))
        allocated_times[max_lesson_id] = round(allocated_times[max_lesson_id] + diff, 2)
        
    return allocated_times
