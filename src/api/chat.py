"""
Chat proxy route — chuyển tiếp tin nhắn từ Frontend → agent-core (local hoặc Bedrock AgentCore deployed).
Trả về SSE stream giống format cũ để Frontend không cần sửa gì.
"""
import json
import os
import boto3
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from src.core.config import settings

router = APIRouter()

# Bedrock Agent config
AGENT_ID = "slozy_agent-41V41aAl4L"
REGION = settings.AWS_REGION

LOCAL_DEV = os.getenv("LOCAL_DEV", "0") == "1"
LOCAL_AGENT_URL = os.getenv("LOCAL_AGENT_URL", "http://localhost:8080/invocations")


def _get_bedrock_client():
    """Tạo Bedrock AgentCore Runtime client dùng AWS credentials từ .env"""
    return boto3.client(
        "bedrock-agentcore",
        region_name=REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
    )


@router.post("")
async def chat_proxy(request: Request):
    """
    Nhận tin nhắn từ Frontend, chuyển tới agent-core (local dev) hoặc Bedrock AgentCore (production).
    LOCAL_DEV=1  → gọi http://localhost:8080/invocations qua httpx
    LOCAL_DEV=0  → gọi AWS Bedrock AgentCore qua boto3
    """
    body = await request.json()
    prompt = body.get("prompt", "Xin chào!")
    session_id = body.get("session_id", "default-session-0001")
    user_name = body.get("user_name", "")

    request_payload = {
        "prompt": prompt,
        "session_id": session_id,
        "user_name": user_name,
    }

    if LOCAL_DEV:
        async def stream_agent_response():
            """Gọi agent-core local tại /invocations và forward SSE stream"""
            try:
                import httpx
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream("POST", LOCAL_AGENT_URL, json=request_payload) as response:
                        response.raise_for_status()
                        # agent-core trả về SSE: "data: {...}\n\n"
                        # Forward thẳng từng chunk mà không parse lại
                        async for chunk in response.aiter_bytes():
                            if chunk:
                                yield chunk
            except Exception as e:
                error_msg = f"Lỗi kết nối agent-core local: {str(e)}"
                yield f"data: {json.dumps({'token': error_msg})}\n\n".encode("utf-8")
    else:
        async def stream_agent_response():
            """Gọi Bedrock AgentCore deployed qua boto3"""
            try:
                client = _get_bedrock_client()
                response = client.invoke_agent_runtime(
                    agentRuntimeArn=f"arn:aws:bedrock-agentcore:{REGION}:982092375481:runtime/{AGENT_ID}",
                    runtimeSessionId=session_id,
                    payload=json.dumps(request_payload).encode("utf-8"),
                )
                stream = response.get("response")
                if stream:
                    for line in stream.iter_lines():
                        if line:
                            chunk_text = line.decode("utf-8")
                            yield f"{chunk_text}\n".encode("utf-8")
            except Exception as e:
                error_msg = f"Lỗi kết nối AgentCore: {str(e)}"
                yield f"data: {json.dumps({'token': error_msg})}\n\n".encode("utf-8")

    return StreamingResponse(
        stream_agent_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
