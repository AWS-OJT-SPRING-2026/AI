from fastapi import APIRouter

api_router = APIRouter()

# Tại đây bạn có thể include các router từ các chức năng khác
from src.assignment_gen.router import router as assignment_router
from src.api.subjects import router as subjects_router
from src.api.books import router as books_router
from src.api.upload import router as upload_router
from src.api.roadmap import router as roadmap_router

api_router.include_router(assignment_router, prefix="/assignments", tags=["Assignments"])
api_router.include_router(subjects_router, prefix="/subjects", tags=["Subjects"])
api_router.include_router(books_router, prefix="/books", tags=["Books"])
api_router.include_router(upload_router, prefix="/upload", tags=["Upload"])
api_router.include_router(roadmap_router, prefix="/roadmap", tags=["Roadmap"])

# Một route test tạm thời trong scope của API
@api_router.get("/health")
def api_health_check():
    return {"status": "ok", "message": "API is running"}
