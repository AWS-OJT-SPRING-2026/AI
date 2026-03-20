from fastapi import APIRouter

api_router = APIRouter()

# Tại đây bạn có thể include các router từ các chức năng khác
from src.assignment_gen.router import router as assignment_router
api_router.include_router(assignment_router, prefix="/assignments", tags=["Assignments"])

# Một route test tạm thời trong scope của API
@api_router.get("/health")
def api_health_check():
    return {"status": "ok", "message": "API is running"}
