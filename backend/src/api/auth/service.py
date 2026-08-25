"""Auth service katmanı — directory login → user provisioning → JWT.

Kılavuz §4.4 verbatim; helper'lar idempotent upsert olarak modellendi.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.auth.ldap import (
    LdapIdentity,
    LdapUnavailableError,
    authenticate_ldap,
)
from backend.src.data.db.models import (
    LdapGroupMapping,
    OrgMembership,
    Organization,
    Role,
    RoleBinding,
    RoleBindingSource,
    User,
)
from backend.src.data.db.models.organizations import Namespace
from backend.src.observability.settings import get_settings

logger = logging.getLogger(__name__)


# ---- internal helpers ---------------------------------------------------

async def _get_user_by_ldap_dn(session: AsyncSession, dn: str) -> Optional[User]:
    return (await session.execute(
        select(User).where(User.ldap_dn == dn)
    )).scalar_one_or_none()


async def _get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    return (await session.execute(
        select(User).where(User.username == username)
    )).scalar_one_or_none()


async def _get_user_by_id(session: AsyncSession, user_id: UUID) -> Optional[User]:
    return (await session.get(User, user_id))


async def _ensure_org_membership(
    session: AsyncSession, user_id: UUID, org_id: UUID
) -> None:
    """Idempotent insert; iki kez aynı user+org sorun değil.

    Yarış koşulu: aynı tuple başka bir istek tarafından eklendiyse
    ``IntegrityError`` alırız — ama bunu **SAVEPOINT içine** alıp lokalde
    yutuyoruz ki caller'ın outer transaction'ı etkilenmesin.
    """
    existing = await session.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user_id,
            OrgMembership.org_id == org_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return
    try:
        async with session.begin_nested():
            session.add(OrgMembership(user_id=user_id, org_id=org_id))
    except IntegrityError:
        # same tuple was committed concurrently — arzu edilen sonuç.
        return


async def _ensure_role_binding(
    session: AsyncSession,
    user: User,
    role: Role,
    org_id: UUID,
    *,
    namespace_id: Optional[UUID],
    source: str,
) -> None:
    """Scope-aware idempotent upsert. ``namespace_id IS NULL`` ≠ ``namespace_id == x``."""
    stmt = select(RoleBinding).where(
        RoleBinding.user_id == user.id,
        RoleBinding.role_id == role.id,
        RoleBinding.org_id == org_id,
    )
    if namespace_id is None:
        stmt = stmt.where(RoleBinding.namespace_id.is_(None))
    else:
        stmt = stmt.where(RoleBinding.namespace_id == namespace_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        if existing.source != source:
            existing.source = source  # LDAP-sync bir manual kaydı override etmesin;
                                     # bu yol normalde çağrılmaz; aynı tuple için iki
                                     # binding yarışı engellenir.
        return
    try:
        async with session.begin_nested():
            session.add(RoleBinding(
                user_id=user.id,
                role_id=role.id,
                org_id=org_id,
                namespace_id=namespace_id,
                source=source,
            ))
    except IntegrityError:
        # unique (user, role, org, ns) race — başka istek ekledi, noop.
        return


async def _ensure_default_namespace_access(session: AsyncSession, user: User) -> None:
    """Kullanıcının hiç binding'i yoksa ``DEFAULT_NAMESPACE_SLUG`` üzerinde
    viewer yetkisi ver — ilk login dead-end olmasın (kılavuz §4.4).

    ``source='manual'`` ile işaretlenir ki LDAP sync bunu revoke etmesin.
    """
    settings = get_settings()
    slug = settings.default_namespace_slug.strip()
    if not slug:
        return
    # hiç binding'i var mı?
    has_any = (await session.execute(
        select(RoleBinding.id).where(RoleBinding.user_id == user.id).limit(1)
    )).scalar_one_or_none()
    if has_any is not None:
        return

    org = (await session.execute(
        select(Organization).where(Organization.slug == "default")
    )).scalar_one_or_none()
    if org is None:
        # Bootstrap admin bile default org yaratmamışsa atla.
        return
    namespace = (await session.execute(
        select(Namespace).where(
            Namespace.org_id == org.id, Namespace.slug == slug,
        )
    )).scalar_one_or_none()
    if namespace is None:
        return
    viewer = (await session.execute(
        select(Role).where(Role.name == "viewer")
    )).scalar_one_or_none()
    if viewer is None:
        return
    await _ensure_org_membership(session, user.id, org.id)
    await _ensure_role_binding(
        session, user, viewer, org.id,
        namespace_id=namespace.id, source=RoleBindingSource.MANUAL,
    )


# ---- public service funcs ----------------------------------------------

async def provision_ldap_user(
    session: AsyncSession, identity: LdapIdentity,
) -> User:
    """Upsert LDAP identity → User; authorize from group mappings.

    LDAP parolası **asla** saklanmaz — her login'de directory'ye yeniden
    bind yapılır.
    """
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
        )
        session.add(user)
    else:
        user.ldap_dn = identity.dn
        user.username = identity.username
        user.email = user.email or email
        user.display_name = identity.display_name or user.display_name
    await session.flush()

    # LDAP'dan gelen group listesi → mappings → desired grants.
    mappings: list[LdapGroupMapping] = []
    if identity.group_dns:
        mappings = list((await session.execute(
            select(LdapGroupMapping).where(
                LdapGroupMapping.group_dn.in_(identity.group_dns)
            )
        )).scalars().all())
    desired = {(m.role_id, m.org_id, m.namespace_id) for m in mappings}

    # Eski LDAP kaynaklı stale binding'leri temizle (manual olanlara dokunma).
    ldap_bindings = (await session.execute(
        select(RoleBinding).where(
            RoleBinding.user_id == user.id,
            RoleBinding.source == RoleBindingSource.LDAP,
        )
    )).scalars().all()
    for binding in ldap_bindings:
        if (binding.role_id, binding.org_id, binding.namespace_id) not in desired:
            await session.delete(binding)

    for mapping in mappings:
        role = await session.get(Role, mapping.role_id)
        if role is not None:
            try:
                async with session.begin_nested():
                    await _ensure_org_membership(session, user.id, mapping.org_id)
                    await _ensure_role_binding(
                        session, user, role, mapping.org_id,
                        namespace_id=mapping.namespace_id,
                        source=RoleBindingSource.LDAP,
                    )
            except IntegrityError:
                logger.warning(
                    "LDAP role binding integrity error (race): "
                    "user=%s role=%s org=%s ns=%s",
                    user.id, mapping.role_id, mapping.org_id, mapping.namespace_id,
                )

    await _ensure_default_namespace_access(session, user)
    user.last_login_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return user


async def authenticate_local(
    session: AsyncSession, username: str, password: str,
) -> Optional[User]:
    """Local bcrypt account. LDAP user'da password_hash NULL → False döner."""
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
    """Kılavuz §4.4 dispatch:

    - ``LDAP_ENABLED=false`` → local only.
    - ``LDAP_ENABLED=true`` → directory önce; ``LdapUnavailableError`` veya
      ``None`` durumunda ``LDAP_ALLOW_LOCAL_FALLBACK`` izin veriyorsa local'a düş.
    - ``LDAP_REQUIRED_GROUP`` set'liyse ``identity.member_of`` o DN'i
      içermeden provision yapılmaz (kullanıcı directory'de tanınmış olsa
      bile). Bu kontrol LDAP bypass'a karşı ikinci hattır: directory
      tarafında "eve-getirilen" hesaplar panel kullanıcısı olamaz.
    """
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
