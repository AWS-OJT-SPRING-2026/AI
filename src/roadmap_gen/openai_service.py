import os
import json
from typing import Dict, Any, Optional
from openai import OpenAI

class OpenAIService:
    """
    Service xử lý giao tiếp với OpenAI API cho việc tạo roadmap.
    """
    def __init__(self, api_key: Optional[str] = None):
        """
        Khởi tạo OpenAIService.
        Nếu không truyền vào, nó sẽ tự động lấy từ biến môi trường OPENAI_API_KEY.
        
        Args:
            api_key (str, optional): API Key của OpenAI. Defaults to None.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("Không tìm thấy OPENAI_API_KEY. Vui lòng thiết lập biến môi trường hoặc truyền vào qua tham số.")
            
        self.client = OpenAI(api_key=self.api_key)

    def _validate_roadmap_schema(self, data: Dict[str, Any]) -> bool:
        """
        Kiểm tra tính hợp lệ của cấu trúc trả về dựa trên yêu cầu JSON format.
        
        Args:
            data (dict): Dictionary kết quả trả về từ API.
            
        Returns:
            bool: True nếu format chuẩn, False nếu thiếu hoặc sai kiểu.
        """
        if not isinstance(data, dict):
            return False
            
        if "source_document" not in data or "roadmap" not in data:
            return False
            
        roadmap = data.get("roadmap")
        if not isinstance(roadmap, list) or len(roadmap) == 0:
            return False
            
        for item in roadmap:
            required_keys = {"step", "title", "content", "reference_page", "key_takeaways"}
            if not required_keys.issubset(item.keys()):
                return False
                
            if not isinstance(item.get("step"), int):
                return False
                
            if not isinstance(item.get("key_takeaways"), list):
                return False
                
        return True

    def generate_json_response(self, prompt: str, retries: int = 1) -> Dict[str, Any]:
        """
        Gửi yêu cầu tới OpenAI API và xử lý kết quả lấy khối JSON.
        
        Args:
            prompt (str): Text prompt hoàn chỉnh gửi tới OpenAI.
            retries (int): Số lượt retry nếu parse JSON lỗi hoặc thiếu schema. Defaults to 1.
            
        Returns:
            dict: Kết quả API sau khi đã parse từ JSON string.
            
        Raises:
            RuntimeError: Sinh roadmap thất bại sau số lần thử nghiệm.
        """
        for attempt in range(retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini", # Bạn có thể thay đổi sang gpt-4o tùy nhu cầu
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant designed to output strictly valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.7,
                )
                
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("API trả về nội dung rỗng.")
                    
                result_data = json.loads(content)
                
                if not self._validate_roadmap_schema(result_data):
                    raise ValueError("JSON trả về không hợp lệ so với cấu trúc đã yêu cầu.")
                    
                return result_data
                
            except json.JSONDecodeError as e:
                print(f"[Attempt {attempt + 1}/{retries + 1}] Lỗi parse JSON: {e}")
                if attempt == retries:
                    raise RuntimeError(f"Tạo JSON thất bại sau {retries + 1} lần thử do lỗi định dạng JSON.")
            except ValueError as e:
                print(f"[Attempt {attempt + 1}/{retries + 1}] Lỗi cấu trúc: {e}")
                if attempt == retries:
                    raise RuntimeError(f"Tạo dữ liệu thất bại sau {retries + 1} lần thử do lỗi schema: {str(e)}")
            except Exception as e:
                print(f"[Attempt {attempt + 1}/{retries + 1}] Lỗi OpenAI API: {e}")
                if attempt == retries:
                    raise RuntimeError(f"Gọi OpenAI API thất bại qua các lần thử: {str(e)}")
