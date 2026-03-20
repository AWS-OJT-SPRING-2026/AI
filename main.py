from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.api.router import api_router

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Cấu hình CORS (Cross-Origin Resource Sharing) middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Thêm địa chỉ FE của bạn vào đây ở môi trường production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Nhúng router API tổng với cấu hình prefix
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def read_root():
    return {"message": "Welcome to AI Backend Server. Go to /docs for Swagger UI"}
