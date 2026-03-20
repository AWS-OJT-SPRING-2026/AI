from fastapi import APIRouter, HTTPException, status
from src.assignment_gen.schemas import AssignmentCreateRequest, AssignmentCreateResponse
from src.assignment_gen.assignment_generator import create_assignment

router = APIRouter()

@router.post("/", response_model=AssignmentCreateResponse, status_code=status.HTTP_201_CREATED)
def generate_assignment(request: AssignmentCreateRequest):
    """
    Tạo mới một bài tập (assignment) từ DB kết hợp với số lượng câu hỏi AI sinh thêm nếu cần.
    """
    try:
        # Gọi hàm logic create_assignment, bung kwargs
        result = create_assignment(**request.model_dump())
        return result
    except ValueError as e:
        # Bắt lỗi logic từ hàm gốc gửi lên (VD: Số câu AI không được lớn hơn tổng số câu)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # Các lỗi khác như DB error
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Lỗi hệ thống khi tạo assignment: {str(e)}")
