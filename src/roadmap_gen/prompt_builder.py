from typing import Dict, Any

def build_roadmap_prompt(input_data: Dict[str, Any]) -> str:
    """
    Xây dựng prompt gửi tới OpenAI để tạo roadmap học tập.
    
    Args:
        input_data (dict): Dữ liệu đầu vào bao gồm:
            - file_type (str): Định dạng file (VD: PDF)
            - raw_text (str): Nội dung văn bản thô
            - user_request (str): Yêu cầu cụ thể của người dùng
            - focus_keywords (list): Danh sách các từ khóa cần tập trung
            
    Returns:
        str: Prompt hoàn chỉnh
    """
    file_type = input_data.get("file_type", "Unknown")
    raw_text = input_data.get("raw_text", "")
    user_request = input_data.get("user_request", "Tạo roadmap học tập chi tiết")
    focus_keywords = input_data.get("focus_keywords", [])
    
    keywords_str = ", ".join(focus_keywords) if focus_keywords else "Không có từ khóa cụ thể"
    
    prompt = f"""Bạn là một chuyên gia giáo dục và thiết kế chương trình học.
Hãy phân tích nội dung tài liệu dưới đây và tạo một lộ trình học tập (roadmap) dựa trên yêu cầu của người dùng.

THÔNG TIN TÀI LIỆU:
- Loại tài liệu: {file_type}
- Nội dung tài liệu:
{raw_text}

YÊU CẦU CỦA NGƯỜI DÙNG:
{user_request}

TỪ KHÓA TRỌNG TÂM:
{keywords_str}

YÊU CẦU SINH ROADMAP:
- Phân tích nội dung tài liệu để tạo roadmap.
- Phân chia roadmap thành các bước (step) hợp lý dựa trên yêu cầu của người dùng (ví dụ: nếu yêu cầu 4 tuần, tạo ít nhất 4 step lớn).
- Ưu tiên các nội dung liên quan đến các TỪ KHÓA TRỌNG TÂM.
- Mỗi bước (step) PHẢI bao gồm đầy đủ các thông tin sau:
  + step: Số thứ tự bước (số nguyên, ví dụ: 1, 2, 3).
  + title: Tiêu đề ngắn gọn của bước học hoặc nội dung học.
  + content: Mô tả chi tiết nội dung cần học.
  + reference_page: Trang tham chiếu (nếu có thể suy đoán từ văn bản, nếu không hãy đặt là null hoặc một số nguyên ước lượng).
  + key_takeaways: Danh sách các ý chính cần nắm vững.
- Cấu trúc trả về BẮT BUỘC phải là JSON hoàn chỉnh và chính xác.
- KHÔNG trả lời thêm bất kỳ văn bản nào ngoài JSON.
- KHÔNG sử dụng định dạng markdown (ví dụ: ```json ... ```).
- KHÔNG giải thích thêm.

Format kết quả BẮT BUỘC theo cấu trúc JSON sau:
{{
  "source_document": "Tên tài liệu hoặc nguồn gốc (ví dụ: Tài liệu từ văn bản đầu vào)",
  "roadmap": [
    {{
      "step": 1,
      "title": "Tiêu đề bước",
      "content": "Nội dung cần học",
      "reference_page": 1,
      "key_takeaways": [
        "Ý chính 1",
        "Ý chính 2"
      ]
    }}
  ]
}}
"""
    return prompt
