"""Auth service — local bcrypt + LDAP bind-as-user, then User upsert.

v1 LDAP is basic: upsert User, set ``is_superuser`` from ``LDAP_ADMIN_GROUP``.
Org/namespace/role-binding sync is deferred.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.auth.ldap import (
    LdapIdentity,
    LdapUnavailableError,
    authenticate_ldap,
)
from backend.src.data.db.models import User
from backend.src.observability.settings import get_settings

logger = logging.getLogger(__name__)


async def _get_user_by_ldap_dn(session: AsyncSession, dn: str) -> Optional[User]:
    return (await session.execute(
        select(User).where(User.ldap_dn == dn)
    )).scalar_one_or_none()


async def _get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    return (await session.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()


async def _get_user_by_id(session: AsyncSession, user_id: UUID) -> Optional[User]:
    return await session.get(User, user_id)


def _is_ldap_admin(identity: LdapIdentity) -> bool:
    admin_group = (get_settings().ldap_admin_group or "").strip()
    if not admin_group:
        return False
    return admin_group in (identity.group_dns or [])


async def provision_ldap_user(
    session: AsyncSession, identity: LdapIdentity,
) -> User:
    """Upsert LDAP identity → User. Password is never stored."""
    user = await _get_user_by_ldap_dn(session, identity.dn)
    if user is None:
        user = await _get_user_by_username(session, identity.username)
    email = identity.email or f"{identity.username}@ldap.local"
    if user is None:
        user = User(
            username=identity.username,
            ldap_dn=identity.dn,
            email=email,
            display_name=identity.display_name,
            password_hash=None,
            is_active=True,
            is_superuser=_is_ldap_admin(identity),
        )
        session.add(user)
    else:
        user.ldap_dn = identity.dn
        user.username = identity.username
        user.email = user.email or email
        user.display_name = identity.display_name or user.display_name
        user.password_hash = None
        # LDAP_ADMIN_GROUP her login'de superuser yapar. Panelden verilen
        # yetki (bootstrap/LDAP admin) sonraki login'de silinmez.
        user.is_superuser = _is_ldap_admin(identity) or user.is_superuser
    user.last_login_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return user


async def authenticate_local(
    session: AsyncSession, username: str, password: str,
) -> Optional[User]:
    """Local bcrypt account. LDAP users have password_hash NULL → fail."""
    from backend.src.api.auth.security import verify_password

    user = (await session.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return user


async def authenticate_user(
    session: AsyncSession, username: str, password: str,
) -> Optional[User]:
    """LDAP first when enabled; optional local fallback on miss/outage."""
    settings = get_settings()
    if not settings.ldap_enabled:
        user = await authenticate_local(session, username, password)
        return user if (user and user.is_active) else None

    required_group = (settings.ldap_required_group or "").strip() or None
    user: Optional[User] = None
    try:
        identity = await authenticate_ldap(username, password)
        if identity is not None:
            group_ok = (
                required_group is None
                or required_group in (identity.group_dns or [])
            )
            if group_ok:
                user = await provision_ldap_user(session, identity)
            else:
                logger.info(
                    "login denied: user=%s LDAP_REQUIRED_GROUP=%s match yok",
                    username, required_group,
                )
    except LdapUnavailableError as exc:
        logger.warning("LDAP unavailable for %s: %s", username, exc)

    if user is None and settings.ldap_allow_local_fallback:
        user = await authenticate_local(session, username, password)

    return user if (user and user.is_active) else None


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> Optional[User]:
    return await _get_user_by_id(session, user_id)


__all__ = [
    "authenticate_local",
    "authenticate_user",
    "get_user_by_id",
    "provision_ldap_user",
]
