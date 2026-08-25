"""``/auth/*`` — login, refresh, me (kılavuz §4.5).

Akış:
1. POST /auth/login  — uniform 401 (kullanıcı enumeration yok), rate-limited.
2. POST /auth/refresh — refresh token ile yeni access üretir.
3. GET  /auth/me     — Bearer zorunlu, current user response.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.auth.dependencies import (
    get_current_settings,
    get_current_user,
    get_db_session,
)
from backend.src.api.auth.rate_limit import get_rate_limiter
from backend.src.api.auth.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
)
from backend.src.api.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from backend.src.api.auth.service import authenticate_user
from backend.src.api.utils.dependencies import AppState
from backend.src.data.db.models import User
from backend.src.observability.settings import Settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


# ---- /auth/login ---------------------------------------------------------

def _client_ip(request: Request) -> str:
    """İlk proxy IP'si değil, gerçek peer. Production'da reverse proxy
    başlığı (X-Forwarded-For) konfig'de eklenirse burası genişler.
    """
    if request.client is None:
        return "unknown"
    return request.client.host or "unknown"


@router.post("/login", response_model=TokenResponse,
             responses={401: {"description": "Invalid credentials"}})
async def login(
    request: Request,
    body: LoginRequest,
    settings: Annotated[Settings, Depends(get_current_settings)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """LDAP (öncelikli) veya local bcrypt üzerinden authenticate olur.

    Hata modları (hepsi 401 — kullanıcı enumeration yok):
    - username/password yanlış
    - kullanıcı LDAP_REQUIRED_GROUP'ta değil
    - kullanıcı disabled / is_active=false
    """
    state: AppState = request.app.state.container
    ip = _client_ip(request)
    limiter = get_rate_limiter()

    allowed, retry_after = limiter.check(ip, body.username)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts; retry after {retry_after}s",
            headers={"Retry-After": str(retry_after)},
        )

    user = await authenticate_user(session, body.username, body.password)
    if user is None:
        limiter.record_failure(ip, body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    limiter.record_success(ip, body.username)
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id, remember=body.remember_me)
    logger.info(
        "auth.login ok user=%s ldap=%s",
        user.username, bool(user.ldap_dn),
        extra={"actor_id": str(user.id)},
    )
    return TokenResponse(
        access_token=access.compact,
        refresh_token=refresh.compact,
        expires_in=access.ttl_seconds,
    )


# ---- /auth/refresh -------------------------------------------------------

@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    try:
        claims = decode_token(body.refresh_token, expected_type="refresh")
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {exc}",
        ) from exc

    from backend.src.api.auth.service import get_user_by_id
    from uuid import UUID as _UUID
    try:
        user_id = _UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Malformed subject") from exc

    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id, remember=False)
    return TokenResponse(
        access_token=access.compact,
        refresh_token=refresh.compact,
        expires_in=access.ttl_seconds,
    )


# ---- /auth/me ------------------------------------------------------------

@router.get("/me", response_model=MeResponse)
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> MeResponse:
    return MeResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
    )


__all__ = ["router"]
