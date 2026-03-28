import os
from dotenv import load_dotenv

# Tải file .env từ thư mục hiện hành
load_dotenv()

class Settings:
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "FastAPI App")
    VERSION: str = os.getenv("VERSION", "0.1.0")
    API_V1_STR: str = "/api/v1"
    
    # DB & AWS
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_NAME: str = os.getenv("DB_NAME", "postgres")
    DB_USERNAME: str = os.getenv("DB_USERNAME", "postgres")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    
    AWS_ACCESS_KEY: str = os.getenv("AWS_ACCESS_KEY", "")
    AWS_SECRET_KEY: str = os.getenv("AWS_SECRET_KEY", "")
    
    # Legacy / compatibility
    DATABASE_NAME: str = os.getenv("DB_NAME", "postgres")
    POSTGRESQL_PASSWORD: str = os.getenv("DB_PASSWORD", "")

settings = Settings()
