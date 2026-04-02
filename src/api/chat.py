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
    """Tạo Bedrock AgentCore Runtime client dùng AWS credentials từ .env"""
    return boto3.client(
        "bedrock-agentcore",  # AWS service mới cho AgentCore
        region_name=REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
    )


@router.post("/chat")
async def chat_proxy(request: Request):
    """
    Nhận tin nhắn từ Frontend, chuyển tới Bedrock AgentCore.
    """
    body = await request.json()
    prompt = body.get("prompt", "Xin chào!")
    session_id = body.get("session_id", "default-session-0001")
    user_name = body.get("user_name", "")

    # Chuẩn bị payload đúng chuẩn Giao tiếp của AgentCore Container
    request_payload = {
        "prompt": prompt,
        "session_id": session_id,
        "user_name": user_name
    }

    async def stream_agent_response():
        """Generator gọi Bedrock AgentCore (Method A) và stream kết quả dạng SSE"""
        try:
            client = _get_bedrock_client()
            
            # API mới invoke_agent_runtime
            response = client.invoke_agent_runtime(
                agentRuntimeArn=f"arn:aws:bedrock-agentcore:{REGION}:982092375481:runtime/{AGENT_ID}",
                runtimeSessionId=session_id,
                payload=json.dumps(request_payload).encode("utf-8")
            )

            # Lấy data trả về từ AgentCore (StreamingBody)
            stream = response.get("response")
            if stream:
                for line in stream.iter_lines():
                    if line:
                        chunk_text = line.decode('utf-8')
                        # Phun thẳng từng dòng trả về cho Frontend
                        yield f"{chunk_text}\n"

        except Exception as e:
            error_msg = f"Lỗi kết nối AgentCore: {str(e)}"
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
