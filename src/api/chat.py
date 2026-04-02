"""
Chat proxy route — chuyển tiếp tin nhắn từ Frontend → Bedrock Agent (slozy_agent)
Trả về SSE stream giống format cũ để Frontend không cần sửa gì.
"""
import json
import boto3
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from src.core.config import settings

router = APIRouter()

# Bedrock Agent config
AGENT_ID = "slozy_agent-41V41aAl4L"
AGENT_ALIAS_ID = "TSTALIASID"  # Alias mặc định của AgentCore
REGION = settings.AWS_REGION


def _get_bedrock_client():
    """Tạo Bedrock Agent Runtime client dùng AWS credentials từ .env"""
    return boto3.client(
        "bedrock-agent-runtime",
        region_name=REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
    )


@router.post("/chat")
async def chat_proxy(request: Request):
    """
    Nhận tin nhắn từ Frontend, chuyển tới Bedrock Agent, stream kết quả về.

    Request body (giống format cũ):
    {
        "prompt": "Xin chào Slozy!",
        "session_id": "user123_session_001",
        "user_name": "Nguyễn Văn A"
    }

    Response: SSE stream — data: {"token": "..."}\n\n
    """
    body = await request.json()
    prompt = body.get("prompt", "Xin chào!")
    session_id = body.get("session_id", "default-session-0001")
    user_name = body.get("user_name", "")

    # Đảm bảo session_id đủ dài (AWS yêu cầu >= 2 ký tự)
    if len(session_id) < 2:
        session_id = f"session-{session_id}-pad"

    # Chuẩn bị input text (gửi kèm tên user nếu có)
    input_text = prompt
    if user_name:
        input_text = f"(Hệ thống báo: Bạn đang chat với học sinh tên là {user_name}. Hãy xưng hô thân thiện nếu cần)\n\n{prompt}"

    async def stream_agent_response():
        """Generator gọi Bedrock Agent và stream kết quả dạng SSE"""
        try:
            client = _get_bedrock_client()
            response = client.invoke_agent(
                agentId=AGENT_ID,
                agentAliasId=AGENT_ALIAS_ID,
                sessionId=session_id,
                inputText=input_text,
            )

            # Đọc stream từ Bedrock Agent
            for event in response.get("completion", []):
                if "chunk" in event:
                    chunk_bytes = event["chunk"].get("bytes", b"")
                    if chunk_bytes:
                        text = chunk_bytes.decode("utf-8")
                        # Gửi về Frontend đúng format SSE cũ
                        yield f"data: {json.dumps({'token': text})}\n\n"

        except Exception as e:
            error_msg = f"Lỗi kết nối Agent: {str(e)}"
            yield f"data: {json.dumps({'token': error_msg})}\n\n"

    return StreamingResponse(
        stream_agent_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
