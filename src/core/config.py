import os
from dotenv import load_dotenv

# Tải file .env từ thư mục hiện hành
load_dotenv()

class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "FastAPI App")
    VERSION: str = os.getenv("VERSION", "0.1.0")
    API_V1_STR: str = "/api/v1"
    
    # Bạn có thể thêm các cấu hình CSDL hoặc các key API khác tại đây
    # DATABASE_URL: str = os.getenv("DATABASE_URL", "")

settings = Settings()
