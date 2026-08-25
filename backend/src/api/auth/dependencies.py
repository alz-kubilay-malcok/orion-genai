"""``AppState``'e yardımcı bağımlılıklar (bootstrap admin + auth deps).

``build_app_state`` lifespan'ında çağrılır; route handler'lar için
dependency factory'leri burada durur.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.auth.security import decode_token
from backend.src.api.auth.service import get_user_by_id
from backend.src.api.utils.dependencies import AppState
from backend.src.data.db.models import User
from backend.src.observability.settings import Settings

logger = logging.getLogger(__name__)


# ---- bootstrap admin seed ------------------------------------------------

async def ensure_bootstrap_admin(state: AppState) -> None:
    """``BOOTSTRAP_ADMIN_*`` env'inden idempotent User + RoleBindings.

    Davranış:
    - ``bootstrap_admin_enabled=false`` → noop.
    - Kullanıcı yoksa bcrypt hash ile yaratır.
    - Rolü: ``is_superuser=True`` + tüm mevcut rollere ``role_bindings``.
    - Default org/namespace yoksa bu layer sadece user'ı yaratır; admin
      paneli sonradan mapping kuracak.
    """
    if not state.settings.bootstrap_admin_enabled:
        return
    from backend.src.api.auth.security import hash_password

    username = state.settings.bootstrap_admin_username.strip()
    email = state.settings.bootstrap_admin_email.strip() or f"{username}@local"
    password = state.settings.bootstrap_admin_password

    async with state.session_factory() as session:
        existing = (await session.execute(
            select(User).where(User.username == username)
        )).scalar_one_or_none()
        if existing is not None:
            # Passwd güncellemesi senkron cron'unda değil; sadece hash uydurmuyoruz.
            existing.is_superuser = True
            existing.is_active = True
            await session.flush()
            return
        user = User(
            id=uuid4(),
            username=username,
            email=email,
            display_name="bootstrap admin",
            is_active=True,
            is_superuser=True,
            password_hash=hash_password(password),
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()


# ---- request-time dependencies --------------------------------------------

_BEARER_SCHEME = HTTPBearer(auto_error=False)


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Her route için bir session; hata olursa rollback + close."""
    state: AppState = request.app.state.container
    async with state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_BEARER_SCHEME),
    session: AsyncSession = Depends(get_db_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = decode_token(credentials.credentials, expected_type="access")
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Malformed token subject") from exc
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def get_current_settings(request: Request) -> Settings:
    """``AppState.settings``'i route handler'a geçirir (lru_cache bypass)."""
    state: AppState = request.app.state.container
    return state.settings


# ---- optional helpers (legacy uyumluluk) --------------------------------

async def try_get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_BEARER_SCHEME),
    session: AsyncSession = Depends(get_db_session),
) -> User | None:
    """Bearer varsa kullanıcıyı döndür; yoksa ``None``.

    Legacy admin endpoint'lerinin kaldırılmayacağı varsayımıyla (kılavuz
    admin panelini kaldırmıyor): token yoksa 401 atmak yerine
    ``system:anonymous`` fallback sağlar. Login zorunlu hale gelince bu
    helper kaldırılır ve doğrudan ``get_current_user`` kullanılır.

    Session: ``Depends(get_db_session)`` ile request-scoped AsyncSession
    alır; yeni bir session factory çağrısı UoW transaction'ı yarışa
    sokmaz. Eğer mevcut session'a bağlı bir aktif transaction varsa, User
    SELECT'i kendi connection'ında çalışır (read-after-write: iki UoW arası
    görünürlük sorunu yaşanabilir; commit'ten sonra çağrılan handler'lar
    için güvenli).
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        claims = decode_token(credentials.credentials, expected_type="access")
    except InvalidTokenError:
        return None
    try:
        user_id = UUID(claims["sub"])
    except (KeyError, ValueError):
        return None
    user = await get_user_by_id(session, user_id)
    if user is None or not user.is_active:
        return None
    return user


__all__ = [
    "ensure_bootstrap_admin",
    "get_current_settings",
    "get_current_user",
    "get_db_session",
    "try_get_current_user",
]
