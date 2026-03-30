"""
JWT Token Security Utilities.

Decodes JWT tokens issued by the Java Spring Boot backend (CustomJwtDecoder).
Uses the shared HMAC signer key from configuration.
"""
import os
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ── Security scheme for Swagger UI ──────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=True)


def _get_signer_key() -> str:
    """Retrieve the JWT signer key shared with the Java backend."""
    key = os.getenv("JWT_SIGNER_KEY", "")
    if not key:
        raise RuntimeError("JWT_SIGNER_KEY environment variable is not set")
    return key


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.
    
    The Java backend signs tokens with HS512 using the literal UTF-8 bytes 
    of the secret key.
    """
    signer_key = _get_signer_key()
    secret_bytes = signer_key.encode("utf-8")

    try:
        payload = jwt.decode(
            token,
            secret_bytes,
            algorithms=["HS512", "HS256"],
            options={"verify_exp": True},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token đã hết hạn",
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token không hợp lệ: {str(e)}",
        )


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> int:
    """
    FastAPI dependency that extracts the user ID from the JWT Bearer token.
    
    The Java backend stores the user ID in the 'userID' claim.
    """
    payload = decode_token(credentials.credentials)

    # The Java Spring Boot backend puts the user ID in 'userID' claim
    user_id = payload.get("userID") or payload.get("userId") or payload.get("userid")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không tìm thấy thông tin người dùng trong token",
        )

    try:
        return int(user_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Không thể xác định user ID từ token",
        )

