"""
Cognito JWT Security Utilities.

Validates RS256 access tokens issued by AWS Cognito using the JWKS endpoint.
Maps Cognito `sub` to the local integer user ID stored in the `users` table.
"""
import json
import logging
import os
import time

import httpx
import jwt
import psycopg2
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# ── Swagger UI auth scheme ───────────────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=True)

# ── JWKS cache (refreshed every hour) ────────────────────────────────────────
_jwks_cache: dict = {"keys": [], "fetched_at": 0.0}
_JWKS_TTL = 3600  # seconds


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cognito_config() -> tuple[str, str, str]:
    """Return (user_pool_id, region, app_client_id)."""
    pool_id = os.getenv("COGNITO_USER_POOL_ID", "")
    region = os.getenv("COGNITO_REGION", "ap-southeast-1")
    client_id = os.getenv("COGNITO_APP_CLIENT_ID", "")
    if not pool_id or not client_id:
        raise RuntimeError(
            "COGNITO_USER_POOL_ID and COGNITO_APP_CLIENT_ID must be configured"
        )
    return pool_id, region, client_id


def _fetch_jwks_from_cognito() -> list:
    pool_id, region, _ = _cognito_config()
    url = (
        f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
        "/.well-known/jwks.json"
    )
    with httpx.Client(timeout=10) as client:
        resp = client.get(url)
        resp.raise_for_status()
    return resp.json().get("keys", [])


def _get_jwks() -> list:
    """Return cached JWKS keys, refreshing when the TTL has elapsed."""
    global _jwks_cache
    now = time.time()
    if not _jwks_cache["keys"] or now - _jwks_cache["fetched_at"] > _JWKS_TTL:
        _jwks_cache["keys"] = _fetch_jwks_from_cognito()
        _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def _find_public_key(kid: str):
    """
    Locate the RSA public key matching *kid* from the JWKS.
    On a cache miss the cache is invalidated and re-fetched once.
    """
    for key_data in _get_jwks():
        if key_data.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))

    # kid not in cache — force a refresh and retry once
    _jwks_cache["fetched_at"] = 0.0
    for key_data in _get_jwks():
        if key_data.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_data))

    return None


def _pick_existing_column(column_map: dict[str, str], candidates: tuple[str, ...]) -> str | None:
    """Return the first matching real column name for candidate aliases."""
    for candidate in candidates:
        real_name = column_map.get(candidate.lower())
        if real_name:
            return real_name
    return None


def _resolve_users_lookup_columns(conn) -> tuple[str, str] | None:
    """Resolve users.userid/user_id and users.cognito_sub-style columns."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'users'
            """
        )
        column_map = {row[0].lower(): row[0] for row in cur.fetchall()}

    user_id_col = _pick_existing_column(column_map, ("userid", "user_id"))
    cognito_sub_col = _pick_existing_column(
        column_map,
        ("cognito_sub", "cognitosub", "cognitoSub", "CognitoSub"),
    )

    if not user_id_col or not cognito_sub_col:
        logger.error(
            "Users table schema missing required columns for Cognito lookup "
            "(userid/user_id + cognito_sub). Available columns: %s",
            sorted(column_map.values()),
        )
        return None

    return user_id_col, cognito_sub_col


def _lookup_local_userid(cognito_sub: str) -> int | None:
    """
    Resolve the local integer ``userid`` for a Cognito identity.
    Returns *None* when the user has not yet been provisioned in the local DB.
    """
    conn = None
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            database=os.getenv("DB_NAME", "postgres"),
            user=os.getenv("DB_USERNAME", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )

        resolved_columns = _resolve_users_lookup_columns(conn)
        if resolved_columns is None:
            return None
        user_id_col, cognito_sub_col = resolved_columns

        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    f'SELECT "{user_id_col}" FROM users WHERE "{cognito_sub_col}" = %s LIMIT 1',
                    (cognito_sub,),
                )
                row = cur.fetchone()
        return int(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.error("DB lookup failed for Cognito sub=%s: %s", cognito_sub, exc)
        return None
    finally:
        if conn is not None:
            conn.close()


# ── Public API ────────────────────────────────────────────────────────────────

def decode_token(token: str) -> dict:
    """
    Decode and validate a Cognito RS256 access token.

    Raises HTTP 401 on expired, invalid, or untrusted tokens.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.DecodeError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
        )

    kid = header.get("kid")
    public_key = _find_public_key(kid) if kid else None
    if public_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Không tìm thấy khóa xác thực (JWKS)",
        )

    pool_id, region, client_id = _cognito_config()
    issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"verify_exp": True},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token đã hết hạn",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token không hợp lệ: {exc}",
        )

    # Cognito access-token specific validations
    if payload.get("token_use") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không phải access token của Cognito",
        )
    if payload.get("client_id") != client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không khớp với ứng dụng",
        )

    return payload


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> int:
    """
    FastAPI dependency — validates a Cognito Bearer token and returns
    the caller's local integer user ID (``users.userid``).

    Raises HTTP 401 when:
    - The token is expired, invalid, or not a Cognito access token.
    - The Cognito identity has no matching row in the local ``users`` table
      (i.e. the user has never logged in via the main system).
    """
    payload = decode_token(credentials.credentials)

    cognito_sub: str = payload.get("sub", "")
    if not cognito_sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token thiếu claim 'sub'",
        )

    user_id = _lookup_local_userid(cognito_sub)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Tài khoản chưa được đồng bộ với hệ thống. "
                "Vui lòng đăng nhập qua trang chính trước."
            ),
        )

    return user_id
