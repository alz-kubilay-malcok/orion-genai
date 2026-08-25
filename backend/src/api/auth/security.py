"""Password hashing (bcrypt) + JWT access/refresh üretim/doğrulama.

LDAP password HASH'lenmez veya LOG'lanmaz. Sadece bootstrap admin +
local fallback için bcrypt kullanılır (kılavuz invariant).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from jwt import InvalidTokenError

from backend.src.observability.settings import get_settings

logger = logging.getLogger(__name__)


# ---- Password hashing ---------------------------------------------------

def hash_password(plain: str) -> str:
    """bcrypt hash (60-char). Salt bcrypt tarafından üretilir."""
    if not plain:
        raise ValueError("password boş olamaz")
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str | None) -> bool:
    """LDAP kullanıcılarında ``hashed=None`` → False döner (kılavuz invariant)."""
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ---- JWT issuance ------------------------------------------------------

@dataclass(slots=True, frozen=True)
class IssuedToken:
    compact: str
    ttl_seconds: int
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _encode(payload: dict[str, Any], ttl: timedelta) -> IssuedToken:
    settings = get_settings()
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET tanımsız; token üretilemez")
    iat = _now()
    exp = iat + ttl
    body = {**payload, "iat": int(iat.timestamp()), "exp": int(exp.timestamp())}
    compact = jwt.encode(body, settings.jwt_secret, algorithm="HS256")
    return IssuedToken(compact=compact, ttl_seconds=int(ttl.total_seconds()), expires_at=exp)


def create_access_token(user_id: uuid.UUID | str) -> IssuedToken:
    """Access token — kısa ömürlü, içinde sadece user subject."""
    settings = get_settings()
    jti = uuid.uuid4().hex
    payload = {"sub": str(user_id), "type": "access", "jti": jti}
    return _encode(payload, timedelta(minutes=settings.jwt_access_ttl_minutes))


def create_refresh_token(
    user_id: uuid.UUID | str, *, remember: bool = False,
) -> IssuedToken:
    """Refresh token — uzun ömürlü; ``remember=True`` ile daha da uzun."""
    settings = get_settings()
    jti = uuid.uuid4().hex
    payload = {"sub": str(user_id), "type": "refresh", "jti": jti}
    days = settings.jwt_refresh_ttl_days * (7 if remember else 1)
    return _encode(payload, timedelta(days=days))


# ---- JWT validation -----------------------------------------------------

def decode_token(compact: str, *, expected_type: str) -> dict[str, Any]:
    """Token decode + type check. ``InvalidTokenError`` her hatada."""
    settings = get_settings()
    if not settings.jwt_secret:
        raise InvalidTokenError("JWT_SECRET tanımsız")
    claims = jwt.decode(
        compact, settings.jwt_secret, algorithms=["HS256"],
        options={"require": ["sub", "exp", "iat", "type"]},
    )
    if claims.get("type") != expected_type:
        raise InvalidTokenError(f"token type '{claims.get('type')!r}' != '{expected_type}'")
    return claims


__all__ = [
    "IssuedToken",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
