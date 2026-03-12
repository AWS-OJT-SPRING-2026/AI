import json
from typing import Dict, Any

from prompt_builder import build_roadmap_prompt
from openai_service import OpenAIService
from dotenv import load_dotenv

# Tải biến môi trường (Ví dụ từ file .env chứa OPENAI_API_KEY)
load_dotenv()

def generate_roadmap(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Hàm chức năng chính để phân tích dữ liệu văn bản và sinh ra roadmap học tập.
    
    Args:
        input_data (dict): Dữ liệu đầu vào bắt buộc gồm các trường:
            - file_type (str)
            - raw_text (str)
            - user_request (str)
            - focus_keywords (list)
            
    Returns:
        dict: Roadmap học tập đạt chuẩn format đã được JSON Parse.
    """
    # Bước 1: Khởi tạo service gọi OpenAI
    service = OpenAIService()
    
    # Bước 2: Build prompt từ dữ liệu đầu vào
    prompt = build_roadmap_prompt(input_data)
    
    # Bước 3: Gửi request tới OpenAI, có cơ chế tự động retry 1 lần khi lỗi format
    result_data = service.generate_json_response(prompt=prompt, retries=1)
    
    return result_data


if __name__ == "__main__":
    # Ví dụ tích hợp hoặc sử dụng để debug
    sample_input = {
      "file_type": "PDF",
      "raw_text": (
          "Bài 1. Khái niệm cơ bản về Logistics. Logistics quản lý luồng di chuyển của dịch vụ và "
          "hàng hóa từ chuỗi cung ứng. Bao gồm 7R nguyên lý như sau: Right product, Right customer, "
          "Right time, Right place, Right condition, Right quantity, and Right cost. \n"
          "Bài 2. Quản lý Kho bãi. Kho bãi để lưu trữ nguyên vật liệu theo hệ thống công thức FIFO."
      ),
      "user_request": "Tạo roadmap học tập 2 tuần dựa trên tài liệu này, mỗi tuần một step.",
      "focus_keywords": ["Logistics", "7R", "Kho bãi"]
    }
    
    print("Đang phân tích tài liệu và sinh roadmap, vui lòng đợi...\n")
    try:
        roadmap = generate_roadmap(sample_input)
        
        # Hiển thị output
        print("KẾT QUẢ ĐẠT ĐƯỢC TỪ OPENAI:")
        print(json.dumps(roadmap, ensure_ascii=False, indent=2))
        
    except Exception as e:
        print(f"\n[LỖI CHƯƠNG TRÌNH]: {e}")
